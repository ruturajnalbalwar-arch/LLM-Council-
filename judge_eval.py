"""Automated scoring of blind_scoring.csv using an LLM judge.

    python judge_eval.py

Two passes, in this order, and the order is the point:

  1. Read queries.json ONLY and write a completeness checklist for each query.
     The judge never sees an answer during this pass. Saved to checklists.json.
  2. Score every answer against its checklist, one answer at a time, without
     the condition label and without any other answer for comparison.

Writes the four score columns into blind_scoring.csv and produces
consistency.csv.

READ THIS BEFORE USING THE OUTPUT
---------------------------------
The judge is Llama 3.3 70B, the same model that produced the answers it is
scoring. That is the self-enhancement bias documented by Zheng et al. [21],
which your paper already cites. It means these scores are weaker evidence than
human scoring, and the paper must say the scoring was automated. Do not describe
this as two independent annotators.

Spot-check a sample by hand and report the agreement rate. `python judge_eval.py
--sample 10` prints ten random answers with the scores the judge gave, for
exactly that purpose.
"""
import csv
import json
import os
import random
import re
import sys
import time

from groq import Groq

MODEL = "llama-3.3-70b-versatile"
client = Groq(api_key=os.environ["GROQ_API_KEY"])


def ask(system, user, max_tokens=700):
    for attempt in range(4):
        try:
            r = client.chat.completions.create(
                model=MODEL, temperature=0.0, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            return r.choices[0].message.content
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                time.sleep((attempt + 1) * 10)
            else:
                raise
    raise SystemExit("judge call failed after 4 attempts")


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in judge output: %r" % text[:200])
    return json.loads(m.group(0))


# ── pass 1: checklists, written without seeing any answer ────────────────────
def build_checklists(queries):
    if os.path.exists("checklists.json"):
        print("checklists.json exists, reusing it")
        return json.load(open("checklists.json", encoding="utf8"))

    sys_p = ("You write evaluation checklists. Given a question, list the "
             "distinct points that any complete and correct answer must "
             "contain. Between 4 and 6 points. Each point must be specific "
             "enough that a reader can decide yes or no whether an answer "
             "contains it. Reply with JSON only: "
             '{"points": ["...", "..."]}')
    out = {}
    for q in queries:
        r = parse_json(ask(sys_p, "Question: " + q["query"]))
        out[q["id"]] = r["points"]
        print("  %s  %d points" % (q["id"], len(r["points"])))
    json.dump(out, open("checklists.json", "w", encoding="utf8"), indent=1)

    with open("checklists.md", "w", encoding="utf8") as f:
        for q in queries:
            f.write("## %s  %s\n\n" % (q["id"], q["query"]))
            for p in out[q["id"]]:
                f.write("- %s\n" % p)
            f.write("\n")
    print("wrote checklists.json and checklists.md")
    return out


# ── pass 2: score each answer alone ──────────────────────────────────────────
SCORE_SYS = (
    "You grade a single answer to a question. Work strictly and do not be "
    "generous.\n\n"
    "claims_total: count the checkable factual claims the answer makes. A "
    "claim is checkable if it could be confirmed or refuted against a "
    "reference. Opinions, hedges and restatements of the question are not "
    "claims. If you are not confident whether a claim is true or false, "
    "exclude it from claims_total entirely rather than guessing.\n"
    "claims_correct: how many of those claims are correct.\n"
    "checklist_total: the number of checklist points given to you.\n"
    "checklist_covered: how many checklist points the answer actually "
    "contains. Mentioning a topic is not covering the point.\n\n"
    "Do not reward length, confidence or formatting. Reply with JSON only: "
    '{"claims_total": n, "claims_correct": n, "checklist_total": n, '
    '"checklist_covered": n}')


def score_rows(checklists):
    rows = list(csv.DictReader(open("blind_scoring.csv", newline="", encoding="utf8")))
    for i, r in enumerate(rows):
        if r["claims_total"].strip():
            continue
        points = checklists[r["qid"]]
        user = ("Question: %s\n\nChecklist:\n%s\n\nAnswer to grade:\n%s"
                % (r["query"],
                   "\n".join("- " + p for p in points),
                   r["answer"]))
        v = parse_json(ask(SCORE_SYS, user, max_tokens=300))
        v["checklist_total"] = len(points)
        v["claims_correct"] = min(v["claims_correct"], v["claims_total"])
        v["checklist_covered"] = min(v["checklist_covered"], len(points))
        r.update({k: v[k] for k in
                  ("claims_total", "claims_correct",
                   "checklist_total", "checklist_covered")})
        if i % 10 == 0:
            print("  scored %d/%d" % (i, len(rows)))

    with open("blind_scoring.csv", "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print("wrote scores into blind_scoring.csv")
    return rows


# ── consistency across the 5 repeats ─────────────────────────────────────────
CONS_SYS = ("You are given several answers to the same question, produced by "
            "the same system on separate runs. Decide whether they all reach "
            "the same substantive conclusion. Ignore differences in wording, "
            "length, ordering and formatting. Reply with JSON only: "
            '{"all_agree": true} or {"all_agree": false}')


def consistency():
    runs = [json.loads(l) for l in open("runs.jsonl", encoding="utf8")]
    groups = {}
    for r in runs:
        groups.setdefault((r["qid"], r["condition"]), []).append(r)

    with open("consistency.csv", "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["qid", "condition", "all_agree"])
        for (qid, cond), rs in sorted(groups.items()):
            if len(rs) < 2:
                continue
            body = "\n\n".join("Run %d:\n%s" % (i + 1, x["answer"])
                               for i, x in enumerate(rs))
            v = parse_json(ask(CONS_SYS,
                               "Question: %s\n\n%s" % (rs[0]["query"], body),
                               max_tokens=100))
            w.writerow([qid, cond, "y" if v["all_agree"] else "n"])
    print("wrote consistency.csv")


def sample(n):
    rows = list(csv.DictReader(open("blind_scoring.csv", newline="", encoding="utf8")))
    random.seed()
    for r in random.sample(rows, min(n, len(rows))):
        print("\n" + "=" * 70)
        print("Q:", r["query"])
        print("\nANSWER:\n", r["answer"][:1200])
        print("\nJUDGE:", {k: r[k] for k in
                           ("claims_total", "claims_correct",
                            "checklist_total", "checklist_covered")})
    print("\nCheck these yourself and report how often you agree.")


if "--sample" in sys.argv:
    sample(int(sys.argv[sys.argv.index("--sample") + 1]))
else:
    qs = json.load(open("queries.json", encoding="utf8"))
    print("Pass 1: checklists (no answers seen)")
    cl = build_checklists(qs)
    print("\nPass 2: scoring")
    score_rows(cl)
    print("\nPass 3: consistency")
    consistency()
    print("\nDone. Scoring was automated. Say so in the paper, and spot-check "
          "with: python judge_eval.py --sample 10")
