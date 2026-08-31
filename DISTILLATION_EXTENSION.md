# Distilling the judges into small open models

Status: in progress. Steps 1-4 done (design frozen 24 Aug; adapters
trained and graded on the held-out set 25 Aug 2026). Next: replay (step 5)
and the axiom exam (step 6). The DPO extension was prototyped and dropped
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

Why test 1 is not enough: on ordinary responses, score is entangled with style. Response length alone predicts 31% of the utilitarian judge's score variance, so a copy can match scores well by learning "longer and more thorough scores higher" while knowing nothing about utilitarianism. The axiom pairs are written so both sides have the same length and style and differ only in the morally relevant fact, so style-learning scores at chance there. The pilot proved this failure is real: a crude Ubuntu copy matched scores at 0.64 correlation but scored 44% (chance) on the axioms.

Every outcome is worth writing up. Copies pass: you release the first
axiom-certified open moral judges. Copies match scores but fail axioms:
you've shown the standard way of validating distilled judges (correlation
alone) is broken. Either way there is a result, which is why this beat DPO.

## Fixed decisions

- **Base model:** `Qwen2.5-1.5B-Instruct` (decided 24 Aug 2026). Apache 2.0,
so the released judges carry no licence strings, which matters for a
community artifact; also stronger than Llama-3.2-1B at this scale, and
independence from the `llama3.1:8b` generator avoids any family-affinity
confound. **Three separate LoRA adapters** on this one base, same config,
learning rate, epochs and seed for all three; only the score column
differs.
- **Input:** dilemma + response, same format the teacher saw
(`score_responses.py`).
- **Output:** classification head over the eleven integer scores 0-10
(decided 24 Aug 2026). Not regression: the teacher's distributions are
lumpy and near-bimodal (deontology: mass at ~4 and ~9, empty middle), so
an MSE-trained regressor answers uncertainty with the conditional mean -
a score the teacher never gives - which distorts absolute levels
(maximin) and tie structure in the replay. Classification models the
lattice, and the predicted distribution doubles as an uncertainty
diagnostic. Not a text-generating model.
- **Decoding, frozen before any training:** expected value over the eleven
class probabilities for all correlation metrics (Pearson, Spearman, MAE,
Kendall tau) and for axiom-pair comparisons; expected value rounded to
the nearest integer for the aggregation replay, so ties behave like the
teacher's. Do not revisit after seeing results.
- **One sanity comparison kept:** when the first utilitarian adapter is
trained, run the identical config with a regression head once. Expected
outcome is classification wins or ties; report the comparison in one
sentence. Switch only if regression clearly wins on both correlations
and replay.
- **Split:** `data/dilemma_split.json` (400 train / 100 held-out dilemmas,
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


| #   | What                                                                                                                        | Time           |
| --- | --------------------------------------------------------------------------------------------------------------------------- | -------------- |
| 1   | DONE 24 Aug 2026: base model (Qwen2.5-1.5B-Instruct), classification head, frozen decoding. Stop editing this file          | done           |
| 2   | DONE 24 Aug 2026: `build_distil_data.py` -> `distil_data/{train,heldout}.jsonl` (6,400 / 1,600 rows per frozen split)       | done           |
| 3   | DONE 25 Aug 2026: 4 adapters trained on RunPod L40S (~29 min, ~$0.50); classification beat regression, decision confirmed   | done           |
| 4   | DONE 25 Aug 2026: `eval_distil.py` -> `distil_eval/*.metrics.json`; held-out Pearson .84/.78/.83, within-dilemma tau .40/.32/.44 (Ut/De/Ub) | done           |
| 5   | DONE 25 Aug 2026: `replay_distil.py` -> `distil_eval/replay.metrics.json`. Students reproduce the internal divergence structure almost exactly (unanimity 72% vs teacher 71%); individual winners overlap 43-59% on multi-judge rules but recommendation-level agreement is 91-93%; floor distorts the structure badly | done           |
| 6   | DONE 25 Aug 2026: `axiom_distil.py` -> `distil_eval/axioms.metrics.json`. Main-set diagonal 91% (87/93/93 Ut/De/Ub) vs teacher 99%, floor 60%. BUT held-out pairs 2/6 with systematic margin compression (student mean margin 1.5 pts vs teacher 5.6): verdicts go soft on short prompt-untouched inputs. Certification premature | done           |
| 7   | DONE 25 Aug 2026: `ceiling_distil.py` -> `distil_eval/ceiling.metrics.json`. Teacher self-agreement: Pearson ~0.99, exact-score match 87-92%, within-dilemma tau 0.93/0.87/0.84 (Ut/De/Ub). Students capture <half the achievable ranking fidelity (tau 0.40/0.29/0.31 on the same subset). The teacher is near-deterministic; the tau gap is real, not teacher noise | done           |
| 8   | Write up; package weights + certification script                                                                            | 1–2 days       |


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
- Downstream tie-handling assumes integer scores. Handled by the frozen
decoding rule: the replay uses the expected value rounded to the nearest
integer, so copies live on the same 0-10 lattice as the teacher.

