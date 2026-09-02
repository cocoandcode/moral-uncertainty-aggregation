"""
Build scores/index.html — a browsable table of all scored dilemmas.

Links to each per-dilemma dashboard (hover response numbers there for full text).
Safe to re-run any time; only scans scores/*.json (axioms live under scores/axioms/).

  python3 build_index.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
SCORES_DIR = ROOT / "scores"
FILTERED = ROOT / "data" / "filtered_dilemmas.json"
OUT = SCORES_DIR / "index.html"


def load_slug_order() -> dict[str, dict]:
    """slug -> {key, title, ...} from filtered set when available."""
    if not FILTERED.exists():
        return {}
    data = json.load(FILTERED.open())
    return {v["slug"]: {"key": k, **v} for k, v in data.items()}


def iter_score_files() -> list[Path]:
    """Main-study score JSONs only (axioms live under scores/axioms/)."""
    return sorted(SCORES_DIR.glob("*.json"))


def _score_rows(data: dict) -> list[dict] | None:
    rows = data.get("rows") or data.get("scores")
    if not rows:
        return None
    needed = ("utilitarian", "deontological", "ubuntu")
    if not all(k in rows[0] for k in needed):
        return None
    return rows


def summarize(path: Path, meta: dict[str, dict]) -> dict | None:
    try:
        data = json.load(path.open())
    except (json.JSONDecodeError, OSError):
        return None
    rows = _score_rows(data)
    if not rows:
        return None
    slug = data.get("slug") or path.stem
    info = meta.get(slug, {})
    dilemma = data.get("dilemma") or info.get("prompt") or ""
    return {
        "slug": slug,
        "key": info.get("key", ""),
        "title": info.get("title") or slug.replace("_", " ").title(),
        "dilemma": dilemma,
        "n": len(rows),
        "mean_u": round(mean(r["utilitarian"] for r in rows), 1),
        "mean_d": round(mean(r["deontological"] for r in rows), 1),
        "mean_ub": round(mean(r["ubuntu"] for r in rows), 1),
        "href": f"{slug}.html",
    }


def render(rows: list[dict]) -> str:
    n = len(rows)

    def sort_key(r: dict):
        try:
            return (0, int(r["key"]))
        except (TypeError, ValueError):
            return (1, r["title"].lower())

    rows = sorted(rows, key=sort_key)

    body_rows = []
    for r in rows:
        key = html.escape(str(r["key"])) if r["key"] else "—"
        preview = html.escape(r["dilemma"][:140] + ("…" if len(r["dilemma"]) > 140 else ""))
        body_rows.append(
            f"""<tr>
  <td style="padding:8px 6px;color:#888;font-variant-numeric:tabular-nums;">{key}</td>
  <td style="padding:8px 6px;"><a href="{html.escape(r['href'])}" style="color:#185FA5;font-weight:500;text-decoration:none;">{html.escape(r['title'])}</a>
    <div style="color:#888;font-size:12px;margin-top:2px;max-width:420px;">{preview}</div></td>
  <td style="padding:8px 6px;text-align:center;font-variant-numeric:tabular-nums;">{r['n']}</td>
  <td style="padding:8px 6px;text-align:center;font-variant-numeric:tabular-nums;color:#534AB7;">{r['mean_u']}</td>
  <td style="padding:8px 6px;text-align:center;font-variant-numeric:tabular-nums;color:#185FA5;">{r['mean_d']}</td>
  <td style="padding:8px 6px;text-align:center;font-variant-numeric:tabular-nums;color:#0F6E56;">{r['mean_ub']}</td>
</tr>"""
        )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Raw scores — index</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem;">
  <h1 style="margin-bottom:0.25rem;">Raw framework scores</h1>
  <p style="color:#666;margin-top:0.25rem;">
    {n} scored dilemmas · means are over the 16 candidates ·
    open a row for the full table; hover a response number for text.
    Aggregation is deferred until after normalisation.
  </p>

  <div style="margin:1rem 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
    <input id="q" type="search" placeholder="Filter by title or text…"
      style="flex:1;min-width:200px;padding:8px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
  </div>

  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead>
      <tr style="border-bottom:2px solid #ccc;text-align:left;">
        <th style="padding:8px 6px;">#</th>
        <th style="padding:8px 6px;">Dilemma</th>
        <th style="padding:8px 6px;text-align:center;">N</th>
        <th style="padding:8px 6px;text-align:center;color:#534AB7;">Mean U</th>
        <th style="padding:8px 6px;text-align:center;color:#185FA5;">Mean D</th>
        <th style="padding:8px 6px;text-align:center;color:#0F6E56;">Mean Ub</th>
      </tr>
    </thead>
    <tbody id="tbody">
{chr(10).join(body_rows)}
    </tbody>
  </table>

  <p id="count" style="color:#888;font-size:12px;margin-top:1rem;"></p>

<script>
const rows = [...document.querySelectorAll('#tbody tr')];
const q = document.getElementById('q');
const count = document.getElementById('count');

function apply() {{
  const term = q.value.trim().toLowerCase();
  let shown = 0;
  for (const tr of rows) {{
    const text = tr.textContent.toLowerCase();
    const show = !term || text.includes(term);
    tr.style.display = show ? '' : 'none';
    if (show) shown++;
  }}
  count.textContent = `Showing ${{shown}} of ${{rows.length}}`;
}}
q.addEventListener('input', apply);
apply();
</script>
</body>
</html>
"""


def build() -> Path:
    SCORES_DIR.mkdir(exist_ok=True)
    meta = load_slug_order()
    rows = []
    for path in iter_score_files():
        row = summarize(path, meta)
        if row:
            rows.append(row)
    OUT.write_text(render(rows))
    return OUT


def main() -> int:
    path = build()
    print(f"Wrote {path.relative_to(ROOT)} ({sum(1 for _ in iter_score_files())} score files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
