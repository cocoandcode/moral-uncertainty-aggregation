"""The distillation floor: bag-of-words ridge regression.

Rebuild of the unsaved 21 Aug 2026 pilot, so the floor numbers cited in
the write-up come from code that exists. A linear model predicts each
judge's score from word counts of the RESPONSE TEXT ONLY - no dilemma, no
word order, no meaning. Anything a real student model scores must beat
this, or it has learned nothing beyond vocabulary statistics.

Same data split and the same metrics function as eval_distil.py, so the
numbers are directly comparable with the Qwen adapters.

Outputs to distil_eval/:
    floor_bow_<framework>.predictions.jsonl
    floor_bow.metrics.json

Run:  python3 distil_floor.py
"""

import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge

from eval_distil import metrics

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "distil_eval"
FRAMEWORKS = ("utilitarian", "deontological", "ubuntu")

MAX_FEATURES = 20000
ALPHA = 1.0


def main() -> None:
    train = [json.loads(l)
             for l in (ROOT / "distil_data" / "train.jsonl").open()]
    heldout = [json.loads(l)
               for l in (ROOT / "distil_data" / "heldout.jsonl").open()]
    OUT_DIR.mkdir(exist_ok=True)

    vec = TfidfVectorizer(max_features=MAX_FEATURES)
    x_train = vec.fit_transform(r["response"] for r in train)
    x_heldout = vec.transform(r["response"] for r in heldout)
    print(f"train {x_train.shape}  heldout {x_heldout.shape}")

    all_metrics = {}
    for fw in FRAMEWORKS:
        y_train = np.array([r[fw] for r in train], dtype=float)
        model = Ridge(alpha=ALPHA)
        model.fit(x_train, y_train)
        preds = model.predict(x_heldout)

        with (OUT_DIR / f"floor_bow_{fw}.predictions.jsonl").open("w") as f:
            for r, s in zip(heldout, preds):
                f.write(json.dumps({
                    "slug": r["slug"], "id": r["id"], "teacher": r[fw],
                    "student_ev": round(float(s), 4),
                    "student_int": int(np.clip(round(float(s)), 0, 10)),
                }) + "\n")

        m = metrics(heldout, fw, preds)
        all_metrics[fw] = m
        print(f"{fw}: {json.dumps(m)}")

    out = {
        "model": f"TfidfVectorizer(max_features={MAX_FEATURES}) + "
                 f"Ridge(alpha={ALPHA})",
        "features": "response text only (no dilemma)",
        "note": "Rebuild of the unsaved 21 Aug pilot (which reported "
                "Pearson 0.68/0.53/0.64 Ut/De/Ub). Cite these numbers, "
                "not the pilot's.",
        "metrics": all_metrics,
    }
    (OUT_DIR / "floor_bow.metrics.json").write_text(json.dumps(out, indent=2))
    print(f"saved {OUT_DIR / 'floor_bow.metrics.json'}")


if __name__ == "__main__":
    main()
