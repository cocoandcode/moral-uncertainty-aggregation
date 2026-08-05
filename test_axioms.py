"""
Axiom harness — do the LLM judges actually follow their frameworks?

For every axiom pair in data/axioms.json we score response_a and response_b
under all three judges, then check whether the direction of the two scores
matches the `expected` prediction for that judge.

Run:
  set -a && . ./.env && set +a     # or: export OPENAI_API_KEY="sk-..."
  python3 test_axioms.py
"""

import json
import os
import sys
from pathlib import Path

from openai import OpenAI

# Reuse the judge prompts and the scoring call from the main pipeline,
# so the axioms are scored by exactly the same judges as real responses.
from score_responses import FRAMEWORKS, score_response

ROOT = Path(__file__).resolve().parent
AXIOMS_FILE = ROOT / "data" / "axioms.json"
SCORES_DIR = ROOT / "scores" / "axioms"

# Minimum score gap that counts as a real preference (tie-handling rule).
# 0 = any strict difference counts; a tie fails a directional prediction.
TOLERANCE = 0


def load_axioms(path: Path = AXIOMS_FILE) -> dict:
    return json.loads(path.read_text())


def outcome(score_a: int, score_b: int, tol: int = TOLERANCE) -> str:
    """Turn two 0-10 scores into a direction label."""
    if score_a is None or score_b is None:
        return "error"
    if score_a - score_b > tol:
        return "a > b"
    if score_b - score_a > tol:
        return "b > a"
    return "a ≈ b"


def score_pair(client: OpenAI, dilemma: dict) -> dict:
    """Score response_a and response_b under each judge → {judge: (a, b)}."""
    scores = {}
    scenario = dilemma["dilemma"]
    for judge, prompt in FRAMEWORKS.items():
        sa = score_response(client, dilemma["response_a"], prompt, scenario)
        sb = score_response(client, dilemma["response_b"], prompt, scenario)
        scores[judge] = (sa, sb)
    return scores


def grade(dilemma: dict, scores: dict) -> list[dict]:
    """Compare each judge's actual direction to its expected prediction."""
    rows = []
    for judge, expected in dilemma["expected"].items():
        if expected is None:
            continue  # no prediction for this judge on this pair
        sa, sb = scores[judge]
        actual = outcome(sa, sb)
        rows.append({
            "id": dilemma["id"],
            "judge": judge,
            "score_a": sa,
            "score_b": sb,
            "expected": expected,
            "actual": actual,
            "pass": actual == expected,
        })
    return rows


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print('ERROR: set your key first:  export OPENAI_API_KEY="sk-..."')
        return 1
    client = OpenAI(api_key=api_key)

    axioms_path = Path(sys.argv[1]) if len(sys.argv) > 1 else AXIOMS_FILE
    results_file = SCORES_DIR / f"{axioms_path.stem}_results.json"
    data = load_axioms(axioms_path)
    results = []

    for fw in data["frameworks"]:
        for ax in fw["axioms"]:
            print(f"\n{ax['axiom_id']}: {ax['axiom']}")
            for dilemma in ax["dilemmas"]:
                scores = score_pair(client, dilemma)
                rows = grade(dilemma, scores)
                results.extend(rows)
                for r in rows:
                    mark = "PASS" if r["pass"] else "FAIL"
                    print(
                        f"  [{mark}] {r['id']:<5} {r['judge']:<14}"
                        f" a={r['score_a']} b={r['score_b']}"
                        f"  expected {r['expected']}, got {r['actual']}"
                    )

    # ── Summary ──────────────────────────────────────────────
    total = len(results)
    passed = sum(r["pass"] for r in results)
    print(f"\n{'=' * 60}")
    print(f"Overall: {passed}/{total} predicted cells passed")

    by_axiom: dict[str, list[bool]] = {}
    for r in results:
        by_axiom.setdefault(r["id"][:-1], []).append(r["pass"])
    print("\nPer axiom:")
    for axiom_id in sorted(by_axiom):
        flags = by_axiom[axiom_id]
        print(f"  {axiom_id}: {sum(flags)}/{len(flags)}")

    results_file.parent.mkdir(exist_ok=True)
    results_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nSaved detailed results to {results_file.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
