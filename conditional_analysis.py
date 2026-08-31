"""Conditional analysis: does rule divergence rise when the judges disagree?

For every dilemma, quantify how much the three framework judges disagree
with one another, then test whether the aggregation rules' divergence
(response-level and action-level, as in Table tab:two-levels) is
concentrated on the high-disagreement dilemmas.

Two independent disagreement measures per dilemma:
  D_rank   = 1 - mean pairwise Kendall tau-b between the three judges'
             orderings of the sixteen responses (ordering conflict)
  D_spread = mean over responses of the population SD of the three
             judges' z-scores for that response (level conflict)

Outcomes per dilemma (computed by the existing pipeline, read from
aggregation_results/*.json):
  resp_div = no single response lies in all four rules' winner sets
  act_div  = no recommendation label lies in all four rules' label sets

Also computed for the three uncertainty rules alone (EC, Maximin, Nash),
since the supervisor's question concerns those specifically.

Outputs: conditional_analysis.json (all numbers cited in
CONDITIONAL_ANALYSIS.md come from this file).

Run:  python3 conditional_analysis.py
"""

import itertools
import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent
AGG = ROOT / "aggregation_results"
JUDGES = ("utilitarian", "deontological", "ubuntu")
UNCERTAINTY_RULES = ("ec", "maximin", "nash")
ALL_RULES = ("ec", "maximin", "nash", "baseline")
N_BINS = 4


def dilemma_rows() -> list:
    rows = []
    for p in sorted(AGG.glob("*.json")):
        if p.name == "summary.json":
            continue
        r = json.loads(p.read_text())
        cands = r["candidates"]

        # D_rank: mean pairwise Kendall tau-b over judge orderings.
        # tau is invariant to the (affine) z-transform, so raw == z here.
        taus = []
        for a, b in itertools.combinations(JUDGES, 2):
            xa = [c["raw"][a] for c in cands]
            xb = [c["raw"][b] for c in cands]
            if len(set(xa)) < 2 or len(set(xb)) < 2:
                continue  # a constant judge has no ordering to compare
            t = stats.kendalltau(xa, xb)[0]
            if not np.isnan(t):
                taus.append(t)
        d_rank = 1 - float(np.mean(taus)) if taus else None

        # D_spread: mean per-response population SD of the three z-scores.
        d_spread = float(np.mean(
            [np.std([c["z"][j] for j in JUDGES]) for c in cands]))

        # Outcomes for all four rules (the pipeline's own flags).
        resp_div4 = not r["unanimous"]
        act_div4 = not r["unanimous_recommendation"]

        # Outcomes for EC / Maximin / Nash alone.
        w = r["winners"]
        sets3 = [set(w[m]["tied_ids"]) for m in UNCERTAINTY_RULES]
        resp_div3 = not set.intersection(*sets3)
        label = {c["id"]: c.get("recommendation") for c in cands}
        lsets3 = [{label[i] for i in s if label.get(i)} for s in sets3]
        act_div3 = not (all(lsets3) and set.intersection(*lsets3))

        rows.append({
            "slug": r["slug"], "d_rank": d_rank, "d_spread": d_spread,
            "n_tau_pairs": len(taus),
            "resp_div4": resp_div4, "act_div4": act_div4,
            "resp_div3": resp_div3, "act_div3": act_div3,
        })
    return rows


def quartile_table(rows, dkey, outcome) -> list:
    """Equal-count bins by dkey; divergence rate per bin."""
    usable = [r for r in rows if r[dkey] is not None]
    order = sorted(usable, key=lambda r: r[dkey])
    bins = np.array_split(order, N_BINS)
    table = []
    for i, b in enumerate(bins):
        vals = [r[dkey] for r in b]
        rate = float(np.mean([r[outcome] for r in b]))
        table.append({
            "bin": i + 1, "n": len(b),
            "d_min": round(min(vals), 4), "d_max": round(max(vals), 4),
            "d_mean": round(float(np.mean(vals)), 4),
            "divergence_rate": round(rate, 4),
        })
    return table


def association(rows, dkey, outcome) -> dict:
    usable = [r for r in rows if r[dkey] is not None]
    d = np.array([r[dkey] for r in usable])
    y = np.array([r[outcome] for r in usable], dtype=bool)
    mw = stats.mannwhitneyu(d[y], d[~y], alternative="greater")
    rank_biserial = 2 * mw.statistic / (y.sum() * (~y).sum()) - 1
    rho, rho_p = stats.spearmanr(d, y)
    return {
        "n": len(usable), "n_divergent": int(y.sum()),
        "mean_d_divergent": round(float(d[y].mean()), 4),
        "mean_d_agreeing": round(float(d[~y].mean()), 4),
        "mannwhitney_p_onesided": float(mw.pvalue),
        "rank_biserial": round(float(rank_biserial), 4),
        "spearman_rho": round(float(rho), 4),
        "spearman_p": float(rho_p),
    }


def main() -> None:
    rows = dilemma_rows()
    excluded = [r["slug"] for r in rows if r["d_rank"] is None]
    print(f"{len(rows)} dilemmas; {len(excluded)} excluded from D_rank "
          f"(no comparable judge pair): {excluded}")

    report = {"n_dilemmas": len(rows),
              "d_rank_excluded": excluded,
              "quartiles": {}, "association": {}}
    for dkey in ("d_rank", "d_spread"):
        for outcome in ("resp_div4", "act_div4", "resp_div3", "act_div3"):
            key = f"{dkey}__{outcome}"
            report["quartiles"][key] = quartile_table(rows, dkey, outcome)
            report["association"][key] = association(rows, dkey, outcome)

    corr = stats.spearmanr(
        [r["d_rank"] for r in rows if r["d_rank"] is not None],
        [r["d_spread"] for r in rows if r["d_rank"] is not None])
    report["d_rank_vs_d_spread_spearman"] = round(float(corr[0]), 4)

    (ROOT / "conditional_analysis.json").write_text(
        json.dumps(report, indent=2))

    for key, tab in report["quartiles"].items():
        rates = " ".join(f"{t['divergence_rate']:.2f}" for t in tab)
        a = report["association"][key]
        print(f"{key:24s} rates by quartile: {rates}   "
              f"MW p={a['mannwhitney_p_onesided']:.2e} "
              f"rho={a['spearman_rho']:.3f}")
    print(f"D_rank vs D_spread spearman: "
          f"{report['d_rank_vs_d_spread_spearman']}")
    print("saved conditional_analysis.json")


if __name__ == "__main__":
    main()
