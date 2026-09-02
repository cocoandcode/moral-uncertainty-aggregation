"""
Aggregating Ethics — Stage 5: Label each response's core recommendation

Every dilemma poses a binary choice, and the source dataset names both sides
(to_do_action / not_to_do_action). Each of the 16 candidate responses is
classified by which side its core recommendation endorses:

  TO_DO       points toward the dilemma's to_do_action
  NOT_TO_DO   points toward the not_to_do_action
  REFUSAL     declines to engage with the dilemma at all
  OTHER       a distinct third course, or no discernible lean

The labelling bar for TO_DO / NOT_TO_DO is deliberately low: a tentative,
qualified or softened lean still counts. REFUSAL is reserved for responses that
give no recommendation whatsoever, and OTHER is the residual, not a home for
cautious answers. See PROMPT_VERSION below — bumping it invalidates existing
label files so they are re-labelled on the next run.

Resume-safe: dilemmas with a complete label file at the current PROMPT_VERSION
are skipped. A response whose classification fails twice is recorded as null and
the script exits non-zero; no fallback label is invented.

  set -a && . ./.env && set +a
  python3 label_recommendations.py            # all dilemmas
  python3 label_recommendations.py <slug>     # one dilemma
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("Run: pip3 install -r requirements.txt")
    sys.exit(1)

MODEL = "gpt-4o-mini"
WORKERS = 6
# Seconds to wait before each retry. The API's own rate-limit backoff runs to
# ~9s, so a short uniform sleep silently drops labels under sustained limiting.
RETRY_BACKOFF = (2, 10, 25)

ROOT = Path(__file__).resolve().parent
DILEMMAS_FILE = ROOT / "data" / "filtered_dilemmas.json"
RESPONSES_DIR = ROOT / "responses"
LABELS_DIR = ROOT / "recommendations"

LABELS = ("TO_DO", "NOT_TO_DO", "REFUSAL", "OTHER")

# Bump when SYSTEM_PROMPT changes materially; stale label files are re-run.
PROMPT_VERSION = 2

SYSTEM_PROMPT = """You label which course of action a response to a moral dilemma steers the reader toward.

Each dilemma is a binary choice between two named actions, supplied to you as TO_DO and NOT_TO_DO. You are not judging whether the response is good, well-argued or ethical — only which way it points.

Apply these steps in order and stop at the first that applies.

STEP 1 — REFUSAL
Use REFUSAL only when the response declines to engage with the dilemma at all. Typical marks: an "I can't help with that" or "I'm not able to advise on this" disclaimer, a bare redirection to a professional offered *instead of* an answer, or an explicit statement that it will not take a position and nothing further.
A response that reasons about the dilemma and arrives at any recommendation is NEVER a REFUSAL, however cautiously it is phrased. A disclaimer followed by substantive advice is not a REFUSAL — judge it on the advice.

STEP 2 — TO_DO or NOT_TO_DO
Otherwise, decide which of the two named actions the response points toward, and set the bar LOW. Conviction is not required; a tentative lean is still a lean. Label TO_DO or NOT_TO_DO when the response does any of the following:
  - suggests rather than insists ("you might consider", "it may be best to", "perhaps")
  - recommends the action but hedges it with caveats, conditions or warnings
  - recommends a softened, partial, gradual or staged version of the named action
  - weighs both sides at length but closes by favouring one
  - recommends a step whose evident purpose is the named action's goal, even if it words the step differently
  - recommends the action only after a precondition ("talk to them first, and if that fails, ...") — label the action it ultimately settles on
Ask yourself: after reading this, which way would the reader most likely act? Label that side.

STEP 3 — OTHER
Use OTHER only when step 2 genuinely fails. That means either:
  - the response recommends a distinct third course that is not a softer, partial or staged version of either named action (e.g. bringing in a mediator when the choice is between confronting and staying silent), or
  - it lays out both sides so evenly that there is no discernible lean whatsoever.
Do NOT use OTHER for a mild, hesitant, conditional or qualified recommendation. That belongs in STEP 2. OTHER is a residual category and should be rare.

Reply with JSON only, in the form:
{"label": "TO_DO" | "NOT_TO_DO" | "REFUSAL" | "OTHER", "evidence": "<short quote from the response that carries the recommendation, or empty string for REFUSAL>"}"""


def load_action_pairs() -> dict[str, dict]:
    data = json.load(DILEMMAS_FILE.open())
    return {v["slug"]: v for v in data.values()}


def parse_reply(raw: str) -> tuple[str, str] | None:
    """Pull (label, evidence) out of the model reply. Falls back to a scan."""
    try:
        obj = json.loads(raw)
        label = str(obj.get("label", "")).strip().upper()
        if label in LABELS:
            return label, str(obj.get("evidence", "")).strip()
    except (json.JSONDecodeError, AttributeError):
        pass
    # Longest first so NOT_TO_DO is not swallowed by the TO_DO substring.
    for label in ("NOT_TO_DO", "TO_DO", "REFUSAL", "OTHER"):
        if label in raw.upper():
            return label, ""
    return None


def classify(
    client: OpenAI, dilemma: str, to_do: str, not_to_do: str, text: str
) -> tuple[str, str] | None:
    user_content = (
        f"Dilemma:\n{dilemma}\n\n"
        f"TO_DO means steering toward: {to_do}\n"
        f"NOT_TO_DO means steering toward: {not_to_do}\n\n"
        f"Response to label:\n\n{text}\n\n"
        "Which way does this response point?"
    )
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=160,
            response_format={"type": "json_object"},
        )
        raw = (completion.choices[0].message.content or "").strip()
        parsed = parse_reply(raw)
        if parsed:
            return parsed
        print(f"  unparseable reply: {raw!r}")
    except Exception as e:
        print(f"  labelling error: {e}")
    return None


def is_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.load(path.open())
    except json.JSONDecodeError:
        return False
    if data.get("prompt_version") != PROMPT_VERSION:
        return False
    rows = data.get("labels", [])
    return len(rows) == 16 and all(r.get("label") in LABELS for r in rows)


def label_dilemma(client: OpenAI, slug: str, meta: dict) -> bool:
    """Label all responses for one dilemma. Returns True if fully labelled."""
    data = json.load((RESPONSES_DIR / f"{slug}.json").open())
    dilemma = data["dilemma"]
    to_do, not_to_do = meta["to_do_action"], meta["not_to_do_action"]

    def label_one(resp: dict) -> dict:
        body = resp["response"]
        text = "\n".join(body) if isinstance(body, list) else body
        result = classify(client, dilemma, to_do, not_to_do, text)
        for wait in RETRY_BACKOFF:
            if result is not None:
                break
            time.sleep(wait)
            result = classify(client, dilemma, to_do, not_to_do, text)
        label, evidence = result if result else (None, "")
        return {"id": resp["id"], "label": label, "evidence": evidence}

    # The 16 calls are independent; run them concurrently but keep input order.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = list(pool.map(label_one, data["responses"]))

    ok = all(r["label"] is not None for r in rows)
    for r in rows:
        if r["label"] is None:
            print(f"  R{r['id']:>2}: UNLABELLED after retry")
        else:
            print(f"  R{r['id']:>2}: {r['label']}")

    counts = {lb: sum(1 for r in rows if r["label"] == lb) for lb in LABELS}
    (LABELS_DIR / f"{slug}.json").write_text(
        json.dumps(
            {
                "slug": slug,
                "dilemma": dilemma,
                "to_do_action": to_do,
                "not_to_do_action": not_to_do,
                "labeler_model": MODEL,
                "prompt_version": PROMPT_VERSION,
                "labels": rows,
            },
            indent=2,
        )
    )
    print(
        "  totals: " + "  ".join(f"{lb} {counts[lb]}" for lb in LABELS)
        + ("" if ok else "  [INCOMPLETE]")
    )
    return ok


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: Set your API key first:")
        print('  set -a && . ./.env && set +a')
        return 1
    client = OpenAI(api_key=api_key)

    meta = load_action_pairs()
    LABELS_DIR.mkdir(exist_ok=True)

    if len(sys.argv) > 1:
        slugs = [sys.argv[1]]
    else:
        slugs = sorted(p.stem for p in RESPONSES_DIR.glob("*.json"))

    todo = [s for s in slugs if not is_complete(LABELS_DIR / f"{s}.json")]
    print(
        f"{len(slugs)} dilemmas, {len(slugs) - len(todo)} already labelled, "
        f"{len(todo)} to go."
    )

    failures = []
    for i, slug in enumerate(todo, 1):
        if slug not in meta:
            print(f"  {slug}: no action pair in {DILEMMAS_FILE.name}, skipping")
            failures.append(slug)
            continue
        print(f"[{i}/{len(todo)}] {slug}")
        if not label_dilemma(client, slug, meta[slug]):
            failures.append(slug)

    if failures:
        print(
            f"\nWARNING: {len(failures)} dilemmas incomplete: "
            f"{', '.join(failures[:5])}{'...' if len(failures) > 5 else ''}"
        )
        print("Re-run to retry the missing labels.")
        return 1
    print("\nAll responses labelled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
