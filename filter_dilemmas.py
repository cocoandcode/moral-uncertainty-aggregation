"""
Filter `data/daily_dilemmas.json` for dilemmas where the three ethical
frameworks (utilitarian, deontological, ubuntu) would disagree, and
reformat them as open-ended prompts compatible with `generate_responses.py`.

How it works
------------
Each row in the source corpus describes one side of a binary dilemma
(`action_type` is either "to_do" or "not_to_do") and carries a list of
values that implicitly back that action. Two rows with the same
`dilemma_idx` form a complete dilemma.

Values are mapped to the three frameworks via keyword sets below. For
each dilemma we count framework-aligned values on each side (these are
keyword match counts, NOT the 0-10 ethical scores produced later by
score_responses.py). Each framework "prefers" the side with more aligned
values (or is neutral on a tie). A dilemma is kept iff the frameworks
split — at least one framework prefers `to_do`, at least one prefers
`not_to_do`.

Each kept dilemma is described by two numbers (see NOTES.md §1 for the
rationale and the rejected single-number alternatives):
  - balance:    1 - |mean of the per-framework smoothed leans|. How torn
                the frameworks are; 1.0 = perfect deadlock. Only meaningful
                after the split gate above.
  - confidence: total matched values across frameworks. How much evidence
                backs the leans; guards against thin, noisy "deadlocks".
Results are sorted by balance, then confidence.

Caveats
-------
The mapping is heuristic. It catches dilemmas that are likely to
generate framework disagreement, not ones that are guaranteed to.

Usage
-----
  python3 filter_dilemmas.py
  python3 filter_dilemmas.py --limit 50               # top 50 by balance
  python3 filter_dilemmas.py --min-confidence 4       # drop thin evidence
  python3 filter_dilemmas.py --output data/filtered_dilemmas.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_FILE = ROOT / "data" / "daily_dilemmas.json"
DEFAULT_OUTPUT = ROOT / "data" / "filtered_dilemmas.json"

# ── Value → framework mapping ────────────────────────────────
# Lower-case keywords. Matching is substring-based on the cleaned value
# string, so e.g. "respect for privacy" matches both the full phrase and
# the bare "privacy" keyword.

UTILITARIAN_KEYWORDS = {
    "wellbeing", "well-being", "welfare", "happiness", "satisfaction",
    "survival", "health", "safety", "comfort", "relief", "peace",
    "peace of mind", "efficiency", "productivity", "profit",
    "profitability", "financial stability", "financial security",
    "job security", "stability", "protection", "prosperity",
    "outcome", "harm reduction", "resilience",
}

DEONTOLOGICAL_KEYWORDS = {
    "honesty", "integrity", "fairness", "justice", "lawfulness",
    "duty", "accountability", "responsibility", "transparency",
    "respect for rules", "professionalism", "professional integrity",
    "professional responsibility", "trust", "trustworthiness",
    "respect", "dignity", "autonomy", "right to life",
    "right to privacy", "right to information", "right to autonomy",
    "respect for privacy", "respect for autonomy", "respect for life",
    "freedom", "freedom of expression", "consent", "truth",
    "open communication", "discipline",
}

UBUNTU_KEYWORDS = {
    "compassion", "empathy", "solidarity", "unity", "teamwork",
    "cooperation", "support", "care", "concern", "generosity",
    "love", "loyalty", "kinship", "community", "togetherness",
    "selflessness", "sacrifice", "understanding", "tolerance",
    "patience", "guidance", "consideration", "respect for diversity",
    "respect for others", "friendship", "mutual aid",
}

FRAMEWORK_KEYWORDS = {
    "utilitarian": UTILITARIAN_KEYWORDS,
    "deontological": DEONTOLOGICAL_KEYWORDS,
    "ubuntu": UBUNTU_KEYWORDS,
}


def load_rows(path: Path) -> list[dict]:
    """Load a JSONL file (one JSON object per line)."""
    rows = []
    with path.open() as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  warn: skipping malformed line {line_num}: {e}", file=sys.stderr)
    return rows


def parse_values(raw: str) -> list[str]:
    """`values_aggregated` is a stringified Python list. Parse defensively."""
    if not isinstance(raw, str):
        return []
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, (list, tuple)):
            return [str(v).strip().lower() for v in parsed if v]
    except (ValueError, SyntaxError):
        pass
    return []


def count_value_matches(values: list[str]) -> dict[str, int]:
    """Count how many of a side's values map to each framework's keywords."""
    matches = {f: 0 for f in FRAMEWORK_KEYWORDS}
    for value in values:
        for framework, keywords in FRAMEWORK_KEYWORDS.items():
            if any(kw in value for kw in keywords):
                matches[framework] += 1
                break  # one value, one framework — avoid double counting
    return matches


def preference(to_do_matches: int, not_to_do_matches: int) -> str:
    if to_do_matches > not_to_do_matches:
        return "to_do"
    if not_to_do_matches > to_do_matches:
        return "not_to_do"
    return "neutral"


# ── Disagreement metric ──────────────────────────────────────
# We report TWO separate numbers rather than collapsing them:
#   - balance:    how torn the frameworks are (0 = consensus, 1 = deadlock)
#   - confidence: how much evidence backs the leans (total matched values)
# See NOTES.md §1 for why a single "disagreement_strength" was dropped.

LEAN_SMOOTHING = 1  # additive constant; damps tiny-denominator leans (e.g. 0-1)


def smoothed_lean(to_do_matches: int, not_to_do_matches: int) -> float:
    """Signed lean in [-1, +1]. +1 = fully to_do, -1 = fully not_to_do.

    The +LEAN_SMOOTHING in the denominator means more evidence yields a
    stronger lean (5-0 -> 0.83) while a single value stays tentative
    (1-0 -> 0.5), and a 0-0 side is exactly neutral.
    """
    return (to_do_matches - not_to_do_matches) / (
        to_do_matches + not_to_do_matches + LEAN_SMOOTHING
    )


def balance_score(leans: list[float]) -> float:
    """How close the leans are to cancelling out. 1 = perfect deadlock.

    NOTE: only meaningful *after* the split gate in filter_dilemmas(); a mean
    of 0 can also arise when every framework is neutral (no disagreement).
    """
    mean = sum(leans) / len(leans)
    return round(1 - abs(mean), 4)


# ── Prompt reformatting ──────────────────────────────────────
# We keep the FULL original dilemma text and only append an open-ended ask.
# An earlier version stripped the trailing question, but in this dataset that
# sentence *is* the dilemma (it states the fork, e.g. "do X, or Y?"), so
# stripping flattened ~99% of prompts into trivial ones. See NOTES.md.


def reformat_as_open_ended(dilemma_situation: str) -> str | None:
    text = dilemma_situation.strip()
    if not text:
        return None
    return f"{text}\n\nGive a clear recommendation and explain your reasoning."


# ── Filtering ────────────────────────────────────────────────


def filter_dilemmas(rows: list[dict]) -> list[dict]:
    grouped: dict[int, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        action_type = row.get("action_type")
        if action_type in ("to_do", "not_to_do"):
            grouped[row["dilemma_idx"]][action_type] = row

    kept: list[dict] = []
    for dilemma_idx, sides in grouped.items():
        if "to_do" not in sides or "not_to_do" not in sides:
            continue

        to_do = sides["to_do"]
        not_to_do = sides["not_to_do"]

        to_do_matches = count_value_matches(parse_values(to_do.get("values_aggregated", "")))
        not_to_do_matches = count_value_matches(parse_values(not_to_do.get("values_aggregated", "")))

        prefs = {
            f: preference(to_do_matches[f], not_to_do_matches[f])
            for f in FRAMEWORK_KEYWORDS
        }
        unique_prefs = {p for p in prefs.values() if p != "neutral"}
        if len(unique_prefs) < 2:
            continue  # all frameworks agree (or only one expressed a preference)

        prompt = reformat_as_open_ended(to_do.get("dilemma_situation", ""))
        if not prompt:
            continue

        leans = {
            f: smoothed_lean(to_do_matches[f], not_to_do_matches[f])
            for f in FRAMEWORK_KEYWORDS
        }
        balance = balance_score(list(leans.values()))
        confidence = sum(
            to_do_matches[f] + not_to_do_matches[f] for f in FRAMEWORK_KEYWORDS
        )

        kept.append({
            "source_dilemma_idx": dilemma_idx,
            "basic_situation": to_do.get("basic_situation", "").strip(),
            "topic_group": to_do.get("topic_group"),
            "prompt": prompt,
            "frameworks": {
                f: {
                    "prefers": prefs[f],
                    "lean": round(leans[f], 4),
                    "to_do_value_matches": to_do_matches[f],
                    "not_to_do_value_matches": not_to_do_matches[f],
                }
                for f in FRAMEWORK_KEYWORDS
            },
            "to_do_action": to_do.get("action"),
            "not_to_do_action": not_to_do.get("action"),
            "balance": balance,
            "confidence": confidence,
        })

    # Sort by balance (most torn first), tie-broken by confidence (most evidence).
    kept.sort(key=lambda d: (d["balance"], d["confidence"]), reverse=True)
    return kept


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text[:60] or "dilemma"


def to_output_schema(kept: list[dict]) -> dict:
    """Match the schema of `data/dilemmas.json` so other scripts can consume it."""
    output: dict[str, dict] = {}
    used_slugs: set[str] = set()
    for i, item in enumerate(kept, start=1):
        base_slug = slugify(item["basic_situation"]) or f"dilemma_{item['source_dilemma_idx']}"
        slug = base_slug
        n = 2
        while slug in used_slugs:
            slug = f"{base_slug}_{n}"
            n += 1
        used_slugs.add(slug)
        output[str(i)] = {
            "slug": slug,
            "title": item["basic_situation"].rstrip(".").capitalize() or slug,
            "prompt": item["prompt"],
            "source_dilemma_idx": item["source_dilemma_idx"],
            "topic_group": item["topic_group"],
            "frameworks": item["frameworks"],
            "to_do_action": item["to_do_action"],
            "not_to_do_action": item["not_to_do_action"],
            "balance": item["balance"],
            "confidence": item["confidence"],
        }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=SOURCE_FILE,
                        help=f"Source JSONL file (default: {SOURCE_FILE.relative_to(ROOT)})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Output JSON file (default: {DEFAULT_OUTPUT.relative_to(ROOT)})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Keep only the top N dilemmas (by balance, then confidence)")
    parser.add_argument("--min-confidence", type=int, default=0,
                        help="Drop dilemmas with fewer than this many total matched "
                             "values (guards against fake deadlock from thin evidence)")
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"ERROR: source file not found: {args.source}")
        return 1

    print(f"Loading {args.source.relative_to(ROOT)}...")
    rows = load_rows(args.source)
    print(f"  {len(rows)} rows loaded")

    kept = filter_dilemmas(rows)
    print(f"  {len(kept)} dilemmas show framework disagreement")

    if args.min_confidence > 0:
        before = len(kept)
        kept = [d for d in kept if d["confidence"] >= args.min_confidence]
        print(f"  dropped {before - len(kept)} with confidence < {args.min_confidence}")

    if args.limit is not None:
        kept = kept[: args.limit]
        print(f"  trimmed to top {len(kept)} by balance")

    output = to_output_schema(kept)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(output)} dilemmas to {args.output.relative_to(ROOT)}")

    if kept:
        print("\nTop 5 by balance (balance / confidence):")
        for item in kept[:5]:
            prefs_str = " | ".join(
                f"{f[:3]}:{item['frameworks'][f]['prefers']}" for f in FRAMEWORK_KEYWORDS
            )
            print(f"  [{item['balance']:.3f} / {item['confidence']:>2}] "
                  f"{item['basic_situation'][:46]:<46} {prefs_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
