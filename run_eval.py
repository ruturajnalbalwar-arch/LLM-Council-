"""Run the evaluation described in Section V of the paper.

Place this file in the repo root (next to app_complete.py) and run:

    pip install -r requirements.txt
    export GROQ_API_KEY=...
    export CEREBRAS_API_KEY=...
    python run_eval.py

Writes runs.jsonl (every answer, with latency and token counts) and
blind_scoring.csv (answers shuffled, condition hidden, for you to score).

Three conditions per query:
  single   one plain Groq call
  cot      one Groq call with chain-of-thought, max_tokens matched to the
           mean output budget Atheneum actually consumed
  council  the full five-stage pipeline from app_complete.py

app_complete.py calls demo.launch() at import time, so this loads only the
pipeline half of the file (everything above the GRADIO UI marker).
"""
import asyncio
import csv
import json
import os
import random
import sys
import time
import types

SMOKE = "--smoke" in sys.argv
REPEATS = 1 if SMOKE else 5   # runs per query per condition, for consistency
OUT_RUNS = "runs.jsonl"
OUT_SHEET = "blind_scoring.csv"


# ── load the pipeline without launching the Gradio app ───────────────────────
def load_pipeline(path="app_complete.py"):
    src = open(path, encoding="utf8").read()
    cut = src.index("# ── GRADIO UI")
    mod = types.ModuleType("atheneum_pipeline")
    mod.__dict__["__name__"] = "atheneum_pipeline"
    exec(compile(src[:cut], path, "exec"), mod.__dict__)
    return mod


app = load_pipeline()

for key in ("GROQ_API_KEY", "CEREBRAS_API_KEY"):
    if not os.environ.get(key):
        raise SystemExit("%s is not set. Export it before running." % key)


# ── token accounting ─────────────────────────────────────────────────────────
# app_complete's callers return only the message content, so wrap them to
# record usage as a side effect. Nothing about the pipeline's behaviour changes.
USAGE = []
_orig_groq, _orig_cerebras = app.call_groq, app.call_cerebras


def _wrap(orig, provider):
    async def wrapped(model, system, user, temperature, max_tokens):
        from openai import AsyncOpenAI
        from groq import AsyncGroq
        if provider == "groq":
            client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
        else:
            client = AsyncOpenAI(api_key=os.environ["CEREBRAS_API_KEY"],
                                 base_url="https://api.cerebras.ai/v1")
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature, max_tokens=max_tokens)
        u = resp.usage
        USAGE.append((u.prompt_tokens, u.completion_tokens))
        return resp.choices[0].message.content
    return wrapped


app.call_groq = _wrap(_orig_groq, "groq")
app.call_cerebras = _wrap(_orig_cerebras, "cerebras")


# ── the three conditions ─────────────────────────────────────────────────────
async def run_council(q):
    USAGE.clear()
    t0 = time.time()
    r1 = await app.stage1(q)
    r2 = await app.stage2(q, r1)
    r3 = await app.stage3(q, r1, r2)
    r4, ltm = await app.stage4(q, r3)
    csys, cuser = app.build_chairman_prompt(q, r1, r2, r3, r4, ltm)
    # app_complete streams the Chairman, and streamed responses carry no usage
    # object, so call it unstreamed here. Same model, temperature, prompt and
    # max_tokens, so the output distribution is unchanged; only the tokens
    # become countable.
    chair = {"provider": "groq", "model": app.CHAIRMAN["model"],
             "temperature": app.CHAIRMAN["temperature"]}
    text = await app.call_model(chair, csys, cuser, max_tokens=2000)
    elapsed = time.time() - t0
    tin = sum(a for a, _ in USAGE)
    tout = sum(b for _, b in USAGE)
    return {"answer": text, "latency": elapsed, "calls": len(USAGE),
            "tokens_in": tin, "tokens_out": tout,
            "consensus": app.confidence(r4, ltm)}


async def run_single(q, cot, budget):
    USAGE.clear()
    member = {"provider": "groq", "model": app.MODEL_70B, "temperature": 0.4}
    system = ("You are a knowledgeable assistant. Answer accurately and completely."
              + (" Think step by step, then state your final answer." if cot else ""))
    t0 = time.time()
    text = await app.call_model(member, system, q, max_tokens=budget)
    elapsed = time.time() - t0
    tin = sum(a for a, _ in USAGE)
    tout = sum(b for _, b in USAGE)
    return {"answer": text, "latency": elapsed, "calls": 1,
            "tokens_in": tin, "tokens_out": tout, "consensus": ""}


# ── main ─────────────────────────────────────────────────────────────────────
async def preflight():
    """One cheap call to each provider before spending the real budget."""
    for provider, model in (("groq", app.MODEL_70B),
                            ("cerebras", app.MODEL_CEREBRAS)):
        member = {"provider": provider, "model": model, "temperature": 0.0}
        t0 = time.time()
        out = await app.call_model(member, "Reply with one word.", "Say ok",
                                   max_tokens=10)
        if out.startswith("["):
            raise SystemExit("%s call failed: %s" % (provider, out))
        print("  %-9s ok  %.1fs  %r" % (provider, time.time() - t0, out[:30]))
    print()


async def main():
    queries = json.load(open("queries.json", encoding="utf8"))
    if SMOKE:
        queries = queries[:2]
        print("SMOKE MODE: 2 queries, 1 repeat, 3 conditions. "
              "Delete runs.jsonl before the real run.\n")
    print("Preflight...")
    await preflight()
    rows = []

    # Pass 1: council. Its mean output tokens set the budget for the cot baseline,
    # which is what makes that comparison fair (see Smit et al. [4] in the paper).
    print("Council runs...")
    for qi, item in enumerate(queries):
        for rep in range(REPEATS):
            r = await run_council(item["query"])
            r.update(qid=item["id"], category=item["category"],
                     query=item["query"], condition="council", repeat=rep)
            rows.append(r)
            print("  %s rep%d  %.1fs  %d tok out" % (item["id"], rep,
                                                     r["latency"], r["tokens_out"]))

    council_out = [r["tokens_out"] for r in rows if r["condition"] == "council"]
    budget = max(500, min(8000, int(sum(council_out) / len(council_out))))
    print("\nMean council output: %d tokens. CoT baseline budget set to %d.\n"
          % (budget, budget))

    for cond, cot, bud in (("single", False, 500), ("cot", True, budget)):
        print("%s runs..." % cond)
        for item in queries:
            for rep in range(REPEATS):
                r = await run_single(item["query"], cot, bud)
                r.update(qid=item["id"], category=item["category"],
                         query=item["query"], condition=cond, repeat=rep)
                rows.append(r)

    with open(OUT_RUNS, "w", encoding="utf8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print("wrote %s (%d runs)" % (OUT_RUNS, len(rows)))

    # Blind scoring sheet: first repeat only, shuffled, condition replaced by a key
    first = [r for r in rows if r["repeat"] == 0]
    random.seed(7)
    random.shuffle(first)
    with open(OUT_SHEET, "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["row", "qid", "category", "query", "answer",
                    "claims_total", "claims_correct", "checklist_total",
                    "checklist_covered"])
        for i, r in enumerate(first):
            w.writerow([i, r["qid"], r["category"], r["query"],
                        r["answer"].replace("\n", " "), "", "", "", ""])
    with open("blind_key.csv", "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["row", "condition"])
        for i, r in enumerate(first):
            w.writerow([i, r["condition"]])
    print("wrote %s and blind_key.csv" % OUT_SHEET)
    fails = [r for r in rows if "failed" in r["answer"][:60].lower()]
    if fails:
        print("\nWARNING: %d of %d runs contain a failure marker. "
              "app_complete.py passes these downstream as if they were answers, "
              "so these runs are contaminated. Discard them or fix call_model "
              "before trusting the numbers." % (len(fails), len(rows)))

    if SMOKE:
        print("\nSmoke run finished. If the answers look sane, "
              "delete runs.jsonl and run without --smoke.")
    else:
        print("\nScore blind_scoring.csv without opening blind_key.csv, "
              "then run score_eval.py")


asyncio.run(main())
