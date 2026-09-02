"""
Re-render scores/<slug>.html from existing scores/<slug>.json (no API calls).

Use after template changes, or before opening the index.

  python3 rebuild_score_html.py
"""

from __future__ import annotations

import json

from build_index import SCORES_DIR, build
from score_responses import render_html


def main() -> int:
    n = 0
    for path in sorted(SCORES_DIR.glob("*.json")):
        data = json.load(path.open())
        rows = data.get("rows")
        if not rows:
            # Older files: scores without embedded response text
            scores = data.get("scores")
            if not scores:
                continue
            rows = scores
        slug = data.get("slug") or path.stem
        title = slug.replace("_", " ").title()
        render_html(
            title,
            rows,
            SCORES_DIR / f"{slug}.html",
            dilemma=data.get("dilemma") or "",
            judge_model=data.get("judge_model"),
        )
        n += 1
    build()
    print(f"Rebuilt {n} dilemma pages + index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
