# Aggregating Ethics

Code and data for the MSc dissertation **"Aggregating Ethics: Moral Uncertainty
and Response Selection in Language Models"** (`MUA.pdf`).

The study asks whether the choice of moral aggregation rule changes which
response a language-model system selects on everyday moral dilemmas. Sixteen
candidate responses to each of 500 dilemmas are scored by three LLM judges
(utilitarian, deontological, Ubuntu), and four selection rules are compared:
expected choiceworthiness, maximin, a Nash bargain, and a single-theory
utilitarian baseline. The rules prefer different responses on 32% of dilemmas
and different actions on 11.2%, rising to 27% on the quarter of dilemmas where
the judges disagree most.

## The pipeline

Five stages, one script each:

| Stage | Script | Output |
|---|---|---|
| 1. Generate 16 candidates per dilemma (`llama3.1:8b` via Ollama, temp 1.1, no framework prompt) | `generate_responses.py <n>` | `responses/<slug>.json` |
| 2. Score each candidate under the three judges (`gpt-4o-mini`, 0–10) | `score_responses.py <slug>` | `scores/<slug>.{json,html}` |
| 3. Label each candidate's recommended action (TO_DO / NOT_TO_DO / REFUSAL / OTHER) | `label_recommendations.py <slug>` | `recommendations/<slug>.json` |
| 4. Global z-score normalisation per judge over all 8,000 responses | `normalize_scores.py` | `scores/normalized/` |
| 5. Apply the four rules, keep ties as winner sets, measure divergence | `aggregate_scores.py` | `aggregation_results/` |

Dilemmas come from the DailyDilemmas corpus, filtered to 500 contested cases by
`filter_dilemmas.py` (`data/filtered_dilemmas.json`). Stages 4 and 5 are
corpus-wide by design: normalisation must pool over all dilemmas, and both
stages rewrite their entire output directories on every run.

## Layout

```
data/                    dilemma corpus, filter output, axiom suites, train/test split
responses/               stage 1 output: 16 candidates per dilemma
scores/                  stage 2 output: raw judge scores (+ HTML dashboards)
recommendations/         stage 3 output: action labels with supporting quotes
scores/normalized/       stage 4 output: z-scores, Nash surpluses, judge_stats.json
aggregation_results/     stage 5 output: winner sets per rule, summary.json, dashboards
aggregation_results_deont50/, _ubuntu50/   credence-tilt sensitivity runs
distil_data/, distil_models/, distil_eval/  Section 6 artefacts
templates/               HTML templates
MUA.tex, MUA.pdf         the dissertation
```

## Reproducing the paper's numbers

| Result in the paper | Command |
|---|---|
| Axiom pass-rate grid (judge validation) | `python3 run_axioms_repeated.py` |
| Tie rates, two-level agreement, pairwise divergence | `python3 aggregate_scores.py` (printed; also `aggregation_results/summary.json`) |
| Divergence by judge-disagreement quartile | `python3 conditional_analysis.py` |
| Credence sensitivity (2:1:1 tilts) | `python3 aggregate_scores.py --credences 0.25,0.5,0.25 --out-dir aggregation_results_deont50` (and `0.25,0.25,0.5` for Ubuntu) |
| Pooled-sigma normalisation check | `python3 normalisation_check.py` |
| Distillation fidelity ladder | `python3 eval_untrained.py`, `distil_floor.py`, `eval_distil.py`, `ceiling_distil.py` |
| Pipeline replay on the copies | `python3 replay_distil.py` |
| Copies' axiom exam | `python3 axiom_distil.py`, `axiom_untrained.py` |
| Appendix case studies | `python3 build_case_appendix.py` |

## Judge validation

The judges' fidelity to their frameworks is tested behaviourally, not assumed.
`data/axioms.json` holds 15 operational axioms (5 per theory), each tested by
three matched response pairs. `run_axioms_repeated.py` runs the harness
(`test_axioms.py`) five times; the judges pass 99% of own-framework cells.
`conditional_analysis.py` computes per-dilemma judge disagreement and shows
divergence concentrating where the judges conflict (Section 5.6).

## Distillation extension (Section 6)

The three judges are distilled into `Qwen2.5-1.5B-Instruct` LoRA classifiers,
split 400/100 by dilemma. In run order: `build_distil_data.py`,
`train_distil.py` (see `distil_requirements.txt`), `eval_distil.py`,
`distil_floor.py`, `ceiling_distil.py`, `replay_distil.py`,
`axiom_distil.py`, with untrained baselines in `eval_untrained.py` and
`axiom_untrained.py`. Outputs live in `distil_data/`, `distil_models/`,
`distil_eval/`. Headline: the copies correlate well with their teachers yet
capture less than half of the teachers' ranking and little framework behaviour
beyond the base model's.

## Running it

Requires Python 3, `pip3 install -r requirements.txt`, Ollama serving
`llama3.1:8b`, and `OPENAI_API_KEY` set (a `.env` file is supported:
`set -a && . ./.env && set +a`).

To trace one dilemma end to end:

```bash
python3 generate_responses.py 472
python3 score_responses.py letting_the_police_know_when_people_are_breaking_the_law
python3 label_recommendations.py letting_the_police_know_when_people_are_breaking_the_law
python3 normalize_scores.py
python3 aggregate_scores.py
open aggregation_results/letting_the_police_know_when_people_are_breaking_the_law.html
```

**Warning:** this overwrites the stored results that the dissertation reports
(generation is unseeded, and stages 4–5 rewrite all 500 dilemmas). To
experiment safely, work in a copy of the repo.

Browsable dashboards: `scores/index.html` and `aggregation_results/index.html`.

## Caveats

- All scores and labels are LLM-produced; the labels are consistency-checked
  but not validated against human judgement (Section 4.6.1).
- Generation is stochastic, so a re-run produces a different candidate pool.
- This is a measurement study of selection rules, not a normative ethics engine.
