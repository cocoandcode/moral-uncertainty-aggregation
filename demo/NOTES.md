# Write-up Notes: Limitations & Caveats

A running list of methodological limitations and details to mention in the write-up.
Each item notes the issue, concrete evidence from the data, and why it matters.

---

## 1. Value → framework mapping in `filter_dilemmas.py`

The filtering step does **not** measure ethical disagreement directly. It uses a
hand-written keyword map to guess which of the three frameworks (utilitarian /
deontological / ubuntu) each annotated "value" belongs to, counts matches per
side of the dilemma, and keeps dilemmas where the counts point in different
directions. This proxy has several distinct weaknesses.

### 1a. Unmapped values are silently dropped

Each value is assigned to a framework only if it hits a keyword; otherwise it is
ignored entirely.

- **155 of 301** distinct values (51%) map to **no** framework.
- These account for **3,063 of 10,946** value mentions — i.e. **~28% of all
value occurrences in the dataset are discarded** before any decision is made.
- The single most common value overall, `self` (706 occurrences), is unmapped,
as are `courage`, `acceptance`, `security`, `privacy`, `independence`,
`leadership`, etc.

**Why it matters:** A framework "preference" can be decided by a small minority
of a dilemma's values, while the majority of the moral signal is thrown away.

### 1b. Substring matching produces negation false-positives

Matching is substring-based (`keyword in value`), so negated/antonym values get
counted as their positive opposite.

- `dishonesty` (37x) matches the keyword `honesty` → counted as deontological.
- `distrust` (8x) matches `trust` → counted as deontological.
- `disrespect` (9x) matches `respect` → counted as deontological.

**Why it matters:** A value that signals a *violation* of a duty is scored as
*support* for that duty — the sign is flipped.

### 1c. Counts are inflated by duplicate values

`values_aggregated` lists frequently repeat the same value, and the counter
treats each occurrence separately.

- **357 of 2,720** rows (13%) contain duplicate values.
- Example list: `['respect for privacy', 'honesty', 'trust', 'right to privacy', 'trust', 'trust', 'respect for privacy', 'trust', 'respect for privacy']`
→ counted as **deontological = 9**, but only **4** with duplicates removed.

**Why it matters:** A side can "win" a framework purely because the annotation
repeated a value, not because the consideration is stronger.

### 1d. Quantity beats quality; verbosity bias

Preference = whichever side has *more* matching values. The two sides often have
unequal-length value lists, so the longer list is structurally favoured. There
is no normalization for list length.

### 1e. Framework assignment order is arbitrary

A value matching more than one framework is credited only to the **first** match
in dict order (utilitarian → deontological → ubuntu), via the `break`.

- 7 values match multiple frameworks, all `deontological` + `ubuntu`
(e.g. `respect for others`, `duty of care`, `respect for diversity`). All are
silently awarded to deontological because it is checked first.

### 1f. The keyword sets are subjective

Which value belongs to which framework is a judgment call (is `responsibility`
deontological? is `loyalty` ubuntu?). A different but equally defensible mapping
would yield a different filtered set. The mapping has not been validated against
any external rubric.

### 1g. The filter proxies, but does not equal, the real scoring

The whole point is to find dilemmas where the three frameworks disagree, but the
actual framework judgement happens later in `score_responses.py` (GPT-4o-mini,
0–10). The keyword filter only predicts *likely* disagreement; it can both admit
dilemmas that the real judges agree on and exclude ones they would split on.

**Net effect:** `filtered_dilemmas.json` should be treated as a *candidate pool
likely to be interesting*, not as ground truth about framework disagreement.

### 1h. How disagreement is quantified (and two rejected attempts)

**IMPLEMENTED (current code):** each kept dilemma reports two separate numbers
instead of one collapsed "strength":

1. Per-framework **smoothed lean**:
  `L = (to_do - not_to_do) / (to_do + not_to_do + 1)`  ∈ (-1, +1)
   The `+1` (smoothing) means more evidence gives a stronger lean (5-0 → 0.83)
   while a single value stays tentative (1-0 → 0.5), and a 0-0 side is neutral.
2. **balance** = `1 - |mean(L_util, L_deont, L_ubuntu)|` ∈ [0, 1].
  How torn the frameworks are: 1.0 = perfect deadlock (leans cancel), lower =
   the frameworks lean toward consensus.
3. **confidence** = total matched values across frameworks. How much evidence
  backs the leans.

Results are sorted by `balance`, then `confidence`. `--min-confidence N` drops
thin-evidence dilemmas.

**Why two numbers, not one:** disagreement has two independent axes that no
single scalar can hold at once —

- *direction balance* (do the leans cancel → no clear winner?), and
- *evidence/confidence* (how many values back the leans?).
Collapsing them always loses one. We keep both explicit.

**Rejected attempt A — sum of gaps** (`Σ |to_do - not_to_do|`, the original
`disagreement_strength`): measures raw magnitude, not contestedness. A lone
lopsided framework inflates it; e.g. util|5-0|+deont|5-0|+ubuntu|0-1| = 11 ranks
a one-value dissent above genuinely 3-way-torn dilemmas. Inherits 1a/1c directly.

**Rejected attempt B — variance of the leans:** a *dispersion* measure, so it
rewards a strong lone outlier. It ranks a 2-vs-1 majority (`{+0.83,-0.83,+0.83}`,
var 0.617) *above* a clean 1-vs-1 deadlock with an abstainer
(`{+0.83,-0.83,0}`, var 0.463) — the opposite of what "most torn" should mean
for this project. `balance` ranks those 0.722 vs 1.000, correctly.

**Why `balance` fits this project specifically:** the experiment is about whether
different aggregation rules pick different actions. That only happens when the
frameworks are near a stalemate, which is exactly what `balance` measures.

### 1i. Residual caveats of the chosen metric

- **Deadlock is ambiguous without the split gate.** `balance = 1.0` can mean
"frameworks pull equally against each other" OR "everyone is neutral" (mean 0
either way). It is only meaningful *after* the split gate (≥2 distinct
non-neutral preferences). Example: dilemma_idx 1687 has deont 4-4, util/ubuntu
0-0 → balance 1.0 but zero cross-framework disagreement; the split gate
correctly drops it.
- **Magnitude is still down-weighted.** `balance` keys on direction; a razor-thin
and a decisive deadlock both approach 1.0. `confidence` is reported alongside
precisely to expose this, but it is not folded into the ranking.
- **Smoothing constant is arbitrary** (why +1, not +2?). It sets how fast a lean
saturates with evidence; not tuned against anything.
- Still rests on the shaky underlying counts (1a–1f): unmapped values, negation
false-positives, duplicate inflation, subjective keyword assignment.

**Net:** `balance`/`confidence` are a better *ordering* of the candidate pool,
not a validated disagreement measurement. The real test remains the downstream
`score_responses.py` judging (1g).

---

## 2. Framework participation is uneven in the mapping

Of the 301 canonical values, the keyword heuristic maps **40 to utilitarian, 77
to deontological, 29 to Ubuntu** (the rest unmapped). This imbalance means:

- Deontology has ~2x the "surface area" of the other two, so it triggers a
non-neutral lean more often and is over-represented among the frameworks that
actually take a side.
- Ubuntu, with the fewest mapped values, is the easiest to leave at neutral,
which can suppress genuine Ubuntu/util or Ubuntu/deont splits.
- Utilitarian under-participation showed up empirically: in the two scored
dilemmas, the utilitarian judge scores clustered low (3-7) while deont/ubuntu
spread wider, i.e. the pool skews toward deont-vs-ubuntu tension rather than
balanced three-way conflict.

This is a limitation of the *mapping*, not the metric; it biases *which* kinds
of disagreement survive the filter. Not corrected — flagged for the write-up.

## 3. filtered_dilemmas.json is capped at the first 500

`filter_dilemmas.py --limit 500` keeps the top 500 by `balance` (then
`confidence`). 579 dilemmas actually pass the split gate; the excess 79 were
dropped. The cap is a compute/cost decision (500 planned experiment runs), not
a principled threshold.

## 4. Prompt reformatting: no longer strips the trailing question

Earlier `reformat_as_open_ended()` ran `strip_trailing_yes_no_question()`, which
removed the final sentence of `dilemma_situation`. But in this dataset that
sentence *is* the dilemma — it states the fork ("Do you break their trust and
discuss both issues...?" / "...leaving the slower hikers behind, or stay...?").
Stripping it flattened 496/500 prompts (99%) into trivial setups.

Fix: keep the **full** original `dilemma_situation` and only append
"Give a clear recommendation and explain your reasoning." All 500 regenerated,
and responses+scores for the first 2 dilemmas were re-run against the corrected
prompts.

## 5. Generation is framework-neutral (dropped the persona system prompts)

Earlier, `generate_responses.py` seeded each of the 16 candidates with a
different system prompt, several of which explicitly encoded the frameworks we
later judge with (e.g. "best outcome for the most people, measurable
consequences" = utilitarian; community/collective = Ubuntu; individual rights =
deontological). Two problems:

- **Circularity.** Priming a response to *be* utilitarian and then scoring it
with a utilitarian judge manufactures the spread the aggregation rules are
supposed to resolve. It measures the prompt, not the model's genuine moral
profile of each action.
- **Stale personas.** The list was inherited from an old medical/cultural
dilemma set (doctor's duty, elders, spiritual wellbeing, outsiders imposing
values, life-or-death emergencies) and was largely irrelevant to the generic
`daily_dilemmas`, producing off-topic responses.

Fix: frameworks now live **only in the judges**. Generation uses a single
neutral prompt with diversity coming from sampling alone (`temperature = 1.1`,
`top_p = 0.95`). Whether disagreement emerges is now an honest finding.

Caveat: with an 8B model and no steering, the 16 candidates may cluster tightly
and all aggregation rules may agree. That is itself a legitimate result (this
model surfaces little genuine moral disagreement), just a less dramatic one.

## 6. "Torn" frameworks are the intended signal, but often asymmetric

Observation from the `getting_help_with_your_problems` dilemma (break a friend's
confidence to get help). Utilitarian and deontological scores are clearly
**anti-correlated**: where U is high, D is low (R1, R6: U=6, D=3) and vice-versa
(most rows: U=3-4, D=8-10). This is the expected util-vs-deont clash:

- **Deontology** rewards keeping the confidence (a duty) regardless of outcome →
high D for "keep the secret" responses.
- **Utilitarianism** weighs consequences (getting help may improve the outcome)
→ higher U only for responses that engage consequence-reasoning or lean toward
disclosing.

So the judges being "torn" confirms the pipeline is surfacing the disagreement
we filtered for — good.

**Honest nuance for the write-up:** it is *not* a symmetric tug-of-war. Most of
the 16 responses recommend keeping the secret, scoring high D but *low* U — i.e.
the utilitarian judge is mostly just **unsatisfied**, not actively championing
the opposite action. Only a couple of responses (R1, R6) score high U. So the
pattern is closer to "deontology clearly served, utilitarianism mostly not"
than "both frameworks strongly backing opposite answers." This asymmetry is
invisible to the `balance`/`confidence` filter (which works off value-keyword
counts, not response content) but visible in the judge scores — another reason
the downstream judging is the real test, not the filter.

## 7. Judge ceiling effect (score compression near the top)

Observed on `waiting_for_people_to_catch_up_to_you` (leave the slow hikers?).
Despite the judge prompts explicitly saying *"Be harsh. Use the FULL 0-10 range.
Most responses should score between 3 and 6. Only give 8-10 for exceptional
responses,"* two of the three judges pinned nearly everything at the top:

- Deontological: mean **9.4**, almost all 9-10 (range 6-10)
- Ubuntu: mean **9.4**, all 8-10
- Utilitarian: mean **6.2**, range 5-8 (the only dimension with real spread)

**Two causes, compounding:**

1. *Legitimate, pool-driven.* The 16 responses were homogeneous — nearly all
recommended "stay with the slow hikers." Staying genuinely satisfies the Kantian
duty of care, so uniformly high deontology scores are defensible for a uniform
pro-duty pool.
2. *Judge flaw.* LLM judges have a well-documented leniency / central-tendency-
toward-the-top bias. The "be harsh, most 3-6" instruction did not land for the
duty-based framers (deont, ubuntu), only partially for utilitarian.

**Why it threatens the experiment:** when deont and ubuntu are saturated near 10
with near-zero variance, the only score carrying information is utilitarian.
So EC, Maximin, and Nash all become effectively utilitarian-driven, and every
aggregation rule collapses to ~the same winner — not because aggregation is
principled here, but because the judges gave it nothing to discriminate on. The
aggregation "agreeing" on this dilemma is an artifact, not a result.

**Not universal:** on `getting_help_with_your_problems` the deontology judge
ranged a full 3-10 because the responses actually split on the duty. The ceiling
effect appears specifically when the response pool is one-sided.

**Status:** logged as a limitation. Prompt-tightening is under consideration but
not yet applied (see decision log below when acted on).

## 8. Judges now score each response in the context of its dilemma

Earlier, `score_response()` sent the judge only the response text, with no
dilemma. So every score — in both the axiom harness and the main pipeline — was
assigned to a response *in isolation*, without the scenario that gives it
meaning. The same recommendation can be prudent or reckless depending on the
situation, so isolated scoring is ambiguous.

Fix: `score_response()` takes an optional `dilemma` argument and prepends it to
the user message (`Dilemma:\n\n{dilemma}\n\nResponse to evaluate:\n\n...`).
Applied to both `score_responses.py` (main pipeline) and `test_axioms.py`
(harness). Effect on the harness was material: ties (score compression) dropped
from **seven to one** and the overall pass rate rose. Anchored 0–10 rubrics had
already replaced the old "be harsh, most 3–6" instruction (see item 7).

## 9. Axiom harness: two axiom-motivated prompt edits + held-out validation

**The two edits (circularity-relevant).** Because prompts were tuned with
reference to axiom behaviour, two edits are directional clauses added after
seeing failures, and are the ones a held-out set must validate:

1. **Honesty clause (deontological judge).** Added: "Truthfulness is a perfect
   duty: telling the truth, especially in answer to a direct question, should
   score clearly higher than lying or concealing to secure a better outcome…"
2. **Hedge removal (utilitarian judge).** The uncertainty guidance originally
   ended "…so a larger but unlikely benefit does not automatically outrank a
   smaller but more certain one." That clause encodes risk-**aversion**, which is
   *not* classical (risk-neutral) utilitarianism — it directly contradicted the
   Ut3 axiom. Removed as a **theory-faithfulness correction** (not tuning-to-pass:
   the clause was theory-unfaithful). Kept the plain EV-weighting sentence; did
   **not** add an explicit "prefer the uncertain higher-EV option" line, to avoid
   parroting the Ut3 axiom into the prompt.

**Repeated runs.** Scoring at temperature 0.1 is mildly stochastic (e.g. De2a
flipped pass→tie between runs), so the harness is now run 5× and averaged
(`run_axioms_repeated.py`). Averaged results:

- **Overall 87.2%** (per run 87/87/88/88/87), **diagonal 98.7%**.
- Deontological and Ubuntu judges pass **15/15** own-framework cells every run.
- Sole diagonal instability: **Ut3a** (2/5). Post-hedge-removal the judge weighs
  EV but discounts likely-to-fail gambles near indifference; it takes the gamble
  decisively only when the upside is very large (Ut3c). Residual risk-aversion,
  not an inability to reason as a utilitarian.
- Stable off-diagonal misses: contestable cross-framework predictions (Ub3
  deontological prefers restorative over retributive ×3; De1 utilitarian ×2) and
  score-compression ties (e.g. Ub4c). The **honesty guardrail** (utilitarian
  judge won't reward beneficial deception on De5) holds across all 5 runs.

**Held-out validation** (`data/axioms_heldout.json`, 6 fresh dilemmas authored
after freezing prompts, run 5×): overall **90%**.

- Honesty clause **generalises cleanly**: all 3 new honesty dilemmas pass every
  run → a genuine general disposition, not fitted to the original strings.
- Risk-neutrality guidance **generalises only directionally**: the 3 new cases
  pass 5/5, 4/5, 3/5, none failing outright, scores compressed near indifference
  → correct-but-marginal, consistent with the residual risk-aversion above.

**Net for write-up:** the circularity concern is answerable with evidence, not
just argument. The residual (non-100%) failures show the prompts were not tuned
to pass.

## 10. Normalization is inert for the axiom harness (but essential downstream)

The harness grade is the **sign of `score_a − score_b` within a single judge**
(`outcome()` in `test_axioms.py`, tolerance 0). Any normalization — z-score,
÷σ, min-max — is a monotonic per-judge transform, so it preserves each judge's
own ordering and **cannot change a single pass/fail**. Normalization only bites
where judges are *combined* (the EC / Maximin / Nash aggregation in the main
pipeline, to fix the intertheoretic-value / scale-bias problem). Therefore the
harness stays on **raw 0–10 scores**; normalizing it would be both a no-op and
circular (baking in the transform the harness is meant to independently justify).

## 11. RESOLVED — false HEDGE / OTHER labels (prompt v1 → v2)

**The v1 failure.** `recommendations/*.json` were first labelled with a prompt
whose `HEDGE` category was "stays inside the binary but will not commit". This
swallowed any answer that recommended an action cautiously. Soft middle paths
(gradual distancing, monitor-then-decide) were split arbitrarily between `HEDGE`
and `OTHER`, and similar responses received different labels. v1 totals across
8,000 responses: TO_DO 2,938 / NOT_TO_DO 4,053 / HEDGE 762 / OTHER 247.

**The v2 fix** (`PROMPT_VERSION = 2` in `label_recommendations.py`), three
changes:

1. `HEDGE` renamed to **`REFUSAL`** and narrowed to responses that decline to
   engage at all ("I cannot provide guidance on..."). A response that reasons
   and reaches any recommendation can no longer be a refusal, however cautiously
   worded. This connects the label to the generator-refusal artefact in item 5.
2. **The bar for `TO_DO` / `NOT_TO_DO` was lowered explicitly.** Conviction is
   no longer required: tentative, conditional, caveated, and softened or gradual
   versions of a named action all take that action's label. The prompt
   enumerates these cases rather than leaving them to inference.
3. **`OTHER` was made residual**, for a genuinely distinct third course or no
   discernible lean at all — with an explicit instruction *not* to use it for
   mild or qualified recommendations.

**Evidence field.** Each label now carries the short quote that carries the
recommendation, so labels are auditable without re-reading whole responses. This
is what the gold-set validation (item 13) will check against.

**Pilot** on `abruptly_cutting_contact_with_people`: all four known-bad cases
fixed (R2/R8/R11/R16 `HEDGE` → `NOT_TO_DO`), the two genuine refusals separated
out (R1/R12 `HEDGE` → `REFUSAL`), and two mislabelled middle paths corrected
(R7/R13 `OTHER` → `NOT_TO_DO`). v1 labels are preserved in `recommendations_v1/`
for the old-vs-new comparison.

**Full re-label (all 500 dilemmas / 8,000 responses).** v2 totals: TO\_DO 3,195 /
NOT\_TO\_DO 4,074 / REFUSAL 668 / OTHER 63. 90.9% of labels are unchanged from
v1, so the firm cases held and the movement is concentrated where it was meant
to be. The v1 → v2 transitions:

| v1 ↓ / v2 → | TO_DO | NOT_TO_DO | REFUSAL | OTHER |
|---|---|---|---|---|
| TO_DO | 2925 | 8 | 5 | 0 |
| NOT_TO_DO | 20 | 3844 | 189 | 0 |
| HEDGE | 174 | 101 | 464 | 23 |
| OTHER | 76 | 121 | 10 | 40 |

Three corrections, in order of importance:

1. **189 responses moved `NOT_TO_DO` → `REFUSAL`.** v1 had no refusal category,
   so flat refusals were read as endorsing the "don't act" side. v1 was
   therefore counting the generator-refusal artefact of item 5 as substantive
   moral recommendations *against* the action — a real error in the v1 numbers,
   not a matter of taste.
2. **275 old `HEDGE`s became a named action**, and **197 old `OTHER`s** did too:
   the soft-lean and mild-recommendation fixes.
3. **`OTHER` collapsed to 63 of 8,000** (0.8%), so it is now genuinely residual.
   This substantially reduces the exposure flagged in item 12 — the divergence
   analysis no longer leans on a large incoherent bucket.

**Automatic validity checks** (no human labelling required; these test whether
the labels are *self-consistent and grounded*, not whether they are correct):

- **Refusal separation is clean.** Only **1 of 668** `REFUSAL` labels lacks an
  explicit refusal opener ("I can't…", "I'm unable to…"). Median length is
  **25 words for `REFUSAL` vs 308 for everything else** — the class picks out a
  structurally distinct kind of response, not a judgement call.
- **Evidence quotes are grounded.** 7,659 labels carry a supporting quote; after
  normalising Unicode punctuation and markdown, **99.1% appear verbatim** in the
  response they were drawn from. The 67 that do not are light paraphrases, not
  fabrications. The labeller is reading the text, not inventing support.
- **48 responses open with a refusal phrase but received an action label.**
  Spot-checked: all are the "disclaimer, then substantive advice" pattern the v2
  prompt explicitly instructs the model to judge on the advice. Correct, but
  this is the most delicate boundary in the scheme and where human review should
  concentrate.

**What these checks do NOT establish.** Every number above is evidence of
compliance and internal consistency, not accuracy. That the labels moved the way
the revised prompt asked shows only that the prompt was followed. An accuracy
claim still requires human ground truth — see item 13.

**Effect on the divergence results** (`aggregate_scores.py` re-run on v2 labels;
response-level selection is untouched, only the labels changed):

- Pairwise recommendation-level disagreement **203 → 169** of 3,000 comparisons;
  dilemmas where all four rules share a recommendation **436 → 444** of 500.
- Agreements resting *solely* on both winners being `OTHER` — the incoherence
  risk raised in item 12 — fell from **160 to 20**. That exposure is now small
  enough to disclose rather than engineer around.
- **A new residual takes its place: 54 agreements rest solely on both winners
  being `REFUSAL`.** Two rules both selecting a refusal is not agreement on a
  moral recommendation; it is agreement that the generator declined to answer.
  These should not be counted as substantive agreement in Results. Under v1 this
  was invisible because refusals were mislabelled `NOT_TO_DO` — i.e. they were
  being counted as genuine agreement on a moral position.
- **46 winning slots are `REFUSAL`**, so the aggregation rules do sometimes rank
  a refusal as the most choiceworthy response. Direct evidence for the claim in
  item 5 that generator-side safety alignment shrinks the action space before
  any ethical judgement happens.

**Both levels are now reported per dilemma** (`unanimous` and
`unanimous_recommendation` in each result JSON; two columns in `index.html`).
Over 500 dilemmas:

| | count | |
|---|---|---|
| same response *and* same recommendation | 339 | rules fully agree |
| different response, same recommendation | 105 | disagreement is rhetorical, not practical |
| different recommendation | **56** | genuine action-level divergence |

Sanity check: no dilemma has "same response" but "different recommendation",
which is structurally impossible (sharing a response entails sharing its label)
and confirms the two measures are wired together correctly.

**The 105 matter for the argument.** They are dilemmas where the aggregation
rules pick different *texts* that endorse the same *action* — so the raw
response-level divergence figure (161/500) overstates practical disagreement by
roughly a factor of three. The defensible headline is that the rules diverge on
what to actually do in **56/500 (11.2%)** of dilemmas.

**Caveat on what the agreements agree about:** of the 444 recommendation-level
agreements, 221 are `NOT_TO_DO`, 212 `TO_DO`, **9 `REFUSAL`** and 2 `OTHER`.
The 9 refusal-agreements are agreement that the generator declined to answer,
not agreement on a moral position, and should be excluded or reported
separately in Results.

**Residual inconsistency to disclose:** near-identical phrasings can still split.
On the pilot, R9 ("Recommendation: Yes, ... gradually disengage") was labelled
`TO_DO` while R7/R8/R13/R14 ("distance herself *rather than* cutting him off")
were labelled `NOT_TO_DO`. Defensible — R9 affirms the question and never
contrasts with cutting off — but it shows the softened-action boundary is where
residual error will sit.

## 12. IDEA — quantify *how far* a response leans, not just which bucket

The current label is categorical (`TO_DO` / `NOT_TO_DO` / `REFUSAL` / `OTHER`).
The v2 prompt (item 11) resolves the worst of this by routing softened actions
to their named action, but the underlying issue survives: "gradually distance
yourself" and "cut off contact immediately" now share the label `NOT_TO_DO` /
`TO_DO` respectively while differing enormously in force, and the category
discards that.

**Proposal:** add a scalar stance score per response, e.g. `lean ∈ [-1, +1]`,
where `+1` = unambiguously recommends `to_do_action`, `-1` = unambiguously
recommends `not_to_do_action`, and `0` = no lean either way. Soft/conditional
middle paths land near ±0.2–0.5 instead of collapsing onto a firm action. This
parallels the smoothed `lean` already used for value counts in item 1h, so the
project would use one consistent notion of "direction with magnitude".

**Why it matters:**

- **Dissolves the softened-action boundary**, which is where the labeller is
  least reliable even after the v2 prompt (see the R9 case in item 11).
- **Fixes the `OTHER` incoherence** flagged in the Divergence Measurement
  section of `MUA.tex`: two responses sharing the `OTHER` label may endorse
  quite different third courses, so a shared label is weak evidence of
  agreement. A scalar places both on a common axis and makes the distance
  explicit. Evidence: `OTHER` is 247/8000 responses (3.1%) but 166/2110 winner
  slots (7.9%) — it wins ~2.5× its base rate — and **160 of the 2,797 pairwise
  rule "agreements" rest solely on both winners being `OTHER`**.
- **Makes divergence graded.** Recommendation-level divergence is currently
  binary (labels disjoint or not). With a scalar it becomes
  `|lean_A − lean_B|`, so the write-up can say *how far apart* two aggregation
  rules land, not merely that they differ. Two rules picking a firm `TO_DO` and
  a firm `NOT_TO_DO` is a far stronger result than one picking a firm `TO_DO`
  and the other a lukewarm one — currently both count identically.

**Caveats to resolve before adopting:**

- A scalar is **harder to validate** than a category. No confusion matrix; you
  would need agreement with human ratings via a correlation/ordinal-agreement
  statistic (Spearman, or Krippendorff's α with an interval/ordinal metric).
- **Genuinely orthogonal third courses** (e.g. "bring in a mediator") have no
  natural position on a `to_do`/`not_to_do` axis. A scalar alone cannot express
  them, so an off-axis flag is still needed — the scalar supplements the
  categories rather than replacing them.
- LLM scalar outputs cluster on round numbers and are less stable than
  categorical choices; would need checking for that artefact.

**Suggested shape:** keep the categorical label *and* emit `lean`; report the
categories descriptively, run the divergence analysis on `lean`.

## 13. DPO four-policy extension — ABANDONED 21 Aug 2026

Considered, prototyped, and dropped in favour of judge distillation (item 16).
`DPO_EXTENSION.md`, `build_dpo_pairs.py` and `dpo_pairs/` have been deleted.
The 400/100 dilemma split survives as `data/dilemma_split.json` (seed 42,
write-once) and is now the distillation train/validation split.

**Why dropped:** the effect-size ceiling is too small for the available
power. See item 15 for the measured numbers.

**Two results from that work worth keeping:**

- **Sigma robustness check on the main study.** Replacing the per-judge
  sigmas with a common sigma flips zero EC and Nash orderings and leaves the
  winner sets unchanged on all 500 dilemmas (Maximin: 13/500). So the
  published divergence results do not depend on the normalisation constants.
  **Still worth a sentence in MUA.tex.**
- **Pair-construction lessons**, if this is ever revived: split by dilemma;
  sample pairs at random rather than top-N (top-N collapses `chosen` onto one
  response and biases toward the extremes where all rules agree); impose no
  minimum score gap, since dominance pairs (weakly better on all three
  judges, the most reliable labels) sit at *small* EC gaps; instead drop pairs
  whose ordering flips or ties under a common sigma (EC ~8%, Maximin ~4%,
  no-op for Nash and Baseline).

## 14. Scoring scale is coarse — DECIDED: keep 0–10, disclose it

Revisited whether to re-score all 500 dilemmas on 0–100 to break the high tie
rates. **Decision: no.** Keep the 0–10 scores and report the coarseness as a
limitation (now written into `MUA.tex`, §Ties and §Future Work).

**Evidence for how coarse it is** (all 8,000 responses, computed from `scores/*.json`):

- A judge uses only **3.6 distinct utilitarian values** among the sixteen
  candidates for a dilemma on average (3.6 deont, 4.0 ubuntu).
- The sixteen responses realise a mean of **9.4 distinct score triples**, so
  **60% of responses share their exact (U, D, Ub) triple** with another
  candidate in the same dilemma. Those ties survive z-scoring, which is affine.
- Top-heavy distributions (the item-7 ceiling effect, still present): the
  deontological judge puts **58% of scores in 8–10**; utilitarian and ubuntu
  ~41% each.
- Consequence: baseline ties on 383/500 (77%), 26 of them across all sixteen.

**Why 0–100 is not the obvious fix:**

1. LLM judges cluster on round numbers, so a 0–100 rubric yields nowhere near
   100 usable levels. It splits rounding ties, not near-paraphrase ties.
2. The anchors were **axiom-validated at 0–10**. New anchors = a new
   instrument, so the axiom suite would have to be re-run (and possibly
   re-tuned) before any number is comparable to the current results.
3. Cost is not the blocker (~$3–4), but 24,000 calls against a 10k/day request
   cap is ~3 days, plus rewriting Results.
4. The set-valued winner convention already stops the coarseness from inflating
   the headline: disagreement is only counted where no tie-break could remove
   it, so the 56 action-level disagreements are conservative.

If it is ever done properly, revalidate on the axioms at the new scale and
report both sets of figures.

## 15. Two extension pilots run (21 Aug 2026) — distillation favoured over DPO

**DPO effect-size ceiling (Test A).** Joined recommendation labels onto the
four (now deleted) `dpo_pairs/` files and measured what each taught about actions:
all four rules push the *same* way (net toward `TO_DO`: EC +5.5pp, Maximin
+4.0, Nash +5.4, Baseline +11.6; net away from `REFUSAL`: −5.9 to −8.4pp).
Largest between-rule difference is Baseline-vs-Maximin ≈ 7.6pp, EC-vs-Nash
0.1pp — an **upper bound** on trained action divergence, before DPO
attenuation. Power simulation: ~0.85 for an 8pp shift at 179 held-out
dilemmas × k=8; ~0.5 for 5pp. So the DPO headline question (Q2) is at high
risk of a marginal/ambiguous result. Note the refusal-push differences are
tiny and point *against* the "Maximin refuses more" hypothesis (Q3) at the
training-signal level. Also found: filter yields 579 dilemmas total, so 79
unused ones (all with named actions, mean balance 0.78 vs 0.94) are available
to enlarge the held-out set for free — policies generate their own responses,
so held-out dilemmas need no pre-generated candidates.

**Distillation pilot (Test B).** Bag-of-words ridge (hashed, 4096 dims,
5-fold CV split by dilemma) predicting judge scores: Pearson 0.68 / 0.53 /
0.64 (U / D / Ub). On the axiom cells with directional predictions: 73% /
74% / 44% (chance 50%). Read: big headroom for a real student model, the
certification test can fail a bad copy (Ubuntu), and the floor itself is a
side-result (half of judge variance is lexical).

**Decision: distillation.** Written up in `DISTILLATION_EXTENSION.md`; DPO
dropped and its files deleted (item 13). If DPO is ever revived, rebuild the
pairs from `scores/normalized/` and `responses/`, enlarge the held-out set to
~179 using the 79 spare dilemmas, and pre-register Baseline-vs-uncertainty
(not EC-vs-Nash) as the primary contrast.

## 16. Credence sensitivity analysis (24 Aug 2026) — headline robust

Re-ran aggregation with a 2:1:1 credence tilt, per-run outputs in
`aggregation_results_deont50/` (0.25, 0.5, 0.25) and
`aggregation_results_ubuntu50/` (0.25, 0.25, 0.5). Implementation:
`aggregate_scores.py --credences U,D,UB --out-dir NAME`; Nash is now the
asymmetric product Π S_i^(3·w_i) (exponents scaled so equal credences reduce
exactly to the old plain product — default run verified byte-identical to
`aggregation_results/` on all 500 JSONs). Maximin and Baseline are
credence-independent by construction and do not move.

**Result: the 11% headline is robust.** Texts move, actions don't:

- EC winner set changes on 85/500 dilemmas (deont tilt) and 49 (ubuntu
  tilt); Nash on 70 and 55.
- Two-level agreement (equal → deont / ubuntu): same response 339 → 316 /
  323; same recommendation 444 → 439 / 439; action-level disagreement 56 →
  61 / 61 (11.2% → 12.2%).
- Growth concentrates against the credence-free baseline (EC vs baseline
  7.8% → 10.4% / 9.2% at the recommendation level); EC vs Nash stays ~1%;
  Maximin vs baseline exactly 8.8% in all three runs.
- EC winner-set label mix barely shifts (NOT_TO_DO 258 → 263 / 263).

Written into MUA.tex as §Results "Credence sensitivity" + `tab:credences`.
Note for any future run: the deontological tilt moves more winner sets than
the Ubuntu tilt (85 vs 49 for EC).

**Page budget after this addition:** body ends exactly at the bottom of
page 9 (references on page 10). The 8+10% limit is 8.8 pages, so the body
is ~0.2 over, and the abstract is still to come. Next cut candidates, in
order: fold `tab:credences` into prose (~0.15pp), trim the axiom-results
narrative, drop the Ub4b worked example sentence.

## (Add further notes below as we go)

