"""
Repeated axiom harness — run the judges over the axiom set N times and
aggregate, to average out temperature-0.1 stochasticity.

For every predicted cell we report how many of the N runs it passed
(pass frequency), plus mean scores. Stable cells pass N/N; flaky cells
land in between. Also reports averaged diagonal and overall pass rates.

Run:
  set -a && . ./.env && set +a
  python3 run_axioms_repeated.py [N]        # N defaults to 5
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

from openai import OpenAI

from test_axioms import AXIOMS_FILE, load_axioms, score_pair, grade

ROOT = Path(__file__).resolve().parent
SCORES_DIR = ROOT / "scores"

# Map an axiom id prefix to the judge whose own framework it tests.
PREFIX_TO_JUDGE = {"Ut": "utilitarian", "De": "deontological", "Ub": "ubuntu"}


def is_diagonal(cell_id: str, judge: str) -> bool:
    return PREFIX_TO_JUDGE.get(cell_id[:2]) == judge


def main() -> int:
    n_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    axioms_path = Path(sys.argv[2]) if len(sys.argv) > 2 else AXIOMS_FILE
    results_file = SCORES_DIR / f"{axioms_path.stem}_repeated.json"

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print('ERROR: set your key first:  export OPENAI_API_KEY="sk-..."')
        return 1
    client = OpenAI(api_key=api_key)

    data = load_axioms(axioms_path)

    # (id, judge) -> {"expected", "passes", "a_scores", "b_scores"}
    cells: dict[tuple, dict] = {}
    per_run_overall: list[float] = []
    per_run_diagonal: list[float] = []

    for run in range(1, n_runs + 1):
        run_rows = []
        for fw in data["frameworks"]:
            for ax in fw["axioms"]:
                for dilemma in ax["dilemmas"]:
                    scores = score_pair(client, dilemma)
                    run_rows.extend(grade(dilemma, scores))

        passed = sum(r["pass"] for r in run_rows)
        diag = [r for r in run_rows if is_diagonal(r["id"], r["judge"])]
        diag_passed = sum(r["pass"] for r in diag)
        per_run_overall.append(passed / len(run_rows))
        per_run_diagonal.append(diag_passed / len(diag))
        print(
            f"run {run}/{n_runs}: overall {passed}/{len(run_rows)}"
            f"  diagonal {diag_passed}/{len(diag)}"
        )

        for r in run_rows:
            key = (r["id"], r["judge"])
            cell = cells.setdefault(
                key,
                {"expected": r["expected"], "passes": 0, "a": [], "b": []},
            )
            cell["passes"] += int(r["pass"])
            cell["a"].append(r["score_a"])
            cell["b"].append(r["score_b"])

    # ── Aggregate + report ───────────────────────────────────────
    summary = []
    for (cell_id, judge), c in cells.items():
        summary.append({
            "id": cell_id,
            "judge": judge,
            "diagonal": is_diagonal(cell_id, judge),
            "expected": c["expected"],
            "passes": c["passes"],
            "runs": n_runs,
            "pass_rate": round(c["passes"] / n_runs, 3),
            "mean_a": round(mean(c["a"]), 2),
            "mean_b": round(mean(c["b"]), 2),
        })
    summary.sort(key=lambda x: x["id"])

    print(f"\n{'=' * 64}")
    print(f"Averaged over {n_runs} runs")
    print(f"  overall  mean pass rate: {mean(per_run_overall):.1%}"
          f"  (per run: {[f'{x:.0%}' for x in per_run_overall]})")
    print(f"  diagonal mean pass rate: {mean(per_run_diagonal):.1%}"
          f"  (per run: {[f'{x:.0%}' for x in per_run_diagonal]})")

    unstable = [s for s in summary if 0 < s["passes"] < n_runs]
    print(f"\nUnstable cells (passed some but not all runs): {len(unstable)}")
    for s in unstable:
        tag = "diag" if s["diagonal"] else "off "
        print(f"  [{tag}] {s['id']:<5} {s['judge']:<14}"
              f" {s['passes']}/{n_runs}  mean a={s['mean_a']} b={s['mean_b']}"
              f"  (expected {s['expected']})")

    never = [s for s in summary if s["passes"] == 0]
    print(f"\nCells that never passed: {len(never)}")
    for s in never:
        tag = "diag" if s["diagonal"] else "off "
        print(f"  [{tag}] {s['id']:<5} {s['judge']:<14}"
              f"  mean a={s['mean_a']} b={s['mean_b']}"
              f"  (expected {s['expected']})")

    results_file.parent.mkdir(exist_ok=True)
    results_file.write_text(json.dumps({
        "n_runs": n_runs,
        "overall_pass_rate": round(mean(per_run_overall), 3),
        "diagonal_pass_rate": round(mean(per_run_diagonal), 3),
        "per_run_overall": per_run_overall,
        "per_run_diagonal": per_run_diagonal,
        "cells": summary,
    }, indent=2, ensure_ascii=False))
    print(f"\nSaved aggregated results to {results_file.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
