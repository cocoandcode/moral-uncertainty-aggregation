"""Build the distillation train/held-out files from existing scores.

Joins scores/*.json (teacher scores per response id) with responses/*.json
(response text, same ids) and splits by dilemma per the frozen
data/dilemma_split.json (400 train / 100 held-out, seed 42).

Output: distil_data/train.jsonl and distil_data/heldout.jsonl, one row per
response with raw fields only. Prompt formatting is applied at training
time, not here, so the data never has to be regenerated.

No API calls. Deterministic. Run: python build_distil_data.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "distil_data"

FRAMEWORKS = ("utilitarian", "deontological", "ubuntu")


def load_dilemma(slug: str) -> list[dict]:
    scores_doc = json.loads((ROOT / "scores" / f"{slug}.json").read_text())
    resp_doc = json.loads((ROOT / "responses" / f"{slug}.json").read_text())

    assert scores_doc["dilemma"] == resp_doc["dilemma"], slug
    responses_by_id = {r["id"]: r for r in resp_doc["responses"]}

    rows = []
    for s in scores_doc["scores"]:
        resp = responses_by_id[s["id"]]
        row = {
            "slug": slug,
            "id": s["id"],
            "dilemma": scores_doc["dilemma"],
            "response": "\n".join(resp["response"]),
        }
        for fw in FRAMEWORKS:
            score = s[fw]
            assert isinstance(score, int) and 0 <= score <= 10, (slug, s["id"], fw)
            row[fw] = score
        rows.append(row)
    return rows


def main() -> None:
    split = json.loads((ROOT / "data" / "dilemma_split.json").read_text())
    train_slugs, heldout_slugs = split["train"], split["held_out"]
    assert not set(train_slugs) & set(heldout_slugs)

    OUT_DIR.mkdir(exist_ok=True)
    for name, slugs in (("train", train_slugs), ("heldout", heldout_slugs)):
        rows = [row for slug in sorted(slugs) for row in load_dilemma(slug)]
        path = OUT_DIR / f"{name}.jsonl"
        with path.open("w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        print(f"{path}: {len(rows)} rows from {len(slugs)} dilemmas")


if __name__ == "__main__":
    main()
