"""Step 7: the ceiling - how well does the teacher agree with itself?

Re-scores a sample of held-out responses with gpt-4o-mini using the exact
judge prompts and scoring call from the main pipeline, then compares the
fresh scores to the originals in scores/*.json. No student can honestly
agree with the teacher more than the teacher agrees with itself, so these
numbers are the upper bound against which the student metrics are read.

Design: 13 whole held-out dilemmas (208 responses, ~624 API calls) rather
than scattered responses, so the teacher's WITHIN-DILEMMA tau against
itself is computable - the calibration the students' tau column needs.
The students' metrics are also recomputed on the same 13 dilemmas, so the
comparison is on identical data.

Failed API calls are retried once, then recorded as null and excluded
from metrics (never the main pipeline's fallback-of-5, which would
contaminate the ceiling).

Output: distil_eval/ceiling.rescored.jsonl, distil_eval/ceiling.metrics.json

Run:  set -a && . ./.env && set +a && python3 ceiling_distil.py
"""

import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
from openai import OpenAI

from eval_distil import metrics
from score_responses import FRAMEWORKS as JUDGE_PROMPTS
from score_responses import score_response

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "distil_eval"
FRAMEWORKS = ("utilitarian", "deontological", "ubuntu")
SEED = 42
N_DILEMMAS = 13


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print('ERROR: export OPENAI_API_KEY or source .env first')
        return 1
    client = OpenAI()

    rows = [json.loads(l)
            for l in (ROOT / "distil_data" / "heldout.jsonl").open()]
    slugs = sorted({r["slug"] for r in rows})
    sample_slugs = set(random.Random(SEED).sample(slugs, N_DILEMMAS))
    sample = [r for r in rows if r["slug"] in sample_slugs]
    print(f"re-scoring {len(sample)} responses from {N_DILEMMAS} dilemmas "
          f"({3 * len(sample)} API calls)")

    out_path = OUT_DIR / "ceiling.rescored.jsonl"
    rescored = []
    t0 = time.time()
    with out_path.open("w") as f:
        for i, r in enumerate(sample):
            entry = {"slug": r["slug"], "id": r["id"]}
            for fw in FRAMEWORKS:
                s = score_response(client, r["response"],
                                   JUDGE_PROMPTS[fw], r["dilemma"])
                if s is None:
                    time.sleep(2)
                    s = score_response(client, r["response"],
                                       JUDGE_PROMPTS[fw], r["dilemma"])
                entry[fw] = s  # may be None; excluded from metrics
            rescored.append(entry)
            f.write(json.dumps(entry) + "\n")
            if (i + 1) % 20 == 0:
                rate = (i + 1) / (time.time() - t0)
                print(f"  {i + 1}/{len(sample)} responses "
                      f"({rate:.1f} resp/s)", flush=True)

    report = {"n_dilemmas": N_DILEMMAS, "n_responses": len(sample),
              "sampled_slugs": sorted(sample_slugs),
              "teacher_self_agreement": {}, "student_same_subset": {}}

    # Teacher vs itself on the sample (skip failed calls).
    for fw in FRAMEWORKS:
        ok = [(r, e[fw]) for r, e in zip(sample, rescored)
              if e[fw] is not None]
        rows_ok = [r for r, _ in ok]
        fresh = np.array([s for _, s in ok], dtype=float)
        m = metrics(rows_ok, fw, fresh)
        m["n_failed_calls"] = len(sample) - len(ok)
        m["exact_match_rate"] = round(float(np.mean(
            [s == r[fw] for r, s in ok])), 4)
        report["teacher_self_agreement"][fw] = m
        print(f"teacher-vs-itself {fw}: {json.dumps(m)}")

    # Students vs teacher on the same 13 dilemmas.
    for fw in FRAMEWORKS:
        preds = {}
        path = OUT_DIR / f"{fw}_classification.predictions.jsonl"
        for line in path.open():
            p = json.loads(line)
            preds[(p["slug"], p["id"])] = p["student_ev"]
        student = np.array([preds[(r["slug"], r["id"])] for r in sample])
        m = metrics(sample, fw, student)
        report["student_same_subset"][fw] = m
        print(f"student-vs-teacher {fw} (same subset): {json.dumps(m)}")

    (OUT_DIR / "ceiling.metrics.json").write_text(json.dumps(report, indent=2))
    print(f"saved {OUT_DIR / 'ceiling.metrics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
