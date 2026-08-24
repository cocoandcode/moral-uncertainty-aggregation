# Distilling the judges into small open models

Status: not started. The DPO extension was prototyped and dropped
(`NOTES.md` items 13 and 15); this is the replacement.

## The plan in plain words

The three framework judges (utilitarian, deontological, Ubuntu) are prompts
sent to `gpt-4o-mini`. Train a small open model to imitate each one. The
training data already exists: 8,000 responses, each carrying the three scores
the judges gave it (`scores/*.json`, dilemma and response text included).

Then give each copy two tests:

1. **Score matching.** On dilemmas held out of training, does the copy give
   roughly the scores the original would? Easy to pass, and not enough.
2. **The axiom exam.** The 45 + 6 hand-built pairs in `data/axioms.json` /
   `data/axioms_heldout.json`, where the right answer is known (a utilitarian
   judge must prefer helping 200 people over helping 30). This is the test
   that counts.

Why test 1 is not enough: on ordinary responses, score is entangled with
style. Response length alone predicts 31% of the utilitarian judge's score
variance, so a copy can match scores well by learning "longer and more
thorough scores higher" while knowing nothing about utilitarianism. The axiom
pairs are written so both sides have the same length and style and differ
only in the morally relevant fact, so style-learning scores at chance there.
The pilot proved this failure is real: a crude Ubuntu copy matched scores at
0.64 correlation but scored 44% (chance) on the axioms.

Every outcome is worth writing up. Copies pass: you release the first
axiom-certified open moral judges. Copies match scores but fail axioms:
you've shown the standard way of validating distilled judges (correlation
alone) is broken. Either way there is a result, which is why this beat DPO.

## Fixed decisions

- **Base model: `Qwen2.5-1.5B-Instruct`** (decided 24 Aug 2026). Apache 2.0,
  so the released judges carry no licence strings, which matters for a
  community artifact; also stronger than Llama-3.2-1B at this scale, and
  independence from the `llama3.1:8b` generator avoids any family-affinity
  confound. **Three separate LoRA adapters** on this one base, same config,
  learning rate, epochs and seed for all three; only the score column
  differs.
- **Input:** dilemma + response, same format the teacher saw
  (`score_responses.py`).
- **Output:** a scalar score via a regression or classification head
  (compare both on one judge at step 2). Not a text-generating model.
- **Split: `data/dilemma_split.json`** (400 train / 100 held-out dilemmas,
  seed 42, already frozen). Split by dilemma, never by response: the 16
  responses to one dilemma are correlated, so splitting by response leaks
  and inflates every number.

## How the copies are graded (decide now, don't change later)

Each result needs a floor and a ceiling next to it, or it can't be read:

- **Floor:** a bag-of-words ridge regression (pilot, already run):
  Pearson 0.68 / 0.53 / 0.64 (Ut / De / Ub), axiom cells 73% / 74% / 44%.
  A real model must beat this or it has learned nothing beyond word counts.
- **Ceiling:** re-score ~200 held-out responses with `gpt-4o-mini` and
  measure how well the teacher agrees with itself (~600 API calls, optional
  but cheap). No copy can beat that.

Report, per judge, on the 100 held-out dilemmas:

1. Score match: Pearson, Spearman, MAE.
2. Ranking match: within-dilemma Kendall tau vs the teacher. This matters
   most, because ranking 16 candidates is what the judges are actually for.
3. Replay: re-run normalisation + aggregation with the copy's scores and
   check whether the winner sets and divergence table change materially.
4. Axiom exam: same 3×3 grid as MUA.tex Table `tab:grid`, next to the
   teacher's grid (97 / 100 / 100% diagonal) and the floor's grid. Report
   the 6 held-out pairs separately; they are the only prompt-untouched ones.

## Steps

| # | What | Time |
| --- | --- | --- |
| 1 | Base model decided (Qwen2.5-1.5B-Instruct); output head remains, settled empirically at step 2; then stop editing this file | half a day |
| 2 | Build train/validation JSONL from `scores/*.json` per the frozen split | half a day |
| 3 | Train the 3 adapters (Mac overnight, or ~$5–20 of rented GPU) | 1–2 days |
| 4 | Score + ranking match (grades 1–2) | half a day |
| 5 | Replay (grade 3) | half a day |
| 6 | Axiom exam (grade 4) | half a day |
| 7 | Optional teacher self-agreement ceiling | ~600 API calls |
| 8 | Write up; package weights + certification script | 1–2 days |

Total 5–8 working days. No API cost except optional step 7.

## Caveats to keep in the write-up

- The copies inherit the teacher's biases (leniency, ceiling effects). This
  makes the instrument portable and verifiable, not better.
- 51 axiom pairs is small; make claims about the diagonal pattern, not
  individual cells.
- Ubuntu is the likely weak link (44% at the floor). If the real copy also
  fails it, ship two certified judges and report the Ubuntu failure as a
  finding.
- A copy could pass the axioms by shallow cues (e.g. "bigger number wins")
  without understanding. The 3×3 grid guards against this: a number-matcher
  would show the utilitarian pattern on every row, not a clean diagonal.
- Copies output continuous scores but downstream tie-handling assumes
  integers; if the replay (step 5) shows tie structure matters, round and
  re-check.
