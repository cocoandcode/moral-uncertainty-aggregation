"""Normalisation robustness check: common sigma in place of per-judge sigma.

The pipeline's global z-scoring divides each judge's centred scores by
that judge's own standard deviation, which is a broad-scope variance
normalisation. This script re-runs winner selection with the one
substantive alternative: centre per judge as before, but divide every
judge by the same pooled sigma, so no judge's spread is stretched or
shrunk relative to another's. Baseline is monotone-invariant and the
Nash product is scale-invariant, so only EC and Maximin can move.

Reads the published aggregation_results/*.json (raw scores and labels),
reports per-rule winner-set changes and the two-level agreement table
under the variant. Output: normalisation_check.json

Run:  python3 normalisation_check.py
"""

import json
from pathlib import Path
from statistics import pstdev

ROOT = Path(__file__).resolve().parent
FRAMEWORKS = ("utilitarian", "deontological", "ubuntu")
TIE_TOL = 1e-9

stats = json.load((ROOT / "scores" / "normalized" / "judge_stats.json").open())
MU = {fw: stats["frameworks"][fw]["mean"] for fw in FRAMEWORKS}

records = []
for p in sorted((ROOT / "aggregation_results").glob("*.json")):
    if p.name == "summary.json":
        continue
    records.append(json.load(p.open()))

all_raw = [c["raw"][fw] for r in records for c in r["candidates"]
           for fw in FRAMEWORKS]
SIGMA = pstdev(all_raw)
print(f"{len(records)} dilemmas, pooled sigma {SIGMA:.4f} "
      f"(per-judge {[round(stats['frameworks'][fw]['stdev'], 3) for fw in FRAMEWORKS]})")


def winners_variant(cands):
    rows = []
    for c in cands:
        z = {fw: (c["raw"][fw] - MU[fw]) / SIGMA for fw in FRAMEWORKS}
        s = {fw: c["raw"][fw] / SIGMA for fw in FRAMEWORKS}
        rows.append({
            "id": c["id"], "rec": c["recommendation"],
            "ec": sum(z.values()) / 3,
            "maximin": min(z.values()),
            "nash": s["utilitarian"] * s["deontological"] * s["ubuntu"],
            "baseline": z["utilitarian"],
        })
    out = {}
    for rule in ("ec", "maximin", "nash", "baseline"):
        best = max(r[rule] for r in rows)
        tied = [r for r in rows if abs(r[rule] - best) <= TIE_TOL]
        out[rule] = {"ids": sorted(r["id"] for r in tied),
                     "labels": sorted(set(r["rec"] for r in tied))}
    return out


def two_level(winsets, labelsets):
    if set.intersection(*[set(w) for w in winsets.values()]):
        return "same_response"
    if set.intersection(*[set(l) for l in labelsets.values()]):
        return "same_recommendation"
    return "different_recommendation"


changed = {rule: 0 for rule in ("ec", "maximin", "nash", "baseline")}
table = {"same_response": 0, "same_recommendation": 0,
         "different_recommendation": 0}
flipped_class = 0
for r in records:
    pub = {rule: sorted(w["tied_ids"]) for rule, w in r["winners"].items()}
    pub_labels = {rule: sorted(set(w["tied_recommendations"]))
                  for rule, w in r["winners"].items()}
    var = winners_variant(r["candidates"])
    for rule in changed:
        if var[rule]["ids"] != pub[rule]:
            changed[rule] += 1
    var_class = two_level({k: v["ids"] for k, v in var.items()},
                          {k: v["labels"] for k, v in var.items()})
    pub_class = two_level(pub, pub_labels)
    table[var_class] += 1
    if var_class != pub_class:
        flipped_class += 1

out = {
    "pooled_sigma": round(SIGMA, 4),
    "per_judge_sigma": {fw: round(stats["frameworks"][fw]["stdev"], 4)
                        for fw in FRAMEWORKS},
    "winner_set_changed": changed,
    "two_level_table_variant": table,
    "dilemmas_changing_two_level_class": flipped_class,
    "published_table": {"same_response": 339, "same_recommendation": 105,
                        "different_recommendation": 56},
    "notes": "Variant keeps per-judge centring, replaces per-judge sigma "
             "with one pooled sigma over all 24,000 raw scores. Baseline "
             "and Nash cannot move (monotone / scale invariance).",
}
(ROOT / "normalisation_check.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
