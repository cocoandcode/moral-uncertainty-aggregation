"""
Aggregating Ethics — Stage 3: Normalise raw judge scores

Reads every main-study score file in `scores/`, computes one mean and standard
deviation per judge over the whole corpus, and writes normalised scores to
`scores/normalized/`.

Two quantities are produced per response and judge:

  z = (x - mu_j) / sigma_j        used by Expected Choiceworthiness and Maximin
  s = x / sigma_j                 Nash surplus above a disagreement point of a
                                  raw score of 0

Global (rather than per-dilemma) statistics are used so that a judge which is
nearly indifferent within a dilemma is not forced to show a full spread there.

Run after all dilemmas have been scored:

  python3 normalize_scores.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCORES_DIR = ROOT / "scores"
NORMALIZED_DIR = SCORES_DIR / "normalized"
STATS_FILE = NORMALIZED_DIR / "judge_stats.json"

FRAMEWORKS = ("utilitarian", "deontological", "ubuntu")


def iter_score_files() -> list[Path]:
    """Main-study score JSONs only (axioms and normalised output are nested)."""
    return sorted(SCORES_DIR.glob("*.json"))


def load_scored(paths: list[Path]) -> tuple[list[dict], list[str]]:
    scored, skipped = [], []
    for path in paths:
        with path.open() as f:
            data = json.load(f)
        rows = data.get("scores", [])
        bad = [
            r.get("id")
            for r in rows
            if any(not isinstance(r.get(fw), (int, float)) for fw in FRAMEWORKS)
        ]
        if not rows or bad:
            reason = "no scores" if not rows else f"non-numeric scores for {bad}"
            print(f"  skipping {path.name}: {reason}")
            skipped.append(path.name)
            continue
        scored.append(data)
    return scored, skipped


def compute_judge_stats(scored: list[dict]) -> dict:
    stats = {}
    for fw in FRAMEWORKS:
        values = [r[fw] for data in scored for r in data["scores"]]
        mean = statistics.mean(values)
        sigma = statistics.pstdev(values)
        if sigma == 0:
            raise ValueError(f"judge {fw} has zero variance; cannot normalise")
        stats[fw] = {
            "n": len(values),
            "mean": mean,
            "stdev": sigma,
            "min": min(values),
            "max": max(values),
        }
        print(f"  {fw:14s} n={len(values):5d}  mu={mean:.4f}  sigma={sigma:.4f}")
    return stats


def normalise(data: dict, stats: dict) -> dict:
    rows = []
    for row in data["scores"]:
        entry = {"id": row["id"], "raw": {}, "z": {}, "nash_surplus": {}}
        for fw in FRAMEWORKS:
            x = row[fw]
            mu = stats[fw]["mean"]
            sigma = stats[fw]["stdev"]
            entry["raw"][fw] = x
            entry["z"][fw] = (x - mu) / sigma
            entry["nash_surplus"][fw] = x / sigma
        rows.append(entry)
    return {
        "dilemma": data.get("dilemma"),
        "slug": data["slug"],
        "judge_model": data.get("judge_model"),
        "normalization": "global z-score per judge; Nash surplus anchored at raw 0",
        "scores": rows,
    }


def main() -> int:
    paths = iter_score_files()
    if not paths:
        print(f"No score files found in {SCORES_DIR}. Run score_responses.py first.")
        return 1

    print(f"Reading {len(paths)} score files...")
    scored, skipped = load_scored(paths)
    if not scored:
        print("No usable score files.")
        return 1

    print("\nPer-judge statistics over the full corpus:")
    stats = compute_judge_stats(scored)

    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    with STATS_FILE.open("w") as f:
        json.dump(
            {"frameworks": stats, "dilemmas": len(scored), "source": "scores/*.json"},
            f,
            indent=2,
        )
    print(f"\nJudge statistics written to {STATS_FILE.relative_to(ROOT)}")

    for data in scored:
        out = NORMALIZED_DIR / f"{data['slug']}.json"
        with out.open("w") as f:
            json.dump(normalise(data, stats), f, indent=2)
    print(f"Normalised scores written for {len(scored)} dilemmas to "
          f"{NORMALIZED_DIR.relative_to(ROOT)}/")

    if skipped:
        # Skipped dilemmas are absent from both the statistics and the output,
        # so downstream aggregation would silently cover fewer dilemmas.
        print(f"\nWARNING: {len(skipped)} of {len(paths)} score files were skipped "
              f"and are missing downstream: {', '.join(skipped)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
