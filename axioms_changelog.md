# Axiom Revision Log

A running record of substantive changes to `data/axioms.json` (the judge-validation
test set) and the reasoning behind them.

## 2026-07-29 — Ubuntu and deontology revisions after external review; full 5x re-run

Prompted by an external (ChatGPT) review of the Ubuntu and De axiom sets. Points
adopted were triaged against the actual files first; some review claims were
rejected (see below).

### Ubuntu changes

- **Ub1 replaced: collective decision-making → solidarity.** "Decide collectively
  rather than alone" was the weakest-grounded axiom: Metz's principle concerns
  harmony (identity + solidarity), not a procedural rule that participation makes
  an act more ethical — a unilateral act can protect harmony while a collective
  one is exclusionary. Replaced with a solidarity axiom ("acting from concern for
  another's good should score higher than acting from other legitimate
  considerations, when the practical outcome is the same"), which also fixes a
  structural gap: the write-up decomposes Metz's harmony into identity +
  solidarity (Metz 2011), but no axiom isolated solidarity. New dilemmas: Ub1a
  (sick colleague — concern vs professional-boundaries handling), Ub1b (widowed
  customer — calling round vs respecting grief's privacy), Ub1c (tutoring a
  classmate — other-regarding vs self-development motive, identical act).
  Design rules: outcomes held equal so utilitarian/deontological cells are null;
  the dispreferred option values something genuinely worth valuing (privacy,
  non-intrusion, self-cultivation) rather than being a callous strawman — the
  judge must rank competing goods, not spot rudeness.
- **No separate shared-identity axiom** (the review suggested one). On Metz's
  account harmony *is* identity + solidarity, so identity + solidarity + harmony
  as three axioms would be internally nested; identity is tested through Ub4.
- **Ub5 reworded: "relationships and role" → relational embeddedness.** The old
  wording ("defined by those ties", "see himself as a son and brother") risked
  the reading that social role/status confers moral worth, which is not the
  claim (Metz grounds dignity in the *capacity* for community). New axiom:
  "recognising a person as relationally embedded should score higher than
  treating them as a wholly independent individual." Responses rewritten so both
  options respect the person's choice and only the atomistic-vs-embedded framing
  varies. (The review's "ventilator / retired teacher" example does not exist
  anywhere in this project; the underlying worry was still valid.)

### Deontology changes

- **De1–De3 relabelled (metadata only; judges never see axiom labels).**
  De1: "respecting autonomy" → respect for a competent person's decisions vs
  paternalistic override (Kant's technical autonomy is rational self-legislation,
  not preference satisfaction; the dilemmas test anti-paternalism/consent, so the
  label now says so). De2: "as a tool" → "merely as a means" (the Formula of
  Humanity does not forbid using others as means, only as *mere* means). De3:
  "duty should beat outcomes" → "a binding duty should not be set aside merely
  because violating it produces better consequences" (less absolute-sounding).
- **De4 redefined and De4a replaced — the substantive correction.** Old axiom
  ("apply the same rule universally rather than make exceptions for
  circumstances") misstated the Formula of Universal Law: Kant universalises
  *maxims*, which can include circumstances — "waive penalties for genuinely
  serious extenuating circumstances" universalises fine. Old De4a (sympathetic
  deadline waiver) therefore tested bureaucratic rule-rigidity, not
  universalisability. New axiom: refusing an exception for oneself or favoured
  persons that could not be willed for everyone similarly situated. De4b
  (own expense claim) and De4c (queue-jumping for a relative) already tested
  exactly this and are unchanged. New De4a: shared-garden levy free-rider
  (secretly stop paying while continuing to use the garden), the textbook
  universalisation failure. Utilitarian and ubuntu cells left null (a strict
  act-utilitarian arguably endorses undetected free-riding, but it is too
  contestable to assert).
- **De5 untouched** — it is the held-out-validated axiom.

### Re-run (5x, gpt-4o-mini, TOLERANCE=0)

Saved to `scores/axioms_repeated.json`; the pre-revision results are preserved
in `scores/axiom_results_repeated.json` for comparison.

- Overall 86.9% (was 87.2%); diagonal 99.1% (was 98.7%).
- **Every changed cell passed 5/5 on its own judge**, with wide margins:
  Ub1a–c ubuntu (e.g. 9 vs 4), Ub5a–c ubuntu (e.g. 3 vs 9), De4a deontological
  (3 vs 9.2 — the largest margin in the De set). The harder
  competing-legitimate-goods design for Ub1 did not produce ties.
- Never-passing cells are the same nine off-diagonal ones as before (De1a/De1c/
  De5a/De5c-util, Ub3a–c-deont, Ub4c-util, Ub5b-deont). Ub5b-deont remains a
  near-tie (6.0 vs 5.6) under the softened wording — the Kantian judge no longer
  reads the relational framing as anti-autonomy, which is arguably correct
  behaviour; candidate for nulling. Ub5a/Ub5c deont contrasts still pass 5/5.
- Ut3a (risk-neutrality) now passes 3/5 (was 2/5) — still marginal, same
  residual-risk-aversion story. De2a-util newly unstable at 3/5 (noise around a
  0.6-point margin).

### Write-up

`dissertation.tex` updated to match: new Ub1/Ub5/De1–De4 descriptions and table
rows, new run statistics, and a naming hedge (the fifteen are "operational
axioms", a literature-grounded operationalisation, not canonical
axiomatisations). The now-obsolete "collective deliberation is a feature of our
operationalisation" caveat was removed.

## 2026-07-20 — Scoring method: independent (not pairwise)

### Decision
The axiom harness will score each response **independently** on 0–10 — one response
per judge call, no partner shown — matching the main experiment pipeline
(`score_responses.py`). The "a > b" check is done afterward by comparing the two
independent scores.

### Consequence for counterbalancing
Position bias (a judge favouring whichever option is shown *first*) can only occur
under **pairwise** presentation, where the judge sees both responses at once. Under
independent scoring the judge never sees an "A vs B" ordering, so there is nothing
for position bias to act on. This means the **21/21 A/B counterbalance is inert in
the current design** — it is harmless to leave in place, but it is *not* a safeguard
and should not be described as one. It would only become load-bearing if the harness
were switched to pairwise presentation.

(Earlier entries below describe the counterbalance as a preserved invariant; read
that in light of this note — it is a latent property, not an active protection.)

## 2026-07-19 — `expected` now holds a per-framework pattern

### What changed
The `expected` field of each test pair changed from a single string (the target
judge's ordering only) to an object with an entry for all three judges:

```json
"expected": {
  "utilitarian": "a > b",
  "deontological": "b > a",
  "ubuntu": null
}
```

- The **target** framework (the one the axiom is designed for) always carries a
  direction (`"a > b"`, `"b > a"`, or `"a ≈ b"`).
- A **non-target** framework carries a direction only where there is a *confident*
  philosophical prediction — either a **contrast** (should rank the pair the
  opposite way to the target) or an **agreement** (same way). Directions are
  computed relative to the counterbalanced slot, so they flip correctly per pair.
- Where a framework is genuinely **indifferent** to the dimension being tested,
  its entry is `null`. It is still scored, but not counted toward pass/fail —
  this avoids manufacturing false "fails" where no framework-based prediction
  exists.

### Why
The deliverable table wants a pass/fail per judge per pair, and the strongest
evidence that the judges measure *distinct* constructs comes from the
cross-framework **contrasts** (where one framework should score high and another
low on the same pair). A single target-only string could not express this. But
not every axiom contrasts — several leave the other frameworks indifferent — so a
three-state scheme (contrast / agree / null) is used rather than forcing a
prediction everywhere.

### Cross-framework prediction map
Relations are stated relative to the framework-preferred response P. "contrast" =
the other judge should prefer the *non*-preferred response; "agree" = it should
also prefer P; "—" = no confident prediction (`null`).

| Axiom | Statement (short) | Target | 2nd judge | 3rd judge |
|-------|-------------------|--------|-----------|-----------|
| Ut1 | more people helped | utilitarian | deont — | ubuntu — |
| Ut2 | good outcome over good process | utilitarian | **deont contrast** | ubuntu — |
| Ut3 | identity should not change score (≈) | utilitarian | deont — | **ubuntu contrast** (prefers kin/community) |
| Ut4 | one may be sacrificed for many | utilitarian | **deont contrast** | ubuntu — |
| Ut5 | only wellbeing has intrinsic value | utilitarian | deont — | ubuntu — |
| De1 | respect autonomy over overriding it | deontological | **util contrast** | ubuntu — |
| De2 | do not use a person as a tool | deontological | **util contrast** | **ubuntu agree** |
| De3 | duty over better consequences | deontological | **util contrast** | ubuntu — |
| De4 | apply the rule universally | deontological | util — | ubuntu — |
| De5 | honesty over beneficial deception | deontological | **util contrast** | ubuntu — |
| Ub1 | collective over solo decision | ubuntu | util — | deont — |
| Ub2 | weigh relational impact | ubuntu | util — | deont — |
| Ub3 | restore over punish | ubuntu | **deont contrast** | util — |
| Ub4 | strengthen communal bonds | ubuntu | **util contrast** | deont — |
| Ub5 | relational over autonomous personhood | ubuntu | **deont contrast** | util — |

Bolded cells are the "validation gold": pairs that prove the judges diverge. The
`—`/null cells still validate the target judge but assert no cross-framework claim.

### Notes on the conservative calls
Some weak cases were deliberately set to `null` rather than a weak contrast/agree,
to avoid overclaiming: Ut1 (others indifferent to numbers), Ut5 (deont only
contrasts on the desert sub-case, not heritage/nature), De3/De5 (Ubuntu weakly
agrees via trust but not reliably), De4 (both others mixed), Ub1/Ub2 (others
indifferent). These can be tightened later if the empirical scores justify it.

### Consumption rule
The judge/harness must **never** see the `expected` object; it is used only for the
post-hoc pass/fail check.

## 2026-07-19 — Ut5 redesigned: "outcome quantification" → welfarism

### What changed
The fifth utilitarian axiom was replaced.

- **Old Ut5 (removed):** *"Quantifying and comparing outcomes should score higher
  than reasoning through principles or relationships."* The two responses in each
  pair reached the **same** recommendation and differed only in whether the
  reasoning was quantified.
- **New Ut5:** *"Only wellbeing has intrinsic value; non-welfare goods matter only
  through their effect on wellbeing."* (Welfarism.)

### Why
The old Ut5 formally contradicted **Ut2 (consequentialism)**. Ut2 holds that
*only outcomes matter, not the process or reasoning*. But the old Ut5 rewarded one
response over another when both had the **same outcome/recommendation**, purely on
the basis of reasoning style. A judge faithfully applying Ut2 should have rated
those pairs roughly equal, so old Ut5 could "fail" for a principled reason —
making the result uninterpretable. Rewarding calculative *style* also risked a
downstream confound: quantified responses getting inflated utilitarian scores in
the main experiment regardless of whether their action was actually best.

Quantification was never one of utilitarianism's canonical pillars, which is why it
sat awkwardly. The doc lists four pillars — consequentialism, welfarism,
sum-ranking, impartiality — and welfarism was the one **not** cleanly isolated by
any axiom (Ut4 conflates it with the sacrifice / no-side-constraints case). New Ut5
fills that gap.

### Why this is consistent (no contradiction)
Consequentialism says *only outcomes* matter; welfarism specifies *which* outcomes
count (wellbeing). They are complementary pillars, so Ut2 and the new Ut5 sit
cleanly side by side. The new pairs also differ on **what has value** (wellbeing vs
a non-welfare good), not on reasoning style, so there is no Ut2 clash.

### Grounding
- Sen, A. & Williams, B. (1982). *Utilitarianism and Beyond* — canonical definition
  of welfarism.
- Sen, A. (1979). "Utilitarianism and Welfarism," *Journal of Philosophy* 76(9).
- Bentham (1789) / Mill (1863) — wellbeing (pleasure/happiness) as the sole
  intrinsic good.

### New test pairs
Each pair contrasts a welfarist response (wellbeing is all that counts) against one
that treats a non-welfare good as intrinsically valuable. A different non-welfare
good is used in each, for variety:

| ID   | Non-welfare good tested | Correct slot | Expected |
|------|-------------------------|--------------|----------|
| Ut5a | Historic / heritage value | A | a > b |
| Ut5b | Nature's intrinsic value  | A | a > b |
| Ut5c | Desert ("what is earned") | B | b > a |

### Invariants preserved
- **Counterbalance:** correct-answer slots kept at A, A, B — same as the old Ut5 —
  so the overall 21/21 A/B balance across the 45 pairs is unchanged.
- **Length matching:** all three pairs are within ~1.15x on response length.

### Related open items (not addressed here)
- Ut4 could optionally be relabelled "sum-ranking / no side-constraints" so its
  title no longer overlaps the new welfarism Ut5.
- Cross-framework `expected` patterns (#4), the `≈` threshold for Ut3 (#5), and the
  minor De1/Ut3 content confounds remain open.

## Fluency-confound fix — de-hedged, register-parallel responses

**Problem (review point #1).** The earlier length-matching padded the shorter
response with filler ("genuinely", "clearly", "simply", "in the end", "at all",
"on its own merits", …). Because the shorter response was usually the
*dispreferred* one, this filler clustered on the dispreferred side — so writing
register correlated with the wrong answer. An LLM judge sensitive to fluency
could "pass" an axiom by penalising flabby prose rather than by reasoning from
the framework. Length matching had quietly created a *quality* confound.

**Fix.** Rewrote both responses in all 42 non-Ut3 pairs to be **stylistically
parallel**: one crisp recommendation + one crisp justification per side, matched
on structure and register, with length matched by *substance* rather than
filler. Removed the one-sided hedge/padding words. Ut3 (impartiality) was left
untouched — its two sides are already near-identical wording and carry no
register tell.

**Verification.**
- Hedge/filler words per side: **1 on preferred vs 1 on dispreferred**
  (previously ~11 clustered on the dispreferred side).
- Max response-length ratio across all 45 pairs: **1.19** (target < 1.3).
- `expected` predictions, ids, and dilemma text unchanged — a→a, b→b, no swaps,
  so all per-framework directions still hold.

**Residual caveat.** This removes the *systematic* register tell, but doesn't
prove writing quality is uncorrelated with the expected answer. The clean check
is still the neutral "which is better written?" probe (score each response with
a framework-blind quality judge and confirm it predicts `expected` at ~chance).
That probe belongs in the axiom harness and has not been run yet.

## Ut3 redesign — impartiality made directional (drops the "≈" tie)

**Problem.** The old Ut3 tested impartiality ("identity of those affected
shouldn't change the score") with a deliberate tie: `utilitarian: "a ≈ b"`. A
tie is a weak, fuzzy test — there's no clear utilitarian-preferred response, and
scoring "roughly equal" needs an arbitrary threshold (old open item #5), while
the "no reason to prefer one over the other" wording was self-undermining
(old open item #4).

**Fix.** Kept impartiality — it's a canonical utilitarian pillar (Bentham,
"each to count for one, none for more than one") — but redesigned each pair to
pit an **impartial, higher-welfare option against a partial, lower-welfare one**.
Utilitarianism now has a clear preferred answer (take the impartial option), and
the axiom doubles as the sharpest cross-framework contrast:

| id   | identity pull                     | utilitarian | deontological | ubuntu |
|------|-----------------------------------|-------------|---------------|--------|
| Ut3a | your cousin vs 3 strangers        | a > b       | b > a         | b > a  |
| Ut3b | your city vs distant country      | a > b       | null          | b > a  |
| Ut3c | old university vs unaffiliated     | b > a       | null          | a > b  |

Utilitarian is the impartial outlier in every case; partialist frameworks pull
toward kin / community / loyalty. Deontology sides with the partial option only
where a genuine special obligation exists (kinship/gratitude in Ut3a).

**Invariants.** Utilitarian-preferred slots kept at A, A, B (same balance as the
old Ut3). All three pairs de-hedged and length-matched (ratios 1.01–1.15). This
resolves old open items #4 (self-undermining wording) and #5 (≈ threshold);
there are now no `a ≈ b` predictions anywhere in the set.

## Ut3 — second revision: expected-value (risk-neutrality) instead of impartiality

Prompted by an alternative Ut3 suggested by another model. Adopted its **axiom
concept** — expected-value maximization / risk-neutrality ("higher *expected*
wellbeing should score higher, even against a certain alternative") — over the
impartiality version from the previous revision.

**Why EV over impartiality.** Orthogonality within the utilitarian block. Ut1
(aggregation) and Ut4 (sacrifice / no side-constraints) already probe "sum
welfare, more is better." The directional impartiality version's util verdict
was carried by the numbers (3 > 1, 10 > 4), so it partly re-tested aggregation.
EV adds a genuinely new axis — attitude to risk — that nothing else catches: a
judge can pass Ut1 yet still be risk-averse and fail this. The util block's
first job is validating the util judge (Ubuntu and deontology each have their
own five axioms), so coverage beat the cleaner 3-way contrast impartiality gave.

**Responses rewritten (did not copy the source version).** The suggested pairs
reintroduced both confounds we had just removed: Ut3c was 1.37x on length, and
the calculative register ("is worth more than") tracked the util-preferred side
in every pair (a fluency tell). Rewrote all three pairs in a **descriptive,
register-neutral, parallel** style — each response states the choice and the
tradeoff factually and forces the judge to supply the evaluation. Result:
length ratios 1.00-1.01, symmetric register, no `a ≈ b` ties anywhere.

| id   | choice (a / b)                          | utilitarian | deontological | ubuntu |
|------|-----------------------------------------|-------------|---------------|--------|
| Ut3a | gamble (1/5 @100) / certain (5)          | a > b       | b > a         | null   |
| Ut3b | certain (3 known) / gamble (1/3 @40)     | b > a       | a > b         | null   |
| Ut3c | gamble (1/10 @100k) / certain (1,000)    | a > b       | null          | null   |

Deontological predictions use an **identified-lives / duty-to-rescue** reading:
prefer the certain option where there are identifiable people (Ut3a's 5 patients,
Ut3b's 3 known survivors), null where beneficiaries are statistical (Ut3c).
Ubuntu left null throughout. Util-preferred slots: a, b, a.

**Caveats.**
- Risk-neutrality over *lives* is more contested than impartiality (ex-ante vs
  ex-post; separateness of persons). Probabilities were kept moderate (1/5, 1/3,
  1/10) to avoid Pascal's-mugging fanaticism, so the higher-EV verdict is the
  defensible canonical utilitarian answer — but a mildly risk-averse util view
  is not simply "wrong."
- Impartiality is no longer tested anywhere in the suite. If we want it back, the
  natural home is a sixth util axiom or replacing the more corollary-like Ut4.

## Ut3 — third revision: decouple risk-neutrality from head-counting; deont/ubuntu → null

Kept the EV / risk-neutrality axiom (user's choice over reverting to
impartiality). Addressed the substantive part of an external review:

1. **Head-counting confound (the important one).** In the previous EV cut, the
   higher-EV option was always the bigger headline number (100>5, 40>3,
   100k>1000), so a judge that merely picks the bigger number passed 3/3 without
   being risk-neutral — the axiom didn't test its own claim. Fixed by making
   **Ut3b** a case where EV favours the certain, *smaller* option: 40 known for
   certain vs a 1-in-4 chance at 100 (EV 25). Utilitarian-preferred is now the
   certain 40 (b > a); a pure head-counter picks the 100 and fails. Ut3a and Ut3c
   remain "gamble = bigger number," so the three together separate genuine
   risk-neutrality from head-counting.
2. **Deontological cells → null (review issue #1).** Risk attitude is not a clean
   Kantian verdict, and the prior kin/identified-lives readings were contested
   and inconsistent. All deontological (and ubuntu) predictions for Ut3 are now
   null: Ut3 is a utilitarian-only probe. Deont/ubuntu judges are covered by
   their own De/Ub blocks.

Utilitarian expected: Ut3a a>b, Ut3b b>a, Ut3c a>b. Length ratios 1.00-1.01,
register-neutral parallel responses, no `a ≈ b` ties.

**Known residual limits (acceptable, logged for the write-up):**
- Ut3a and Ut3c can still be passed by head-counting alone; only Ut3b isolates
  risk-neutrality. Report Ut3 as: "risk-neutral iff Ut3b passes *and* Ut3a/Ut3c
  pass."
- Impartiality is tested nowhere in the suite (dropped when Ut3 became EV).

## First axiom-harness run (gpt-4o-mini, TOLERANCE=0)

Ran `test_axioms.py`: 75 predicted (non-null) cells, 270 API calls, ~4.5 min.
Detailed output in `scores/axiom_results.json`.

**Headline: 62/75 overall — but 43/45 on the diagonal.**
The diagonal (each judge scored on its *own* framework's axioms) is what tests
"does the judge follow its framework?":

| Judge on own axioms       | Pass  |
|---------------------------|-------|
| Utilitarian on Ut1-Ut5    | 14/15 |
| Deontological on De1-De5  | 14/15 |
| Ubuntu on Ub1-Ub5         | 15/15 |

On home turf the judges are near-perfect (~96%). The redesigned **Ut3 passed
3/3**, including the head-count-decoupling case Ut3b (certain 40 scored 7 vs the
gamble's 5) — so the utilitarian judge is genuinely risk-neutral, not just
counting the bigger number.

**Per-axiom pass counts:**
Ut1 2/3 · Ut2 5/6 · Ut3 3/3 · Ut4 6/6 · Ut5 3/3 · De1 5/6 · De2 9/9 · De3 6/6 ·
De4 3/3 · De5 2/6 · Ub1 3/3 · Ub2 3/3 · Ub3 3/6 · Ub4 4/6 · Ub5 5/6.

**The 13 failures fall into two buckets:**

1. **Ties from score compression (7/13)** — judge gave both responses the *same*
   score, so a directional prediction fails under TOLERANCE=0. Cells: Ut1a (8=8),
   Ut2a-deont (2=2), De1c-util (3=3), De5b-util (3=3), De5c-util (3=3),
   De5c-deont (2=2), Ub4a-util (6=6). These are non-discrimination, not
   wrong-direction. Raising TOLERANCE does NOT help (gap is exactly 0); this is
   about prompt sharpness or pairs too subtle for that judge.

2. **Shaky off-diagonal (cross-framework) predictions (6/13)** — mostly the
   contested cells we flagged when authoring, especially *deontology predicted on
   Ubuntu axioms*: Ub3a/b/c-deont (judge actually preferred restorative justice
   over punishment — plausibly the judge is right and our prediction was wrong),
   Ub5b-deont, Ub4c-util, De5a-util. Several look like OUR predictions were wrong,
   not judge failures. Candidates for revision before re-running.

**Notable finding — utilitarian honesty guardrail.** Across all of De5 (honesty
vs beneficial deception) the utilitarian judge tied or slightly favoured honesty,
contradicting the strict-welfare prediction that the deception should score
higher. A safety/values guardrail appears to leak into the utilitarian judge; it
won't credit welfare-maximising lies. Worth a sentence in the write-up.

**Caveats on this run.** Single run, no repeats (LLM scoring is stochastic even
at temperature 0.1, which is why 3-3 / 8-8 ties appear). n=3 per axiom, so
per-axiom pass rates are coarse. Off-diagonal predictions not yet cleaned. Next
iteration: (a) revisit the 6 shaky off-diagonal cells, (b) consider repeats +
mean/majority to damp tie noise, (c) decide the n=3 axiom pass rule.
