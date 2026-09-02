"""Step 6: the axiom exam for the distilled judges.

The test that counts. Each axiom pair is two responses to one scenario
that differ only in a morally relevant fact, with a predicted preference
direction per judge (data/axioms.json, 45 pairs, 75 non-null predictions;
data/axioms_heldout.json, 6 pairs, reported separately). A judge copy
that merely learned style scores at chance here; one that learned the
framework shows the teacher's diagonal pattern.

Grading mirrors test_axioms.py exactly: each response is scored
independently together with its scenario, and a predicted cell passes
when the sign of the score difference matches the prediction. A tie
fails. Students decode by expected value (frozen rule), which is
continuous, so exact ties are effectively impossible for them - noted in
the output as a mild asymmetry versus the integer-scoring teacher.

Exam-takers: the three classification adapters (deterministic, so one
run suffices, unlike the teacher's five) and the rebuilt bag-of-words
floor. The teacher's published grid (MUA.tex tab:grid) is included for
reference.

Output: distil_eval/axioms.metrics.json

Run:  python3 axiom_distil.py
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from eval_distil import pick_device, predict

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "distil_eval"
FRAMEWORKS = ("utilitarian", "deontological", "ubuntu")
PREFIXES = ("Ut", "De", "Ub")

# Teacher reference: mean pass rates over five runs, MUA.tex tab:grid.
TEACHER_GRID = {
    "utilitarian": {"Ut": "97% (15)", "De": "63% (12)", "Ub": "67% (3)"},
    "deontological": {"Ut": "100% (6)", "De": "100% (15)", "Ub": "33% (6)"},
    "ubuntu": {"Ut": None, "De": "100% (3)", "Ub": "100% (15)"},
}


def load_pairs() -> list:
    pairs = []
    for source, fname in (("main", "axioms.json"),
                          ("heldout", "axioms_heldout.json")):
        data = json.loads((ROOT / "data" / fname).read_text())
        for fw in data["frameworks"]:
            for ax in fw["axioms"]:
                for d in ax["dilemmas"]:
                    pairs.append({
                        "pair_id": d["id"],
                        "set_prefix": fw["prefix"],
                        "source": source,
                        "dilemma": d["dilemma"],
                        "response_a": d["response_a"],
                        "response_b": d["response_b"],
                        "expected": d["expected"],
                    })
    return pairs


def score_with_students(pairs: list) -> dict:
    """{judge: {pair_id: (score_a, score_b)}} via the Qwen adapters."""
    device = pick_device()
    rows = []
    for p in pairs:
        for side in ("a", "b"):
            rows.append({"slug": p["pair_id"], "id": side,
                         "dilemma": p["dilemma"],
                         "response": p[f"response_{side}"]})
    out = {}
    for fw in FRAMEWORKS:
        scores = predict(f"{fw}_classification", rows, device, 8)
        by_pair = defaultdict(dict)
        for row, s in zip(rows, scores):
            by_pair[row["slug"]][row["id"]] = float(s)
        out[fw] = {pid: (v["a"], v["b"]) for pid, v in by_pair.items()}
    return out


def score_with_floor(pairs: list) -> dict:
    """Same, via the rebuilt bag-of-words ridge (response text only)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import Ridge
    from distil_floor import ALPHA, MAX_FEATURES

    train = [json.loads(l)
             for l in (ROOT / "distil_data" / "train.jsonl").open()]
    vec = TfidfVectorizer(max_features=MAX_FEATURES)
    x_train = vec.fit_transform(r["response"] for r in train)

    texts = [p[f"response_{side}"] for p in pairs for side in ("a", "b")]
    x_axioms = vec.transform(texts)

    out = {}
    for fw in FRAMEWORKS:
        model = Ridge(alpha=ALPHA)
        model.fit(x_train, np.array([r[fw] for r in train], dtype=float))
        preds = model.predict(x_axioms)
        out[fw] = {p["pair_id"]: (float(preds[2 * i]), float(preds[2 * i + 1]))
                   for i, p in enumerate(pairs)}
    return out


def grade(pairs: list, scores: dict) -> tuple[list, dict]:
    """Grade every non-null prediction; build the 3x3 grid per source."""
    cells = []
    for p in pairs:
        for judge in FRAMEWORKS:
            expected = p["expected"].get(judge)
            if expected is None:
                continue
            sa, sb = scores[judge][p["pair_id"]]
            if sa > sb:
                actual = "a > b"
            elif sb > sa:
                actual = "b > a"
            else:
                actual = "a ≈ b"
            cells.append({
                "pair_id": p["pair_id"], "set": p["set_prefix"],
                "source": p["source"], "judge": judge,
                "score_a": round(sa, 4), "score_b": round(sb, 4),
                "expected": expected, "actual": actual,
                "pass": actual == expected,
            })

    grids = {}
    for source in ("main", "heldout"):
        grid = {}
        for judge in FRAMEWORKS:
            grid[judge] = {}
            for prefix in PREFIXES:
                sub = [c for c in cells if c["source"] == source
                       and c["judge"] == judge and c["set"] == prefix]
                if not sub:
                    grid[judge][prefix] = None
                    continue
                passed = sum(c["pass"] for c in sub)
                grid[judge][prefix] = f"{100 * passed / len(sub):.0f}% ({len(sub)})"
        subset = [c for c in cells if c["source"] == source]
        diag = [c for c in subset
                if PREFIXES[FRAMEWORKS.index(c["judge"])] == c["set"]]
        grid["_overall"] = {
            "all_cells": f"{sum(c['pass'] for c in subset)}/{len(subset)}",
            "diagonal": f"{sum(c['pass'] for c in diag)}/{len(diag)}",
        }
        grids[source] = grid
    return cells, grids


def show(name: str, grid: dict) -> None:
    print(f"\n{name} (main set):")
    print(f"  {'judge':15s} {'Ut axioms':>12s} {'De axioms':>12s} {'Ub axioms':>12s}")
    for judge in FRAMEWORKS:
        row = grid[judge]
        print(f"  {judge:15s} " + " ".join(
            f"{(row[p] or '---'):>12s}" for p in PREFIXES))
    print(f"  overall {grid['_overall']['all_cells']}, "
          f"diagonal {grid['_overall']['diagonal']}")


def main() -> None:
    pairs = load_pairs()
    n_main = sum(1 for p in pairs if p["source"] == "main")
    print(f"{len(pairs)} pairs ({n_main} main, {len(pairs) - n_main} held-out)")

    student_cells, student_grids = grade(pairs, score_with_students(pairs))
    floor_cells, floor_grids = grade(pairs, score_with_floor(pairs))

    show("STUDENTS (Qwen adapters)", student_grids["main"])
    show("FLOOR (bag-of-words ridge)", floor_grids["main"])
    print("\nTeacher reference (mean of 5 runs, MUA.tex tab:grid):")
    for judge in FRAMEWORKS:
        row = TEACHER_GRID[judge]
        print(f"  {judge:15s} " + " ".join(
            f"{(row[p] or '---'):>12s}" for p in PREFIXES))

    print("\nHeld-out pairs (never used in prompt iteration):")
    show("STUDENTS", student_grids["heldout"])
    show("FLOOR", floor_grids["heldout"])

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "axioms.metrics.json").write_text(json.dumps({
        "student_grids": student_grids,
        "floor_grids": floor_grids,
        "teacher_reference": TEACHER_GRID,
        "student_cells": student_cells,
        "floor_cells": floor_cells,
        "notes": "Pass = sign of score difference matches prediction; tie "
                 "fails (test_axioms.py criterion, tolerance 0). Students "
                 "decode by expected value, so ties are effectively "
                 "impossible for them; the integer-scoring teacher can tie "
                 "and fail. Students are deterministic (one run); teacher "
                 "grid is a mean over five stochastic runs.",
    }, indent=2, ensure_ascii=False))
    print(f"\nsaved {OUT_DIR / 'axioms.metrics.json'}")


if __name__ == "__main__":
    main()
