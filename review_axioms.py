"""
Build a compact, hover-to-expand HTML review of the axiom run.

Joins data/axioms.json (dilemmas + responses) with a results file
(default scores/axiom_results.json) and writes an HTML dashboard grouped
by framework and axiom, so each judge's A/B scores can be eyeballed against
the responses that produced them.

Usage:
  python3 review_axioms.py                         # defaults
  python3 review_axioms.py <results.json> <out.html> [axioms.json]
"""

import html
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "scores" / "axiom_results.json"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "scores" / "axiom_review.html"
AXIOMS = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "data" / "axioms.json"

axioms = json.loads(AXIOMS.read_text())
results = json.loads(RESULTS.read_text())

# group graded cells by dilemma id
by_id = defaultdict(list)
for r in results:
    by_id[r["id"]].append(r)

total = len(results)
passed = sum(r["pass"] for r in results)


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def cell(text: str, cls: str = "") -> str:
    """A truncated span whose full text appears in the hover tooltip."""
    return f'<span class="tip {cls}" data-full="{esc(text)}">{esc(text)}</span>'


parts = []
for fw in axioms["frameworks"]:
    parts.append(f'<h2>{esc(fw["framework"].title())}</h2>')
    for ax in fw["axioms"]:
        rows_here = [r for dl in ax["dilemmas"] for r in by_id.get(dl["id"], [])]
        p = sum(r["pass"] for r in rows_here)
        n = len(rows_here)
        parts.append(
            f'<div class="axiom"><div class="ahead">'
            f'<span class="aid">{esc(ax["axiom_id"])}</span> {esc(ax["axiom"])}'
            f'<span class="ascore">{p}/{n}</span></div>'
        )
        for dl in ax["dilemmas"]:
            parts.append('<div class="dil">')
            parts.append(f'<div class="scen"><b>{esc(dl["id"])}</b> {cell(dl["dilemma"])}</div>')
            parts.append(
                f'<div class="resp"><span class="lbl">A</span> {cell(dl["response_a"])}</div>'
                f'<div class="resp"><span class="lbl">B</span> {cell(dl["response_b"])}</div>'
            )
            graded = by_id.get(dl["id"], [])
            if graded:
                parts.append('<table class="judges"><tr>'
                             '<th>judge</th><th>A</th><th>B</th>'
                             '<th>expected</th><th>actual</th><th></th></tr>')
                for r in graded:
                    a, b = r["score_a"], r["score_b"]
                    ah = ' class="hi"' if isinstance(a, int) and isinstance(b, int) and a > b else ''
                    bh = ' class="hi"' if isinstance(a, int) and isinstance(b, int) and b > a else ''
                    badge = 'pass' if r["pass"] else 'fail'
                    parts.append(
                        f'<tr><td>{esc(r["judge"])}</td>'
                        f'<td{ah}>{esc(a)}</td><td{bh}>{esc(b)}</td>'
                        f'<td>{esc(r["expected"])}</td><td>{esc(r["actual"])}</td>'
                        f'<td class="{badge}">{badge.upper()}</td></tr>'
                    )
                parts.append('</table>')
            parts.append('</div>')
        parts.append('</div>')

body = "\n".join(parts)

HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Axiom review</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px;
         color: #1a1a1a; max-width: 900px; }}
  h1 {{ margin-bottom: 4px; }}
  .sum {{ color: #444; margin-bottom: 18px; }}
  h2 {{ margin: 26px 0 8px; border-bottom: 2px solid #ddd; padding-bottom: 4px;
        text-transform: capitalize; }}
  .axiom {{ margin: 14px 0 18px; }}
  .ahead {{ font-weight: 600; background: #f3f4f6; padding: 7px 10px; border-radius: 6px; }}
  .aid {{ display: inline-block; min-width: 42px; color: #2563eb; }}
  .ascore {{ float: right; color: #555; font-weight: 700; }}
  .dil {{ border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px 12px;
          margin: 8px 0 8px 8px; }}
  .scen {{ color: #333; margin-bottom: 6px; }}
  .resp {{ margin: 2px 0; }}
  .lbl {{ display: inline-block; width: 16px; font-weight: 700; color: #6b7280; }}
  .tip {{ display: inline-block; max-width: 640px; white-space: nowrap; overflow: hidden;
          text-overflow: ellipsis; vertical-align: bottom; cursor: help;
          border-bottom: 1px dotted #cbd5e1; }}
  table.judges {{ border-collapse: collapse; margin-top: 8px; font-size: 14px; }}
  .judges th, .judges td {{ border: 1px solid #e5e7eb; padding: 3px 10px; text-align: center; }}
  .judges th {{ background: #fafafa; color: #555; font-weight: 600; }}
  .judges td:first-child {{ text-align: left; }}
  td.hi {{ font-weight: 800; background: #eef6ff; }}
  td.pass {{ color: #067d3b; font-weight: 700; }}
  td.fail {{ color: #c1121f; font-weight: 700; }}
  #tt {{ position: fixed; z-index: 50; max-width: 460px; background: #111827; color: #f9fafb;
         padding: 8px 10px; border-radius: 6px; font-size: 13px; line-height: 1.35;
         box-shadow: 0 4px 14px rgba(0,0,0,.25); display: none; white-space: normal; }}
</style></head><body>
<h1>Axiom review</h1>
<div class="sum">Source: {esc(RESULTS.name)} &nbsp;|&nbsp; <b>{passed}/{total}</b> predicted cells passed.
Higher A/B score is highlighted. Hover any underlined text for the full wording.</div>
{body}
<div id="tt"></div>
<script>
  const tt = document.getElementById('tt');
  document.querySelectorAll('.tip').forEach(el => {{
    el.addEventListener('mouseenter', e => {{ tt.textContent = el.dataset.full; tt.style.display = 'block'; }});
    el.addEventListener('mousemove', e => {{
      tt.style.left = Math.min(e.clientX + 14, window.innerWidth - 470) + 'px';
      tt.style.top  = (e.clientY + 16) + 'px';
    }});
    el.addEventListener('mouseleave', () => {{ tt.style.display = 'none'; }});
  }});
</script>
</body></html>
"""

OUT.write_text(HTML)
print(f"Wrote {OUT.relative_to(ROOT)}  ({passed}/{total} cells)")
