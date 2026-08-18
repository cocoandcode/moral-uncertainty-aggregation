"""
Aggregation rules for combining framework scores into a single decision.

Each rule takes per-framework scores for one response and returns a scalar.
The four rules below are the ones compared in the experiment:

- Expected choiceworthiness (EC): weighted sum across frameworks.
- Maximin: the lowest framework score (risk-averse).
- Nash parliament: product of surpluses above the disagreement point.
- Baseline: utilitarian score alone (ignores the other frameworks).

Inputs come from scores/normalized/*.json, written by normalize_scores.py.
EC and Maximin read the z-scores, since on raw 0-10 scores a judge with a wide
spread would swing them more than a compressed one. Nash reads nash_surplus,
which is anchored at a raw score of 0 so every gain is non-negative. Baseline
reads the utilitarian z-score; the z-transform is monotonic, so its winner is
the same as on raw scores.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

FRAMEWORKS = ("utilitarian", "deontological", "ubuntu")

DEFAULT_WEIGHTS = (1 / 3, 1 / 3, 1 / 3)  # utilitarian, deontological, ubuntu

TIE_TOL = 1e-9


def expected_choiceworthiness(
    u: float, d: float, ub: float, weights: Iterable[float] = DEFAULT_WEIGHTS
) -> float:
    wu, wd, wub = weights
    return wu * u + wd * d + wub * ub


def maximin(u: float, d: float, ub: float) -> float:
    return min(u, d, ub)


def nash(u: float, d: float, ub: float) -> float:
    return u * d * ub


def baseline(u: float, d: float, ub: float) -> float:
    return u


METHODS = {
    "ec": expected_choiceworthiness,
    "maximin": maximin,
    "nash": nash,
    "baseline": baseline,
}


def compute_row(row: Mapping[str, Any], weights=DEFAULT_WEIGHTS) -> dict:
    """Augment a normalised score row with all four aggregation values."""
    z = row["z"]
    surplus = row["nash_surplus"]
    zu, zd, zub = (z[fw] for fw in FRAMEWORKS)
    su, sd, sub = (surplus[fw] for fw in FRAMEWORKS)
    return {
        "id": row["id"],
        "raw": dict(row["raw"]),
        "z": dict(z),
        "ec": expected_choiceworthiness(zu, zd, zub, weights),
        "maximin": maximin(zu, zd, zub),
        "nash": nash(su, sd, sub),
        "baseline": baseline(zu, zd, zub),
    }


def pick_winners(rows: list[dict]) -> dict:
    """Return the best-scoring row id and value for each aggregation method.

    Ties are reported rather than silently broken, so that how often they occur
    can be measured before a tie-breaking convention is fixed.
    """
    winners: dict[str, dict] = {}
    for method in METHODS:
        best = max(r[method] for r in rows)
        tied = [r["id"] for r in rows if abs(r[method] - best) <= TIE_TOL]
        winners[method] = {"id": tied[0], "value": best, "tied_ids": tied}
    return winners
