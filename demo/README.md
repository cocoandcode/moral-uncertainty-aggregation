# Aggregating Ethics Experimentation

A small, local experiment comparing how different moral aggregation methods select "best" AI advice.

The workflow:

1. Generate multiple candidate answers to a moral dilemma.
2. Score each answer under three ethical frameworks (raw 0–10 scores).
3. (Later) Normalise scores, then aggregate with multiple decision rules.
4. Visualize which response each rule picks.

Generation uses Ollama locally with `llama3.1:8b`. Scoring uses OpenAI's `gpt-4o-mini`.

## Project layout

```
.
├── generate_responses.py     # Stage 1: produce N candidate responses
├── format_responses.py       # Optional helper to wrap response lines
├── score_responses.py        # Stage 2: score + aggregate + visualise
├── aggregation.py            # Aggregation rules (EC, Maximin, Nash, Baseline)
├── data/
│   ├── dilemmas.json         # Prompts used by Stage 1, keyed by id
│   └── daily_dilemmas.json   # Reference corpus
├── responses/                # Stage 1 output (one file per dilemma)
├── scores/                   # Stage 2 output (.json + .html dashboard)
│   └── axioms/               # Axiom harness results (separate from main study)
├── templates/
│   └── scores.html           # HTML template for the dashboard
├── requirements.txt
└── README.md
```

## The four aggregation rules

Each candidate response gets three judge scores (0-10):

- **Utilitarian** — overall outcomes / wellbeing
- **Deontological** — duties, honesty, rights
- **Ubuntu** — community, relational harmony

The four rules in `aggregation.py`:

- **Expected choiceworthiness (EC)** — weighted sum (`0.4, 0.35, 0.25`)
- **Maximin** — maximise the minimum framework score
- **Nash parliament** — maximise the product of scores
- **Baseline** — utilitarian score alone

The experiment asks: do different aggregation rules select different responses?

## Setup

Requirements: Python 3, Ollama running locally with `llama3.1:8b` pulled, and an OpenAI API key.

```bash
pip3 install -r requirements.txt
ollama pull llama3.1:8b
ollama serve
export OPENAI_API_KEY="sk-..."
```

## How to run

Add or edit dilemmas in `data/dilemmas.json`. Each entry has a `slug`, `title`, and `prompt`.

```bash
python3 generate_responses.py 3                 # writes responses/grandmother.json
python3 format_responses.py                     # optional: re-wrap response lines
python3 score_responses.py grandmother          # writes scores/grandmother.{json,html}
```

`score_responses.py` accepts either a slug (e.g. `grandmother`) or a full path to a responses file.

Open `scores/index.html` in your browser for a linked table of all scored
dilemmas. Each row opens `scores/<slug>.html` — hover a response number to
read the full text. Scoring writes **raw** judge scores only; aggregation
happens in a later step after normalisation.
Re-run `python3 build_index.py` (or `python3 rebuild_score_html.py`) anytime
to refresh the index after scoring.

## Output schema

`responses/<slug>.json`:

- top-level metadata: `dilemma`, `slug`, `model`, `temperature`, `num_responses`
- `responses`: list of `{ id, system_prompt, response }` where `response` is a list of wrapped lines

`scores/<slug>.json`:

- `dilemma`, `slug`, `judge_model`
- `scores` — raw framework scores per response (`id`, U/D/Ub)
- `rows` — same scores plus full response text (for the HTML dashboard)

## Caveats

- Experimental setup; not a normative ethics engine.
- Scores are produced by an LLM, so judge-model bias is likely.
- `temperature=1.0` means each generation run produces a different response pool.
