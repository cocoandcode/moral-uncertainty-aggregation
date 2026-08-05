"""
Aggregating Ethics — Stage 1: Generate candidate responses

Sends a moral dilemma to Llama 3.1 8B via Ollama and collects a diverse
candidate pool using temperature sampling alone. No framework-flavoured
system prompts: the ethical frameworks live only in the judges
(score_responses.py), so priming the generator would manufacture the very
disagreement we later measure. See NOTES.md §5.

Before running:
  1. Make sure Ollama is running (icon in your menu bar).
  2. pip3 install -r requirements.txt
  3. python3 generate_responses.py <dilemma_number>
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from pathlib import Path

import requests

# ── Settings ─────────────────────────────────────────────────
MODEL = "llama3.1:8b"
NUM_RESPONSES = 16
TEMPERATURE = 1.1
TOP_P = 0.95
WRAP_WIDTH = 100
OLLAMA_URL = "http://localhost:11434/api/generate"

ROOT = Path(__file__).resolve().parent
DILEMMAS_FILE = ROOT / "data" / "filtered_dilemmas.json"
RESPONSES_DIR = ROOT / "responses"


def load_dilemma(number: int, source: Path = DILEMMAS_FILE) -> dict:
    with source.open() as f:
        dilemmas = json.load(f)
    key = str(number)
    if key not in dilemmas:
        available = sorted(int(k) for k in dilemmas)
        preview = available[:10] + (["..."] if len(available) > 10 else [])
        raise KeyError(f"Dilemma {number} not found in {source.name}. Available: {preview}")
    return dilemmas[key]


def wrap_text(text: str, width: int = WRAP_WIDTH) -> list[str]:
    """Wrap long lines while preserving short ones and blank lines."""
    result: list[str] = []
    for line in text.strip().split("\n"):
        if len(line) <= width:
            result.append(line)
        else:
            result.extend(
                textwrap.wrap(line, width=width, break_long_words=False, break_on_hyphens=False)
                or [""]
            )
    return result


def generate_one_response(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": TEMPERATURE, "top_p": TOP_P},
    }
    response = requests.post(OLLAMA_URL, json=payload)
    return response.json()["response"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate candidate responses for a dilemma.")
    parser.add_argument("dilemma_number", type=int, help="Key of the dilemma in the source file")
    parser.add_argument("--source", type=Path, default=DILEMMAS_FILE,
                        help=f"Dilemmas JSON file (default: {DILEMMAS_FILE.name})")
    args = parser.parse_args()

    try:
        dilemma = load_dilemma(args.dilemma_number, args.source)
    except (FileNotFoundError, KeyError) as e:
        print(f"ERROR: {e}")
        return 1

    slug = dilemma["slug"]
    prompt = dilemma["prompt"]
    output_file = RESPONSES_DIR / f"{slug}.json"
    RESPONSES_DIR.mkdir(exist_ok=True)

    print(f"Generating {NUM_RESPONSES} diverse responses for: {dilemma.get('title', slug)}")
    print(f"Model: {MODEL} | Temperature: {TEMPERATURE}")
    print("=" * 60)

    responses = []
    for i in range(NUM_RESPONSES):
        print(f"\nResponse {i+1}/{NUM_RESPONSES}")
        print("  Generating...", end=" ", flush=True)
        start = time.time()

        try:
            text = generate_one_response(prompt)
            elapsed = time.time() - start
            print(f"done ({elapsed:.1f}s)")
            print(f"  >> {text.strip()[:120]}...")
            responses.append({"id": i + 1, "response": wrap_text(text)})
        except Exception as e:
            print(f"ERROR: {e}")
            print("  Is Ollama running? Check your menu bar.")

    output = {
        "dilemma": prompt.strip(),
        "slug": slug,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "num_responses": len(responses),
        "responses": responses,
    }
    with output_file.open("w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Done! {len(responses)} responses saved to {output_file.relative_to(ROOT)}")
    print("\nNext: score these with the three ethical judges.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
