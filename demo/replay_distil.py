"""Step 5: replay aggregation with the distilled judges' scores.

Question: if the three gpt-4o-mini judges were swapped for their Qwen
copies, would the aggregation rules pick different winners on the 100
held-out dilemmas?

Student side mirrors the real pipeline end to end, as a deployment would:
integer scores (rounded expected value, the frozen decoding rule) ->
global per-judge z-stats computed over the student's own scored corpus
(the 1,600 held-out responses) -> the same aggregation.py rules ->
winner sets with ties kept. The teacher side is the published
aggregation_results/ records for the same dilemmas. The bag-of-words
floor is replayed through the identical path for context.

Reported per rule:
  overlap        teacher and student winner sets share >= 1 response
  exact          winner sets identical
  strict_div     winner sets disjoint (no tie-break could reconcile)
  rec_agree      winner sets share a recommendation label (weaker: same
                 action even if a different response)

Plus each pipeline's internal rule-vs-rule divergence table, to check the
copies reproduce the dissertation's headline structure.

Output: distil_eval/replay.metrics.json

Run:  python3 replay_distil.py
"""

import itertools
import json
import statistics
from collections import defaultdict
from pathlib import Path

from aggregation import DEFAULT_WEIGHTS, FRAMEWORKS, METHODS, compute_row, pick_winners

ROOT = Path(__file__).resolve().parent
EVAL_DIR = ROOT / "distil_eval"
AGG_DIR = ROOT / "aggregation_results"
REC_DIR = ROOT / "recommendations"


def load_predictions(pattern: str) -> dict:
    """pattern has one {fw} slot; returns slug -> id -> {fw: int score}."""
    by_slug: dict = defaultdict(lambda: defaultdict(dict))
    for fw in FRAMEWORKS:
        path = EVAL_DIR / f"{pattern.format(fw=fw)}.predictions.jsonl"
        for line in path.open():
            r = json.loads(line)
            by_slug[r["slug"]][r["id"]][fw] = r["student_int"]
    return by_slug


def build_winner_sets(by_slug: dict) -> dict:
    """Run the pipeline's normalisation + aggregation on integer scores."""
    values = {fw: [row[fw] for rows in by_slug.values() for row in rows.values()]
              for fw in FRAMEWORKS}
    stats = {fw: (statistics.mean(v), statistics.pstdev(v))
             for fw, v in values.items()}

    winners_by_slug = {}
    for slug, rows_by_id in by_slug.items():
        rows = []
        for rid in sorted(rows_by_id):
            raw = rows_by_id[rid]
            row = {
                "id": rid,
                "raw": raw,
                "z": {fw: (raw[fw] - stats[fw][0]) / stats[fw][1]
                      for fw in FRAMEWORKS},
                "nash_surplus": {fw: raw[fw] / stats[fw][1]
                                 for fw in FRAMEWORKS},
            }
            rows.append(compute_row(row, DEFAULT_WEIGHTS))
        winners = pick_winners(rows)
        winners_by_slug[slug] = {m: set(w["tied_ids"])
                                 for m, w in winners.items()}
    return winners_by_slug


def load_teacher(slugs: list) -> dict:
    winners_by_slug = {}
    for slug in slugs:
        rec = json.loads((AGG_DIR / f"{slug}.json").read_text())
        winners_by_slug[slug] = {m: set(w["tied_ids"])
                                 for m, w in rec["winners"].items()}
    return winners_by_slug


def load_labels(slugs: list) -> dict:
    labels = {}
    for slug in slugs:
        path = REC_DIR / f"{slug}.json"
        by_id = {}
        if path.exists():
            data = json.loads(path.read_text())
            by_id = {row["id"]: row["label"] for row in data.get("labels", [])}
        labels[slug] = by_id
    return labels


def compare(teacher: dict, student: dict, labels: dict) -> dict:
    slugs = sorted(teacher)
    n = len(slugs)
    per_rule = {}
    for m in METHODS:
        overlap = exact = strict = rec_agree = 0
        for slug in slugs:
            ts, ss = teacher[slug][m], student[slug][m]
            if ts & ss:
                overlap += 1
            if ts == ss:
                exact += 1
            if ts.isdisjoint(ss):
                strict += 1
            by_id = labels[slug]
            t_recs = {by_id[i] for i in ts if i in by_id}
            s_recs = {by_id[i] for i in ss if i in by_id}
            if t_recs & s_recs:
                rec_agree += 1
        per_rule[m] = {
            "overlap": round(overlap / n, 4),
            "exact_set": round(exact / n, 4),
            "strict_divergence": round(strict / n, 4),
            "rec_agree": round(rec_agree / n, 4),
        }
    return per_rule


def internal_divergence(winners_by_slug: dict) -> dict:
    slugs = sorted(winners_by_slug)
    n = len(slugs)
    out = {}
    for a, b in itertools.combinations(METHODS, 2):
        strict = sum(1 for s in slugs
                     if winners_by_slug[s][a].isdisjoint(winners_by_slug[s][b]))
        out[f"{a}_vs_{b}"] = round(strict / n, 4)
    unanimous = sum(1 for s in slugs
                    if set.intersection(*winners_by_slug[s].values()))
    out["unanimous_response"] = round(unanimous / n, 4)
    return out


def main() -> None:
    student = build_winner_sets(load_predictions("{fw}_classification"))
    floor = build_winner_sets(load_predictions("floor_bow_{fw}"))
    slugs = sorted(student)
    teacher = load_teacher(slugs)
    labels = load_labels(slugs)
    print(f"{len(slugs)} held-out dilemmas")

    report = {
        "n_dilemmas": len(slugs),
        "student_vs_teacher": compare(teacher, student, labels),
        "floor_vs_teacher": compare(teacher, floor, labels),
        "internal_divergence": {
            "teacher": internal_divergence(teacher),
            "student": internal_divergence(student),
            "floor": internal_divergence(floor),
        },
        "notes": "Teacher = published aggregation_results (global z-stats "
                 "from all 500 dilemmas). Student/floor = same pipeline on "
                 "rounded-EV integer scores with z-stats from their own "
                 "1,600 held-out scores. Overlap = winner sets share a "
                 "response; rec_agree = winner sets share a recommendation "
                 "label.",
    }
    (EVAL_DIR / "replay.metrics.json").write_text(json.dumps(report, indent=2))

    for side in ("student_vs_teacher", "floor_vs_teacher"):
        print(f"\n{side}:")
        for m, r in report[side].items():
            print(f"  {m:9s} overlap {r['overlap']:.2f}  exact {r['exact_set']:.2f}  "
                  f"strict-div {r['strict_divergence']:.2f}  rec-agree {r['rec_agree']:.2f}")
    print("\ninternal rule-vs-rule strict divergence (teacher | student | floor):")
    t = report["internal_divergence"]
    for key in t["teacher"]:
        print(f"  {key:24s} {t['teacher'][key]:.2f} | {t['student'][key]:.2f} | {t['floor'][key]:.2f}")
    print(f"\nsaved {EVAL_DIR / 'replay.metrics.json'}")


if __name__ == "__main__":
    main()
