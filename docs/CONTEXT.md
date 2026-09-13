# What this evaluation is for

Context for whoever (or whatever) is setting this up. Read before touching the
files, because a few of the choices look wrong until you know the reason.

## The system

Atheneum is a multi-agent debate framework. A user asks one question and five
Llama 3.3 70B agents handle it across five stages:

1. Four agents (Logician, Scout, Maverick, Scholar) answer independently
2. Each attacks the other three answers
3. Each defends and rewrites its own answer
4. All four rank the final answers under anonymised labels
5. A Chairman agent, which took no part in the debate, writes the final answer

Seventeen model calls per question. Agents within a stage run concurrently, so
latency is about five sequential calls. The Logician, Scout and Chairman go
through Groq; the Maverick and Scholar through Cerebras. Both serve the same
weights, so the agents differ by instruction and sampling temperature (0.3, 0.5,
0.95, 0.7) rather than by model.

## The claim being tested

That a debate between agents produces more reliable answers than one model
answering once.

## Why there are three conditions, not two

This is the part that matters most, and it is easy to get wrong.

- **single**: one plain call. The obvious comparison.
- **cot**: one call, chain-of-thought prompt, output budget set to the mean
  output the debate pipeline actually consumed on the same queries.
- **council**: the full five-stage pipeline.

Smit et al. (ICML 2024, "Should We Be Going MAD?") found that reported gains
from multi-agent debate often shrink or vanish once you compare against a
properly tuned single agent given the same compute. Some of the improvement
credited to debate is really just the extra tokens.

So `single` vs `council` answers "is this better than what I do now," and `cot`
vs `council` answers "is the debate structure doing the work, or is it just the
extra compute." Only the second is evidence about the method. Reporting only the
first is the error Smit et al. identified, and a reviewer who knows that paper
will go straight for it.

This is why `run_eval.py` runs the council first and derives the cot budget from
measured token usage rather than guessing it up front. Do not "simplify" that.

## What gets measured

- **Factual accuracy**: checkable claims that are correct, as a percentage
- **Reasoning consistency**: how often 5 repeats of the same query reach the
  same conclusion
- **Completeness**: fraction of a checklist, written before any answer was seen,
  that the answer covers
- **Latency and tokens**: the cost side of the trade

Answers are scored blind. `blind_scoring.csv` hides which condition produced
each answer; `blind_key.csv` holds the mapping and must not be opened until
scoring is finished.

## Why the failure-marker bug blocks everything

`call_model` in `app_complete.py` returns `"[The Scout failed: ...]"` on error,
and that string flows into stages 2 through 5 as if it were an answer. Agents
attack it, the ranking stage ranks it, the Chairman receives it.

Groq's free tier will rate limit during a 450-call run. Every run that hits this
produces a confident final answer that is indistinguishable from a clean one, so
the contamination is invisible in the output. Fix it first or the numbers mean
nothing.

## The outcome is not predetermined

A result showing debate helping on ambiguous and multi-step queries but not on
factual recall, with the budget-matched baseline closing most of the gap, is a
real finding and a defensible paper. Flat or negative results are publishable
here. Nothing in this pipeline should be adjusted to make the council look
better, and no number should ever be estimated, extrapolated or filled in by
hand. If a step fails, stop and report it.
