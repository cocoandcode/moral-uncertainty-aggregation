# The distillation extension, explained from the ground up

Written 25 Aug 2026, after steps 1-4 completed. This is the plain-English
companion to `DISTILLATION_EXTENSION.md` (the plan) — read this to
understand *what is actually going on*; read that one for the frozen
decisions and the step list.

---

## Part 1: The metrics, with a worked example

Every number in `distil_eval/` is one of four metrics. They exist because
"the student copies the teacher" can fail in more than one way, and each
metric sees a different failure.

### The running example

Real utilitarian teacher scores for the first six responses to the coach
dilemma, and a hypothetical student's scores for the same six:

| Response | R1 | R2 | R3 | R4 | R5 | R6 |
|---|---|---|---|---|---|---|
| Teacher | 3 | 8 | 4 | 8 | 5 | 8 |
| Student | 1 | 9 | 2 | 6 | 1 | 6 |

The student is clearly *related* to the teacher (low where teacher is low,
high where high) but sits lower overall, and it has knocked R5 down badly
(teacher 5, student 1).

### MAE — "off by how many points?"

Mean Absolute Error: average of |student − teacher| over all responses.

Here: |3−1| + |8−9| + |4−2| + |8−6| + |5−1| + |8−6| = 13, divided by 6 =
**2.17**. On average this student is off by about two points on the 0-10
rubric.

MAE is the only metric in the *original units* — "off by one point" means
something to a human reading the rubric. Its blind spot: it can't tell a
harmless systematic offset (always 2 points stingier) from a scramble
that happens to average two points of error. The correlations separate
those cases.

### Pearson — "do the values move together?"

Pearson correlation measures *linear* agreement: when the teacher goes up
by some amount, does the student go up proportionally? It ranges from -1
to +1, and it forgives constant offsets and rescalings — a student that
is exactly `teacher − 2` scores a perfect 1.0.

Here: **0.90**. Very high, despite the visible 2-point stinginess and
the R5 error — Pearson cares about the overall linear pattern, and the
big moves (3→8 type jumps) dominate it.

Why it matters: it's the standard "did the copy track the teacher"
number, comparable across papers. Why it's not enough: it's dominated by
easy, coarse distinctions and barely feels one or two flipped rankings.

### Spearman — "is the ORDER right, even if the numbers aren't?"

Spearman is Pearson computed on ranks instead of raw scores. Replace each
score with its rank within the set, then correlate the ranks. It throws
away calibration entirely and asks only: did the student order the
responses the way the teacher did?

Here: **0.84** — lower than Pearson, because the student broke the
teacher's orderings in a way ranks feel more sharply: the teacher has
R5 (5) above R3 (4), but the student put R5 (1) below R3 (2).

Why it matters: our judges are systematically lenient (deontology puts
~47% of scores at 9-10), and a well-calibrated-but-reordered copy is
worse for us than a miscalibrated-but-correctly-ordered one, because
aggregation consumes *comparisons*, not absolute values.

### Kendall tau — "of every pair, did both pick the same winner?"

Kendall tau looks at every *pair* of responses and asks: did teacher and
student agree on which of the two is better? Pairs that agree are
*concordant*, pairs that disagree (teacher says A > B, student says
B > A) are *discordant*. Tau is roughly (concordant − discordant) / (all
pairs): +1 = every pairwise verdict matches, 0 = coin-flip, −1 =
systematically reversed.

Here, of the 15 pairs among six responses: 4 involve a tie on one side or
the other, leaving 11 cleanly comparable. 10 agree; exactly one flips
(R3 vs R5, as above). The tau-b variant (which corrects for the tied
pairs; it's what scipy and our code compute) gives **0.72**.

Why this one matters most: the judges' actual job in the pipeline is to
rank the 16 candidate responses within one dilemma so aggregation can
pick a winner. Tau counts precisely those pairwise verdicts. A student
can post Pearson 0.90 — as this one does — and still flip the pair that
decides a dilemma's winner. Tau is the metric that notices.

**Within-dilemma tau**, the number reported in `distil_eval/`, is tau
computed separately inside each of the 100 held-out dilemmas (16
responses each) and then averaged. Corpus-wide correlations can be
inflated by easy between-dilemma distinctions ("thorough answers beat
lazy refusals"); within-dilemma tau cannot — it only rewards ordering
siblings correctly, which is the hard part and the part that matters.

### Why all four together

| Pattern | Diagnosis |
|---|---|
| High Pearson, high Spearman, high tau | Faithful copy (still must pass the axiom exam) |
| High Pearson, low tau | Matches scores in the large, shuffles close pairs — lethal for aggregation |
| High Spearman/tau, low Pearson | Right order, wrong calibration — breaks maximin (which reads levels), mostly survives EC and Nash |
| All near the floor | Learned vocabulary, not the judge |

And none of them is the axiom exam. The correlations ask "same numbers as
the teacher, on ordinary responses?" The axiom exam asks "does it prefer
helping 200 people over 30, when everything else about the two responses
is identical?" The bag-of-words pilot proved these come apart: decent
correlation, chance on the axioms.

---

## Part 2: The floor — what a know-nothing model scores

**What it is:** a ridge regression (a linear model) over bag-of-words
features of the *response text only*. No dilemma, no word order, no
meaning — literally "which words appear in this response". Script:
`distil_floor.py`, rebuilt 25 Aug because the original pilot script was
never saved (never cite numbers whose code doesn't exist).

**Why it exists:** the judges' scores are entangled with style — response
length alone explains 31% of the utilitarian judge's score variance. So
some correlation is earnable with zero ethical understanding. The floor
measures exactly how much. Any real student must beat it, or it has
learned nothing beyond word statistics.

**The rebuilt floor numbers** (held-out, same metrics code as the
students; slightly stronger than the unsaved pilot's 0.68/0.53/0.64 —
cite these, not the pilot's):

| Judge | Pearson | Spearman | MAE | Within-dilemma tau |
|---|---|---|---|---|
| Utilitarian | 0.757 | 0.688 | 1.20 | 0.283 |
| Deontological | 0.593 | 0.603 | 1.65 | 0.184 |
| Ubuntu | 0.679 | 0.647 | 1.48 | 0.327 |

The pilot's axiom result for a floor-style model was 73% / 74% / 44%
(Ut/De/Ub) — Ubuntu at chance. The rebuilt floor sits ready to take the
step-6 axiom exam alongside the students.

---

## Part 3: The ceiling — how well the teacher agrees with itself

**What it is (= step 7 of the plan):** send ~200 held-out responses
through `gpt-4o-mini` *again*, same three judge prompts, and correlate
the fresh scores with the originals in `scores/*.json`. About 600 API
calls.

**Why it matters:** the teacher is not deterministic — even at
temperature 0.1, re-scoring the same response can give a different
number. No student can honestly agree with the teacher more than the
teacher agrees with itself, so teacher self-agreement is the ceiling
against which student numbers must be read. If the teacher's own
within-dilemma tau against itself is ~0.55, a student at 0.40 is a
decent copy of a noisy instrument; if the teacher self-agrees at 0.9,
the student has a real gap. Without the ceiling, the tau column is
uninterpretable.

**Why "optional":** it changes no decision and trains nothing — it only
calibrates interpretation. But it is cheap and, given the moderate tau
results, clearly worth running.

---

## Part 4: How the students were actually trained

### The data

One training example = one response to one dilemma. From
`distil_data/train.jsonl` (6,400 rows = 400 dilemmas x 16 responses):

- **Input:** the literal text
  `Dilemma:\n\n{dilemma}\n\nResponse to evaluate:\n\n{response}` —
  the same format the teacher saw in `score_responses.py`. Tokenised,
  capped at 1,024 tokens.
- **Target:** that response's teacher score for ONE framework — an
  integer 0-10. Three training runs, identical in every way except which
  score column is the target.

40 of the 400 training dilemmas were carved out (seed 42) as a
validation set, used only to watch for overfitting during training. The
100 held-out dilemmas in `heldout.jsonl` were never read by the training
script at all.

### The model

`Qwen2.5-1.5B-Instruct` is a text-generating transformer. We removed its
word-predicting head and bolted on a fresh **score head**: a single
linear layer from the model's final hidden state (a 1,536-number summary
of the whole input, taken at the last token) to **11 outputs**, one per
possible score. A softmax turns those into probabilities:
"5% it's a 4, ... 70% it's a 9, 20% it's a 10".

So a forward pass is: read dilemma + response → 1,536-dim summary → 11
probabilities over the scores 0-10.

### The loss: cross-entropy

If the teacher's score is 3, the loss is −log p(3) — the model is
punished by how little probability it put on the correct score. It is
*not* punished by distance (guessing 4 vs guessing 9 when the truth is 3
costs the same); with 6,400 examples the model learns the ordinal
structure from the data itself.

Why classification and not regression (frozen decision, since confirmed
empirically): the teachers are verdict-makers with lumpy, near-bimodal
score distributions — deontology piles up at ~4 ("violates the duty")
and ~9 ("honours it") with an empty middle. A regression model trained
on distance (MSE) responds to uncertainty by predicting the middle of
the two humps (~6.5) — a score the teacher never gives — which corrupts
exactly what the pipeline reads: absolute levels (maximin) and tie
structure. A classifier can instead say "50% it's a 4, 50% it's a 9",
which is the truthful answer. The regression twin we trained as a sanity
check lost on every held-out metric (Pearson 0.796 vs 0.836, tau 0.341
vs 0.397).

**Decoding (frozen before training):** expected value over the 11
probabilities for all correlation metrics and axiom comparisons;
expected value rounded to the nearest integer for the aggregation
replay, so ties behave like the teacher's.

### What was updated: LoRA

The 1.5 billion base weights stayed **frozen**. Trained:

- **LoRA adapters** on the four attention projections (query, key,
  value, output) in each of the 28 layers. LoRA never touches the
  original matrix W; it learns a correction B·A where A and B are thin
  rank-16 matrices, and the layer computes Wx + BAx. Thin matrices =
  few parameters, and the correction is a separate file.
- **The score head**, trained from scratch.

Total: 4.4M trainable parameters — 0.28% of the model. This is why each
trained judge is a 28 MB file (`distil_models/*/adapter_model.safetensors`)
riding on a public 3 GB base anyone can download, rather than three 3 GB
models we'd have to distribute.

### The loop

AdamW optimiser, learning rate 1e-4, effective batch 16 (8 per step,
gradients accumulated over 2), 2 epochs over 5,760 rows = 720 optimiser
steps, seed 42, bf16 mixed precision with fp32 master copies of the
trainable weights. Per batch: forward pass → cross-entropy →
backpropagate → nudge only the LoRA matrices and head. Each run took
7.2 minutes on a rented L40S GPU (total ~29 min, ~$0.50). Full
provenance per adapter in `distil_models/*/training_meta.json`.

---

## Part 5: Where the results stand (after step 4)

Held-out set: 100 dilemmas x 16 responses the students never saw.

| Judge copy | Pearson | Spearman | MAE | Tau | Floor Pearson | Floor tau |
|---|---|---|---|---|---|---|
| Utilitarian | 0.836 | 0.785 | 0.95 | 0.397 | 0.757 | 0.283 |
| Deontological | 0.777 | 0.788 | 1.19 | 0.317 | 0.593 | 0.184 |
| Ubuntu | 0.826 | 0.822 | 1.09 | 0.440 | 0.679 | 0.327 |
| Utilitarian (regression twin) | 0.796 | 0.738 | 1.11 | 0.341 | — | — |

Readings:

- **All three clear the floor on every metric** — they learned more than
  vocabulary statistics.
- **Ubuntu is the upset:** the floor's weak link (and the pilot's
  expected failure) is the best ranker of the three. "Ubuntu is hard to
  imitate" was really "Ubuntu is hard to imitate with word counts."
- **The tau column (0.32-0.44) is the honest one:** ordering 16 sibling
  responses is much harder than tracking scores corpus-wide, and the
  students will shuffle close calls. How much that matters in practice
  is exactly what the step-5 replay measures, and how much of it is
  irreducible teacher noise is what the step-7 ceiling measures.
- None of this yet says the copies *understand* their frameworks. That
  is the step-6 axiom exam, the test that counts.

### The step-5 replay (`replay_distil.py`, 25 Aug)

Swapping the student judges into the full pipeline on the 100 held-out
dilemmas:

- **Individual winners shuffle** (the tau prediction come true): on the
  three multi-judge rules the student's winner set shares a response
  with the teacher's in only 43-59% of dilemmas (86% for the
  single-judge baseline, where errors don't compound).
- **Recommended actions survive**: winner sets share a recommendation
  label in 91-99% of dilemmas. Different text, same advice.
- **The headline science survives**: the student pipeline's internal
  rule-vs-rule divergence table is nearly identical to the teacher's
  (e.g. unanimity 72% vs 71%; EC-vs-maximin strict divergence 15% vs
  18%). A researcher running the whole study on the copies would draw
  the same conclusions. The floor fails this test badly (unanimity 56%,
  divergences inflated ~1.7x), which makes structure-preservation a
  second certification layer that correlation alone misses.

### The step-6 axiom exam (`axiom_distil.py`, 25 Aug)

The test that counts, and the results are two-sided.

**Main set (45 pairs, 75 predictions):** the students show the real
diagonal pattern - 87% / 93% / 93% (Ut/De/Ub) on their own frameworks'
axioms, versus the teacher's 99% and the floor's scrambled 60%. Overall
they match 65/75 predictions, coincidentally the teacher's own average
(86.9%). This is far above chance and far above the floor: the copies
learned framework-specific moral direction, not just style.

**Held-out pairs (6, never used in prompt iteration): 2/6**, versus the
teacher's 90%. And the failure has a mechanism, not just bad luck: the
students' score margins are compressed roughly fourfold everywhere
(mean |a-b| of 1.5 points on the main set, 0.9 held-out, versus the
teacher's 5.6 and 4.8). On two held-out pairs where the teacher is
maximally decisive (10 vs 2), the student scores 6.6 vs 7.3 - mushy and
pointing the wrong way. Axiom responses are one or two sentences; the
students trained on multi-paragraph responses, and their verdicts go
soft on inputs that short.

**Reading:** the copies are genuinely framework-shaped but not yet
certifiable - their preferences are weak-signal exactly where the
teacher is most confident, and 6 held-out pairs is too few to bound how
bad this is (the honest fix: write more held-out axiom pairs). The
"correlation is not sufficient evidence" thesis is now demonstrated in
a subtler form than the pilot's: these students pass correlation AND
ranking AND replay, and still stumble on the strictest test.

### The step-7 ceiling (`ceiling_distil.py`, 25 Aug)

Re-scored 13 whole held-out dilemmas (208 responses, 624 calls, zero
failures) with the real GPT judges and compared to the original scores.

**The teacher agrees with itself almost perfectly:** Pearson ~0.99 on
all three judges, the identical integer score 87-92% of the time, MAE
~0.1, and within-dilemma tau of 0.93 / 0.87 / 0.84 (Ut/De/Ub). At
temperature 0.1 the teacher is near-deterministic.

The full ladder on identical data (utilitarian, within-dilemma tau):
floor 0.28 -> student 0.40 -> ceiling 0.93. So the students capture
LESS THAN HALF of the achievable ranking fidelity, and the generous
reading of their tau ("maybe the teacher is noisy too") is ruled out.

The one-sentence version for the write-up: a headline Pearson of 0.84 -
which standard practice would report as a successful distillation -
coexists with capturing under half of the teacher's reproducible
within-dilemma ranking behaviour and a 2/6 result on prompt-untouched
axiom pairs. Correlation, ranking, replay, exam, floor and ceiling
together give the full picture; no single number does.

(Footnote: on this 13-dilemma subset the students' Pearson reads
0.69-0.79 versus 0.78-0.84 on the full 100 - small-subset variance;
cite the full-set numbers as primary.)
