"""Aggregate scored runs into comparison.csv for Table III and Fig. 2.

Run after you have filled in blind_scoring.csv:

    python score_eval.py

Reads runs.jsonl, blind_scoring.csv, blind_key.csv and consistency.csv.
Writes comparison.csv and per_category.csv.
"""
import csv
import json
from collections import defaultdict

COND = {"single": "Single call", "cot": "CoT matched", "council": "Atheneum"}
ORDER = ["single", "cot", "council"]


def read_csv(path):
    with open(path, newline="", encoding="utf8") as f:
        return list(csv.DictReader(f))


runs = [json.loads(l) for l in open("runs.jsonl", encoding="utf8")]
key = {r["row"]: r["condition"] for r in read_csv("blind_key.csv")}
scored = read_csv("blind_scoring.csv")

blank = [r["row"] for r in scored
         if not all(r[c].strip() for c in
                    ("claims_total", "claims_correct",
                     "checklist_total", "checklist_covered"))]
if blank:
    raise SystemExit("blind_scoring.csv has unscored rows: %s" % ", ".join(blank))

# accuracy and completeness, per condition and per category
acc = defaultdict(lambda: [0, 0])
comp = defaultdict(lambda: [0, 0])
acc_cat = defaultdict(lambda: [0, 0])

for r in scored:
    c = key[r["row"]]
    acc[c][0] += int(r["claims_correct"])
    acc[c][1] += int(r["claims_total"])
    comp[c][0] += int(r["checklist_covered"])
    comp[c][1] += int(r["checklist_total"])
    acc_cat[(c, r["category"])][0] += int(r["claims_correct"])
    acc_cat[(c, r["category"])][1] += int(r["claims_total"])

# consistency: you mark, per query and condition, whether the 5 repeats agreed
try:
    cons_rows = read_csv("consistency.csv")
    cons = defaultdict(lambda: [0, 0])
    for r in cons_rows:
        cons[r["condition"]][0] += 1 if r["all_agree"].strip().lower() in ("y", "yes", "1") else 0
        cons[r["condition"]][1] += 1
except FileNotFoundError:
    cons = None
    print("consistency.csv not found. Leaving that row blank.")

lat = defaultdict(list)
tok = defaultdict(list)
for r in runs:
    lat[r["condition"]].append(r["latency"])
    tok[r["condition"]].append(r["tokens_in"] + r["tokens_out"])


def pct(pair):
    return "" if not pair[1] else round(100 * pair[0] / pair[1], 1)


def mean(xs):
    return "" if not xs else round(sum(xs) / len(xs), 1)


with open("comparison.csv", "w", newline="", encoding="utf8") as f:
    w = csv.writer(f)
    w.writerow(["Metric"] + [COND[c] for c in ORDER])
    w.writerow(["Factual accuracy"] + [pct(acc[c]) for c in ORDER])
    w.writerow(["Reasoning consistency"] +
               [pct(cons[c]) if cons else "" for c in ORDER])
    w.writerow(["Completeness"] + [pct(comp[c]) for c in ORDER])
print("wrote comparison.csv")

with open("latency_tokens.csv", "w", newline="", encoding="utf8") as f:
    w = csv.writer(f)
    w.writerow(["Measure"] + [COND[c] for c in ORDER])
    w.writerow(["Mean latency (s)"] + [mean(lat[c]) for c in ORDER])
    w.writerow(["Mean tokens per query"] + [mean(tok[c]) for c in ORDER])
print("wrote latency_tokens.csv (rows 4 and 5 of Table III)")

cats = sorted({c for _, c in acc_cat})
with open("per_category.csv", "w", newline="", encoding="utf8") as f:
    w = csv.writer(f)
    w.writerow(["Category"] + [COND[c] for c in ORDER])
    for cat in cats:
        w.writerow([cat] + [pct(acc_cat[(c, cat)]) for c in ORDER])
print("wrote per_category.csv")
