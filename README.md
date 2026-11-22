# LLM-Council: does multi-agent debate actually help?

This is the evaluation harness for [Atheneum](https://github.com/ruturajnalbalwar-arch/atheneum), a five-stage debate between Llama 3.3 70B agents. It tests one claim: **a debate between agents gives more reliable answers than one model answering once**. The design follows Smit et al., *Should We Be Going MAD?* (ICML 2024), so gains that come only from spending more tokens aren't credited to the debate.

## Design

Every query runs under three conditions:

| Condition | What it is | What it answers |
|---|---|---|
| `single` | One plain call | Is the council better than the usual approach? |
| `cot` | One chain-of-thought call. Its output budget is **set to the tokens the council actually used** on the same query | Does the debate structure help, or just the extra compute? |
| `council` | The full 17-call Atheneum pipeline | — |

The council runs first, and the `cot` budget is taken from its measured token use instead of guessed.

**What gets measured**
- Factual accuracy, as a percentage of checkable claims that are correct
- Reasoning consistency: 5 repeats per query, and how often they reach the same conclusion
- Completeness against a checklist written before any answer was seen
- Latency and tokens

**Blind scoring:** `blind_scoring.csv` shuffles the answers and hides which condition produced each one.

**Human ratings:** [`reader_study.csv`](reader_study.csv) holds ratings from human readers. [`make_figures.py`](make_figures.py) won't plot a row with a missing value, so no figure can show a made-up number.

## Files

| File | Purpose |
|---|---|
| [`run_eval.py`](run_eval.py) | Runs all conditions and writes `runs.jsonl` and `blind_scoring.csv` |
| [`score_eval.py`](score_eval.py), [`judge_eval.py`](judge_eval.py) | Score the runs (human scoring and LLM-judge scoring) |
| [`queries.json`](queries.json) | Evaluation queries |
| [`docs/CONTEXT.md`](docs/CONTEXT.md) | Why the design is the way it is. Read this before changing anything |
| [`docs/CODE_VS_PAPER.md`](docs/CODE_VS_PAPER.md) | How the code maps to the paper |
| [`.github/workflows/evaluate.yml`](.github/workflows/evaluate.yml) | Runs the evaluation on GitHub Actions: `smoke` (about 20 calls) or `full` (about 450) |

## Run

```bash
pip install -r requirements.txt
export GROQ_API_KEY=...  CEREBRAS_API_KEY=...
python run_eval.py --smoke     # quick check
python run_eval.py             # full run
```

You can also add the two keys as repository secrets and start the **Evaluate** workflow from the Actions tab.

**Status:** the harness is complete. Results will be added here after the full run and the reader study.
