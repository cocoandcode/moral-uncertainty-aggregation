"""
Aggregating Ethics — Stage 4: Apply the aggregation rules and select winners

Reads normalised scores from `scores/normalized/` and core-recommendation
labels from `recommendations/`, applies the four selection rules in
aggregation.py, and writes per-dilemma results to `aggregation_results/`:

  <slug>.json    candidate values, recommendation labels, winners, winner texts
  <slug>.html    browsable view with hoverable responses and TO_DO / NOT_TO_DO labels
  index.html     all dilemmas, with a filter for those where the rules disagree
  summary.json   corpus-level tie rates and pairwise divergence

Ties are recorded rather than broken. Two divergence measures are reported:

  strict     the two rules' winner sets are disjoint, so no tie-breaking
             convention could make them agree
  forced     the expected disagreement if each rule picked uniformly at random
             from its tied set, an upper bound that includes arbitrary choices

Run after normalize_scores.py:

  python3 aggregate_scores.py

Credence sensitivity runs go to their own directory, e.g.:

  python3 aggregate_scores.py --credences 0.25,0.5,0.25 --out-dir aggregation_results_deont50
"""

from __future__ import annotations

import argparse
import html
import itertools
import json
import statistics
import sys
from pathlib import Path
from string import Template

from aggregation import (
    DEFAULT_WEIGHTS,
    FRAMEWORKS,
    METHODS,
    TIE_TOL,
    compute_row,
    pick_winners,
)

ROOT = Path(__file__).resolve().parent
NORMALIZED_DIR = ROOT / "scores" / "normalized"
RESPONSES_DIR = ROOT / "responses"
LABELS_DIR = ROOT / "recommendations"
DEFAULT_OUT_DIR = ROOT / "aggregation_results"

RULE_LABELS = {
    "ec": "Expected Choiceworthiness",
    "maximin": "Maximin",
    "nash": "Nash",
    "baseline": "Baseline (utilitarian only)",
}
RULE_COLOURS = {
    "ec": "#185FA5",
    "maximin": "#B7791F",
    "nash": "#0F6E56",
    "baseline": "#8A8F98",
}
REC_COLOURS = {
    "TO_DO": "#185FA5",
    "NOT_TO_DO": "#B7791F",
    "REFUSAL": "#6B7280",
    "OTHER": "#7C3AED",
}


def iter_normalized_files() -> list[Path]:
    """Per-dilemma normalised scores only (judge_stats.json is corpus-level)."""
    return sorted(p for p in NORMALIZED_DIR.glob("*.json") if p.name != "judge_stats.json")


def load_response_texts(slug: str) -> dict[int, str]:
    path = RESPONSES_DIR / f"{slug}.json"
    if not path.exists():
        return {}
    texts = {}
    for row in json.load(path.open()).get("responses", []):
        body = row.get("response", "")
        texts[row["id"]] = "\n".join(body) if isinstance(body, list) else body
    return texts


def load_recommendation_labels(slug: str) -> dict | None:
    path = LABELS_DIR / f"{slug}.json"
    if not path.exists():
        return None
    data = json.load(path.open())
    by_id = {row["id"]: row["label"] for row in data.get("labels", [])}
    return {
        "to_do_action": data.get("to_do_action"),
        "not_to_do_action": data.get("not_to_do_action"),
        "labeler_model": data.get("labeler_model"),
        "by_id": by_id,
    }


def embed_json(payload: object) -> str:
    """JSON safe to inline in a <script> element.

    The HTML parser ends a script block at the first "</script" and treats
    "<!--" specially, regardless of JSON quoting, so "<" must not appear
    literally (one llama response contains "<!---->").
    """
    return json.dumps(payload).replace("<", "\\u003c")


def build_record(
    data: dict, texts: dict[int, str], rec: dict | None, weights=DEFAULT_WEIGHTS
) -> dict:
    candidates = [compute_row(row, weights) for row in data["scores"]]
    by_id = (rec or {}).get("by_id", {})
    for c in candidates:
        c["recommendation"] = by_id.get(c["id"])
    winners = pick_winners(candidates)
    for method, info in winners.items():
        info["recommendation"] = by_id.get(info["id"])
        info["tied_recommendations"] = sorted(
            {by_id[i] for i in info["tied_ids"] if i in by_id}
        )
    sets = [set(w["tied_ids"]) for w in winners.values()]
    representatives = {w["id"] for w in winners.values()}
    # Recommendation-level agreement is a weaker test than response-level: rules
    # may pick different responses yet still endorse the same course of action.
    rec_sets = [set(w["tied_recommendations"]) for w in winners.values()]
    shared_recs = set.intersection(*rec_sets) if all(rec_sets) else set()
    return {
        "slug": data["slug"],
        "dilemma": data.get("dilemma"),
        "judge_model": data.get("judge_model"),
        "credences": dict(zip(FRAMEWORKS, weights)),
        "normalization": data.get("normalization"),
        "to_do_action": (rec or {}).get("to_do_action"),
        "not_to_do_action": (rec or {}).get("not_to_do_action"),
        "labeler_model": (rec or {}).get("labeler_model"),
        "candidates": candidates,
        "winners": winners,
        "winner_texts": {str(i): texts.get(i, "") for i in sorted(representatives)},
        "unanimous": bool(set.intersection(*sets)),
        "unanimous_recommendation": bool(shared_recs),
        "shared_recommendations": sorted(shared_recs),
        "distinct_recommendations": sorted(set().union(*rec_sets)) if any(rec_sets) else [],
        "distinct_winners": len(representatives),
    }


def summarise(records: list[dict], weights=DEFAULT_WEIGHTS) -> dict:
    n = len(records)
    per_rule = {}
    for method in METHODS:
        sizes = [len(r["winners"][method]["tied_ids"]) for r in records]
        tied = [s for s in sizes if s > 1]
        per_rule[method] = {
            "dilemmas_with_tie": len(tied),
            "tie_rate": len(tied) / n,
            "mean_tie_size": statistics.mean(tied) if tied else 0.0,
            "max_tie_size": max(sizes),
            "complete_ties": sum(1 for r, s in zip(records, sizes) if s == len(r["candidates"])),
        }

    pairwise = {}
    for a, b in itertools.combinations(METHODS, 2):
        strict = forced = 0.0
        for r in records:
            sa = set(r["winners"][a]["tied_ids"])
            sb = set(r["winners"][b]["tied_ids"])
            if sa.isdisjoint(sb):
                strict += 1
            # Independent uniform picks agree only on the intersection.
            forced += 1 - len(sa & sb) / (len(sa) * len(sb))
        pairwise[f"{a}_vs_{b}"] = {
            "strict_divergence": strict / n,
            "forced_divergence": forced / n,
        }

    return {
        "dilemmas": n,
        "candidates_per_dilemma": sorted({len(r["candidates"]) for r in records}),
        "credences": dict(zip(FRAMEWORKS, weights)),
        "tie_tolerance": TIE_TOL,
        "unanimous": sum(1 for r in records if r["unanimous"]),
        "unanimous_recommendation": sum(1 for r in records if r["unanimous_recommendation"]),
        "all_rules_unique_winner": sum(
            1 for r in records if all(len(w["tied_ids"]) == 1 for w in r["winners"].values())
        ),
        "per_rule": per_rule,
        "pairwise": pairwise,
    }


PAGE = Template("""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Aggregation — $title</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 980px; margin: 2rem auto; padding: 0 1rem;">

<p style="margin: 0 0 0.75rem;"><a href="index.html" style="color:#185FA5;text-decoration:none;">&larr; All dilemmas</a></p>

<h2 style="margin-bottom:0.25rem;">Selected responses — $title</h2>
<p style="color:#666;margin-top:0.25rem;">
  $summary_line &middot; judge model: $judge_model &middot; credences: $credence_line
</p>

<div style="margin: 1rem 0; padding: 12px 14px; background: #f7f7f8; border-radius: 8px; border-left: 3px solid #185FA5;">
  <p style="font-size: 11px; color: #888; margin: 0 0 6px; text-transform: uppercase; letter-spacing: 0.04em;">Dilemma</p>
  <p style="margin: 0; font-size: 14px; line-height: 1.55; white-space: pre-wrap;">$dilemma</p>
  <p style="margin: 10px 0 0; font-size: 12px; color: #555;">
    <span style="color:#185FA5;font-weight:600;">TO_DO</span> = $to_do_action
    &nbsp;&middot;&nbsp;
    <span style="color:#B7791F;font-weight:600;">NOT_TO_DO</span> = $not_to_do_action
  </p>
</div>

<h3 style="margin-top:1.5rem;">Winners by rule</h3>
$winner_cards

<h3 style="margin-top:1.75rem;">All candidates</h3>
<p style="color:#888;font-size:12px;">Hover a response number for its full text. Bold marks the top value for a rule; a dot marks a tied entry.</p>
<table style="width:100%;border-collapse:collapse;font-size:13px;">
<thead>
<tr style="border-bottom:2px solid #ccc;">
  <th style="text-align:left;padding:8px 6px;">Resp</th>
  <th style="text-align:center;padding:8px 6px;">Rec</th>
  <th style="text-align:center;padding:8px 6px;color:#534AB7;">Ut</th>
  <th style="text-align:center;padding:8px 6px;color:#185FA5;">De</th>
  <th style="text-align:center;padding:8px 6px;color:#0F6E56;">Ub</th>
  <th style="text-align:center;padding:8px 6px;color:#185FA5;">EC</th>
  <th style="text-align:center;padding:8px 6px;color:#B7791F;">Maximin</th>
  <th style="text-align:center;padding:8px 6px;color:#0F6E56;">Nash</th>
  <th style="text-align:center;padding:8px 6px;color:#8A8F98;">Baseline</th>
</tr>
</thead>
<tbody>
$table_rows
</tbody>
</table>

<div id="tip" style="display:none;position:fixed;z-index:1000;max-width:460px;max-height:60vh;overflow:auto;background:#1f2933;color:#f5f7fa;padding:12px 14px;border-radius:8px;font-size:13px;line-height:1.5;white-space:pre-wrap;box-shadow:0 6px 24px rgba(0,0,0,0.28);pointer-events:none;"></div>

<script id="texts" type="application/json">$texts_json</script>
<script>
const texts = JSON.parse(document.getElementById('texts').textContent);
const tip = document.getElementById('tip');
function moveTip(e) {
  const pad = 16;
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + tip.offsetWidth > window.innerWidth) x = e.clientX - tip.offsetWidth - pad;
  if (y + tip.offsetHeight > window.innerHeight) y = e.clientY - tip.offsetHeight - pad;
  tip.style.left = x + 'px';
  tip.style.top = y + 'px';
}
for (const el of document.querySelectorAll('[data-resp]')) {
  el.addEventListener('mouseenter', e => {
    tip.textContent = texts[el.dataset.resp] || '(text unavailable)';
    tip.style.display = 'block';
    moveTip(e);
  });
  el.addEventListener('mousemove', moveTip);
  el.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
}
</script>
</body>
</html>
""")


def rec_badge(label: str | None) -> str:
    if not label:
        return '<span style="color:#aaa;">—</span>'
    colour = REC_COLOURS.get(label, "#6B7280")
    return (
        f'<span style="display:inline-block;padding:1px 7px;border-radius:999px;'
        f'background:{colour}18;color:{colour};font-size:11px;font-weight:700;'
        f'letter-spacing:0.02em;">{html.escape(label)}</span>'
    )


def credence_line(weights) -> str:
    if tuple(weights) == tuple(DEFAULT_WEIGHTS):
        return "equal (1/3 each)"
    return ", ".join(f"{fw} {w:.2f}" for fw, w in zip(FRAMEWORKS, weights))


def render_page(record: dict, texts: dict[int, str], weights=DEFAULT_WEIGHTS) -> str:
    title = record["slug"].replace("_", " ").title()
    winners = record["winners"]

    cards = []
    for method, info in winners.items():
        tie_note = (
            f"<span style='color:#B7791F;'>tied with {len(info['tied_ids']) - 1} other(s): "
            f"{', '.join(str(i) for i in info['tied_ids'])}</span>"
            if len(info["tied_ids"]) > 1
            else "<span style='color:#0F6E56;'>unique winner</span>"
        )
        tied_recs = info.get("tied_recommendations") or []
        rec_note = (
            " / ".join(tied_recs) if len(tied_recs) > 1
            else (info.get("recommendation") or "—")
        )
        text = record["winner_texts"].get(str(info["id"]), "")
        cards.append(
            f"""<div style="margin:0 0 12px;padding:12px 14px;border:1px solid #e3e3e6;border-radius:8px;border-left:4px solid {RULE_COLOURS[method]};">
  <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;">
    <strong style="color:{RULE_COLOURS[method]};">{RULE_LABELS[method]}</strong>
    <span style="font-size:12px;color:#666;">response {info['id']} &middot; {rec_badge(info.get('recommendation'))} &middot; value {info['value']:.3f} &middot; {tie_note}</span>
  </div>
  <p style="margin:6px 0 0;font-size:12px;color:#666;">core recommendation among ties: {html.escape(rec_note)}</p>
  <p style="margin:8px 0 0;font-size:13px;line-height:1.5;white-space:pre-wrap;max-height:180px;overflow:auto;color:#333;">{html.escape(text)}</p>
</div>"""
        )

    rows = []
    for c in record["candidates"]:
        cells = []
        for method in METHODS:
            info = winners[method]
            is_top = c["id"] in info["tied_ids"]
            mark = " &bull;" if is_top and len(info["tied_ids"]) > 1 else ""
            weight = "700" if is_top else "400"
            bg = "#f2f7fc" if is_top else "transparent"
            cells.append(
                f'<td style="text-align:center;padding:7px 6px;font-weight:{weight};'
                f'background:{bg};font-variant-numeric:tabular-nums;">{c[method]:.3f}{mark}</td>'
            )
        raw = c["raw"]
        rows.append(
            f"""<tr style="border-bottom:1px solid #eee;">
  <td style="padding:7px 6px;"><span data-resp="{c['id']}" style="cursor:help;border-bottom:1px dotted #999;">#{c['id']}</span></td>
  <td style="text-align:center;padding:7px 6px;">{rec_badge(c.get('recommendation'))}</td>
  <td style="text-align:center;padding:7px 6px;color:#534AB7;">{raw['utilitarian']}</td>
  <td style="text-align:center;padding:7px 6px;color:#185FA5;">{raw['deontological']}</td>
  <td style="text-align:center;padding:7px 6px;color:#0F6E56;">{raw['ubuntu']}</td>
  {''.join(cells)}
</tr>"""
        )

    if record["unanimous"]:
        summary_line = "all four rules can agree on one response"
    else:
        summary_line = f"rules split across {record['distinct_winners']} different responses"
    if record["unanimous_recommendation"]:
        summary_line += (
            "; they share the core recommendation "
            f"{' / '.join(record['shared_recommendations'])}"
        )
    else:
        summary_line += (
            "; they differ on the core recommendation "
            f"({' vs '.join(record['distinct_recommendations'])})"
        )

    return PAGE.safe_substitute(
        title=html.escape(title),
        credence_line=html.escape(credence_line(weights)),
        judge_model=html.escape(record.get("judge_model") or "unknown"),
        dilemma=html.escape(record.get("dilemma") or ""),
        to_do_action=html.escape(record.get("to_do_action") or "(missing)"),
        not_to_do_action=html.escape(record.get("not_to_do_action") or "(missing)"),
        summary_line=summary_line,
        winner_cards="\n".join(cards),
        table_rows="\n".join(rows),
        # Every candidate is hoverable, so the page carries all texts even though
        # the JSON record keeps only the winners'.
        texts_json=embed_json({str(i): t for i, t in texts.items()}),
    )


INDEX = Template("""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Aggregation results — index</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 1150px; margin: 2rem auto; padding: 0 1rem;">
  <h1 style="margin-bottom:0.25rem;">Aggregation results</h1>
  <p style="color:#666;margin-top:0.25rem;">
    $n dilemmas &middot; four selection rules over normalised scores &middot; credences: $credences.
    Ties are shown as sets; a rule with several ids was indifferent between them.
  </p>

  <div style="margin:1rem 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
    <input id="q" type="search" placeholder="Filter by title or text&hellip;"
      style="flex:1;min-width:200px;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
    <label style="font-size:13px;color:#444;display:flex;align-items:center;gap:6px;">
      <input id="divergent" type="checkbox" /> only where rules pick different responses
    </label>
    <label style="font-size:13px;color:#444;display:flex;align-items:center;gap:6px;">
      <input id="divergentRec" type="checkbox" /> only where rules differ on the recommendation
    </label>
  </div>
  <p style="color:#888;font-size:12px;margin:-0.5rem 0 1rem;">
    Two levels of agreement. <b>Same response</b> asks whether some single response could
    satisfy all four rules. <b>Same recommendation</b> is weaker: rules may pick different
    responses and still endorse the same course of action. Rules disagree at the
    recommendation level whenever one selects a label (TO_DO / NOT_TO_DO / REFUSAL / OTHER)
    that another cannot.
  </p>

  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead>
      <tr style="border-bottom:2px solid #ccc;text-align:left;">
        <th style="padding:8px 6px;">Dilemma</th>
        <th style="padding:8px 6px;text-align:center;color:#185FA5;">EC</th>
        <th style="padding:8px 6px;text-align:center;color:#B7791F;">Maximin</th>
        <th style="padding:8px 6px;text-align:center;color:#0F6E56;">Nash</th>
        <th style="padding:8px 6px;text-align:center;color:#8A8F98;">Baseline</th>
        <th style="padding:8px 6px;text-align:center;">Same<br><span style="font-weight:400;color:#888;">response?</span></th>
        <th style="padding:8px 6px;text-align:center;">Same<br><span style="font-weight:400;color:#888;">recommendation?</span></th>
      </tr>
    </thead>
    <tbody id="tbody">
$rows
    </tbody>
  </table>

  <p id="count" style="color:#888;font-size:12px;margin-top:1rem;"></p>

<script>
const rows = [...document.querySelectorAll('#tbody tr')];
const q = document.getElementById('q');
const onlyDiv = document.getElementById('divergent');
const onlyDivRec = document.getElementById('divergentRec');
const count = document.getElementById('count');
function apply() {
  const term = q.value.trim().toLowerCase();
  let shown = 0;
  for (const tr of rows) {
    const matches = !term || tr.textContent.toLowerCase().includes(term);
    const div = !onlyDiv.checked || tr.dataset.unanimous === 'false';
    const divRec = !onlyDivRec.checked || tr.dataset.unanimousRec === 'false';
    const show = matches && div && divRec;
    tr.style.display = show ? '' : 'none';
    if (show) shown++;
  }
  count.textContent = `Showing ${shown} of ${rows.length}`;
}
q.addEventListener('input', apply);
onlyDiv.addEventListener('change', apply);
onlyDivRec.addEventListener('change', apply);
apply();
</script>
</body>
</html>
""")


def render_index(records: list[dict], weights=DEFAULT_WEIGHTS) -> str:
    rows = []
    for r in sorted(records, key=lambda r: r["slug"]):
        title = r["slug"].replace("_", " ").title()
        dilemma = r.get("dilemma") or ""
        preview = dilemma[:130] + ("\u2026" if len(dilemma) > 130 else "")
        cells = []
        for method in METHODS:
            info = r["winners"][method]
            ids = ", ".join(str(i) for i in info["tied_ids"])
            colour = "#B7791F" if len(info["tied_ids"]) > 1 else "#333"
            recs = info.get("tied_recommendations") or []
            rec_line = (
                f'<div style="font-size:11px;margin-top:2px;">{rec_badge(recs[0])}</div>'
                if len(recs) == 1
                else (
                    f'<div style="font-size:10px;margin-top:2px;color:#666;">'
                    f'{html.escape(" / ".join(recs))}</div>'
                    if recs else ""
                )
            )
            cells.append(
                f'<td style="text-align:center;padding:8px 6px;color:{colour};'
                f'font-variant-numeric:tabular-nums;">{ids}{rec_line}</td>'
            )
        def verdict(ok: bool, note: str = "") -> str:
            colour = "#0F6E56" if ok else "#C1121F"
            weight = "400" if ok else "600"
            sub = (
                f'<div style="font-size:10px;color:#888;font-weight:400;margin-top:2px;">{html.escape(note)}</div>'
                if note else ""
            )
            return (
                f'<td style="text-align:center;padding:8px 6px;color:{colour};'
                f'font-weight:{weight};">{"yes" if ok else "no"}{sub}</td>'
            )

        rec_ok = r["unanimous_recommendation"]
        note = ", ".join(r["shared_recommendations"] if rec_ok else r["distinct_recommendations"])
        rows.append(
            f"""<tr data-unanimous="{str(r['unanimous']).lower()}" data-unanimous-rec="{str(rec_ok).lower()}" style="border-bottom:1px solid #eee;">
  <td style="padding:8px 6px;"><a href="{html.escape(r['slug'])}.html" style="color:#185FA5;font-weight:500;text-decoration:none;">{html.escape(title)}</a>
    <div style="color:#888;font-size:12px;margin-top:2px;max-width:430px;">{html.escape(preview)}</div></td>
  {''.join(cells)}
  {verdict(r['unanimous'])}
  {verdict(rec_ok, note)}
</tr>"""
        )
    return INDEX.safe_substitute(
        n=len(records), credences=html.escape(credence_line(weights)), rows="\n".join(rows)
    )


def parse_credences(text: str) -> tuple[float, float, float]:
    parts = [float(eval(p, {"__builtins__": {}})) for p in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("need three comma-separated credences (Ut,De,Ub)")
    total = sum(parts)
    if abs(total - 1.0) > 1e-6:
        raise argparse.ArgumentTypeError(f"credences must sum to 1 (got {total:g})")
    return tuple(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credences", type=parse_credences, default=DEFAULT_WEIGHTS,
        help="Ut,De,Ub credences summing to 1 (default: 1/3 each)",
    )
    parser.add_argument(
        "--out-dir", default=None,
        help="output directory name (default: aggregation_results)",
    )
    args = parser.parse_args()
    weights = tuple(args.credences)
    out_dir = ROOT / args.out_dir if args.out_dir else DEFAULT_OUT_DIR
    summary_file = out_dir / "summary.json"
    index_file = out_dir / "index.html"

    paths = iter_normalized_files()
    if not paths:
        print(f"No normalised scores in {NORMALIZED_DIR}. Run normalize_scores.py first.")
        return 1

    print(f"Reading {len(paths)} normalised score files...")
    print(f"Credences (Ut, De, Ub): {', '.join(f'{w:.4f}' for w in weights)}")
    out_dir.mkdir(parents=True, exist_ok=True)

    records, missing_texts, missing_labels = [], [], []
    for path in paths:
        data = json.load(path.open())
        texts = load_response_texts(data["slug"])
        if not texts:
            missing_texts.append(data["slug"])
        rec = load_recommendation_labels(data["slug"])
        if rec is None:
            missing_labels.append(data["slug"])
        record = build_record(data, texts, rec, weights)
        records.append(record)
        (out_dir / f"{record['slug']}.json").write_text(json.dumps(record, indent=2))
        (out_dir / f"{record['slug']}.html").write_text(render_page(record, texts, weights))

    rel = out_dir.relative_to(ROOT) if out_dir.is_relative_to(ROOT) else out_dir
    print(f"Wrote {len(records)} result files to {rel}/")

    summary = summarise(records, weights)
    summary_file.write_text(json.dumps(summary, indent=2))
    index_file.write_text(render_index(records, weights))
    print(f"Wrote {summary_file.name} and {index_file.name}")

    print(f"\nTies at the top ({summary['dilemmas']} dilemmas):")
    for method, s in summary["per_rule"].items():
        print(f"  {method:9s} {s['dilemmas_with_tie']:4d} ({100 * s['tie_rate']:5.1f}%)  "
              f"mean size {s['mean_tie_size']:.2f}  complete {s['complete_ties']:3d}")

    print("\nPairwise divergence (strict / forced-choice upper bound):")
    for pair, s in summary["pairwise"].items():
        print(f"  {pair:24s} {100 * s['strict_divergence']:5.1f}%  "
              f"{100 * s['forced_divergence']:5.1f}%")

    n = summary["dilemmas"]
    print(f"\nAgreement, two levels (of {n} dilemmas):")
    print(f"  same response       {summary['unanimous']:4d}  "
          f"({100 * summary['unanimous'] / n:.1f}%)")
    print(f"  same recommendation {summary['unanimous_recommendation']:4d}  "
          f"({100 * summary['unanimous_recommendation'] / n:.1f}%)")
    print(f"All four rules have a unique winner in {summary['all_rules_unique_winner']}.")

    failed = False
    if missing_texts:
        print(f"\nWARNING: response text missing for {len(missing_texts)} dilemmas "
              f"(winner text will be blank): {', '.join(missing_texts[:5])}"
              f"{'...' if len(missing_texts) > 5 else ''}")
        failed = True
    if missing_labels:
        print(f"\nWARNING: recommendation labels missing for {len(missing_labels)} dilemmas "
              f"(run label_recommendations.py): {', '.join(missing_labels[:5])}"
              f"{'...' if len(missing_labels) > 5 else ''}")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
