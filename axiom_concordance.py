"""Fill the ungraded cells of the axiom grid.

test_axioms.py scores every pair under all three judges but discards any
cell without a directional prediction (grade() skips `expected is None`),
so the blanks in the published grid are ungraded rather than unrun. This
script re-scores all 45 main-bank pairs under all three judges and keeps
every cell, then grades them two ways:

  own      each judge against its own prediction, where one exists
           (reproduces the published grid, one run rather than five)
  owner    each judge against the OWNER framework's prediction, i.e.
           "how often does judge J deliver the verdict framework F's
           axioms predict on F's own pairs" -- a concordance measure
           needing no prediction for J, so every cell is fillable

A failed call is retried once and then recorded as null. No fallback
score is ever invented.

Writes scores/axioms/axiom_concordance.json. Touches nothing else.

Run:  set -a && . ./.env && set +a
      python3 axiom_concordance.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from openai import OpenAI

from score_responses import FRAMEWORKS, score_response

ROOT = Path(__file__).resolve().parent
AXIOMS_FILE = ROOT / "data" / "axioms.json"
OUT_FILE = ROOT / "scores" / "axioms" / "axiom_concordance.json"

JUDGES = ("utilitarian", "deontological", "ubuntu")
SET_CODE = {"utilitarian": "Ut", "deontological": "De", "ubuntu": "Ub"}
TOLERANCE = 0


def outcome(a: int | None, b: int | None, tol: int = TOLERANCE) -> str:
    if a is None or b is None:
        return "error"
    if a - b > tol:
        return "a > b"
    if b - a > tol:
        return "b > a"
    return "a ≈ b"


def score_once(client: OpenAI, text: str, prompt: str, scenario: str) -> int | None:
    s = score_response(client, text, prompt, scenario)
    if s is None:
        time.sleep(2)
        s = score_response(client, text, prompt, scenario)
    return s


def main() -> int:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("ERROR: OPENAI_API_KEY not set "
              "(set -a && . ./.env && set +a)")
        return 1
    client = OpenAI(api_key=key)

    data = json.loads(AXIOMS_FILE.read_text())
    pairs = [
        {"owner": fw["framework"], "axiom_id": ax["axiom_id"], **d}
        for fw in data["frameworks"]
        for ax in fw["axioms"]
        for d in ax["dilemmas"]
    ]
    total_calls = len(pairs) * 2 * len(JUDGES)
    print(f"{len(pairs)} pairs x 2 responses x {len(JUDGES)} judges "
          f"= {total_calls} calls")

    cells, failures = [], 0
    t0 = time.time()
    for n, p in enumerate(pairs, 1):
        print(f"\n[{n}/{len(pairs)}] {p['id']} (owner {p['owner']})",
              flush=True)
        for judge in JUDGES:
            prompt = FRAMEWORKS[judge]
            sa = score_once(client, p["response_a"], prompt, p["dilemma"])
            sb = score_once(client, p["response_b"], prompt, p["dilemma"])
            if sa is None or sb is None:
                failures += 1
                print(f"  {judge:<14} NULL (call failed twice)")
            act = outcome(sa, sb)
            cells.append({
                "pair_id": p["id"],
                "axiom_id": p["axiom_id"],
                "set": SET_CODE[p["owner"]],
                "owner": p["owner"],
                "judge": judge,
                "score_a": sa,
                "score_b": sb,
                "actual": act,
                "own_prediction": p["expected"][judge],
                "owner_prediction": p["expected"][p["owner"]],
                "graded_in_thesis": p["expected"][judge] is not None,
            })
            print(f"  {judge:<14} a={sa} b={sb} -> {act}")

    # ── grid 1: each judge against its own prediction ──────────
    own = defaultdict(lambda: [0, 0])
    for c in cells:
        if c["own_prediction"] is None:
            continue
        k = (c["judge"], c["set"])
        own[k][1] += 1
        own[k][0] += c["actual"] == c["own_prediction"]

    # ── grid 2: each judge against the owner's prediction ──────
    owner = defaultdict(lambda: [0, 0, 0])
    for c in cells:
        k = (c["judge"], c["set"])
        owner[k][1] += 1
        owner[k][0] += c["actual"] == c["owner_prediction"]
        owner[k][2] += c["actual"] == "a ≈ b"

    def show(title, grid, width):
        print(f"\n{title}")
        print(f"{'judge':<14}" + "".join(f"{s:>16}" for s in
                                         ("Ut pairs", "De pairs", "Ub pairs")))
        for j in JUDGES:
            row = f"{j:<14}"
            for s in ("Ut", "De", "Ub"):
                v = grid.get((j, s))
                if not v or v[1] == 0:
                    row += f"{'—':>16}"
                else:
                    pct = 100 * v[0] / v[1]
                    cell = f"{pct:.0f}% ({v[0]}/{v[1]})"
                    if width == 3 and v[2]:
                        cell += f" t{v[2]}"
                    row += f"{cell:>16}"
            print(row)

    print("\n" + "=" * 74)
    show("GRID 1 — judge vs its OWN prediction (thesis Table 4.2, 1 run)",
         own, 2)
    show("GRID 2 — judge vs the OWNER framework's prediction "
         "(t = ties, which count as misses)", owner, 3)

    diag = sum(v[0] for (j, s), v in own.items() if SET_CODE[j] == s)
    diag_n = sum(v[1] for (j, s), v in own.items() if SET_CODE[j] == s)
    print(f"\nown-prediction diagonal: {diag}/{diag_n}")
    print(f"own-prediction all cells: {sum(v[0] for v in own.values())}"
          f"/{sum(v[1] for v in own.values())}")
    print(f"null cells (failed twice): {failures}")
    print(f"elapsed: {(time.time() - t0) / 60:.1f} min")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        "note": "Single run, temperature 0.1. Published grid (Table 4.2) is "
                "a mean over five runs, so GRID 1 here will differ slightly. "
                "Not part of the submitted results.",
        "model_prompts_from": "score_responses.py FRAMEWORKS (frozen)",
        "tolerance": TOLERANCE,
        "n_pairs": len(pairs),
        "n_calls": total_calls,
        "null_cells": failures,
        "grid_own_prediction": {f"{j}|{s}": v for (j, s), v in own.items()},
        "grid_owner_prediction": {f"{j}|{s}": v for (j, s), v in owner.items()},
        "cells": cells,
    }, indent=2, ensure_ascii=False))
    print(f"written: {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
