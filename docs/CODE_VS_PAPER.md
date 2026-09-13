# What the code does vs. what the draft claimed

I read `app_complete.py` line by line. Seven things in the previous draft did not
match your implementation. All seven are now corrected in the docx. Listing them
because you need to know what changed and why, and because four of them are
things you may want to fix in the code rather than in the paper.

---

### 1. The peer ranking rubric did not exist

**Draft said:** five weighted criteria (logical consistency 0.25, factual
correctness 0.25, completeness 0.20, relevance 0.15, clarity 0.15), each scored
1 to 5.

**Code does:** `stage4` shows all four answers relabelled Response A to D, asks
each agent for an ordered list under a `FINAL RANKING:` marker, parses it with
`re.findall(r"Response\s+[A-Z]")`, and averages positions.

This was the most serious one. I invented that rubric when I wrote the first
draft, and publishing a method description that does not match the code is the
same category of problem as inventing data. Table II is now a table of the
pipeline stages as actually built, and the ranking text describes the ordinal
mechanism.

### 2. Self-scores are not excluded

**Draft said:** an agent's score for its own answer is discarded.

**Code does:** every agent ranks all four answers, including its own. The labels
are anonymised, which helps, but an agent can recognise its own writing.

Zheng et al. [21] is cited in your paper on exactly this bias, so a reviewer who
follows the citation will check. Now written honestly as a limitation. **Worth
fixing in code** — it is a few lines in `stage4`.

### 3. Forced disagreement applies to every agent, not just the Maverick

**Draft said:** only the Maverick is adversarial by design.

**Code does:** `stage2` appends `" You are in a debate. Disagree with at least 2
others specifically."` to *every* agent's system prompt.

This is a real design choice with a real cost, and the paper now discusses it:
it guarantees critiques get produced, but an agent with nothing to object to
will manufacture an objection.

### 4. Agent diversity comes from temperature, which the draft never mentioned

**Code does:** Logician 0.3, Scout 0.5, Scholar 0.7, Maverick 0.95, Chairman 0.4.
Logician, Scout and Chairman on Groq; Maverick and Scholar on Cerebras. Both
providers serve Llama 3.3 70B.

Temperature is your second diversity mechanism and it was missing entirely. Now
in Section III. The two-provider split is also stated precisely: same weights,
different serving stack, so it is not model diversity.

### 5. Stage 3 does not require reasons for rejected critiques

**Draft said:** agents must accept a point and change the answer, or reject it
and say why.

**Code does:** `"Defend what holds. Concede valid points. Write your FINAL answer."`

The framing is right but the reason requirement is not there, so rejections are
not recoverable for analysis. **Worth fixing in code** — one sentence in the
prompt, and it makes the refinement stage auditable.

### 6. Failure handling is worse than the draft described

**Draft said:** a failed agent is dropped and the stage proceeds with the rest.

**Code does:** `call_model` returns `"[Name failed: ...]"` on error, and that
string flows into stage 2, stage 3, stage 4 and the Chairman prompt as if it
were an answer. Other agents attack it. The ranking stage ranks it. Nothing
downstream checks for the marker.

This one matters for your results. A run where one agent failed still produces a
confident final answer and looks identical to a clean run. **Fix this before you
run the evaluation**, or at minimum grep your logged answers for `failed:` and
discard those runs. The paper now names it as a limitation.

### 7. The agreement score was missing from the paper

**Code does:** `confidence()` computes what share of agents ranked the same
answer first and labels the query strong consensus (at least 0.75), good
agreement (at least 0.5), or contested.

This is a genuinely good feature and it was not in the paper at all. Now in
Section III.C. It is also a free reliability signal you can report in results,
and a contested label is meaningful output rather than a failure.

---

## What stayed correct

Seventeen model calls per query. Asynchronous execution within stages, so
latency is about five sequential calls. Stages sequential. Chairman does not
answer in stage 1 and does not participate in critique or ranking. Chairman
prompt has an explicit disagreement section. All confirmed against the code.
