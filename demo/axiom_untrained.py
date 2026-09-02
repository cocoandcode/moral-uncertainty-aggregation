"""Untrained-Qwen control for the axiom exam.

The bag-of-words floor answers "did the students beat vocabulary
statistics?" but not "did distillation add anything the base model
lacked?". This script runs Qwen2.5-1.5B-Instruct with NO adapter and NO
training on the same 45 main + 6 held-out axiom pairs, graded by the
same criterion as axiom_distil.py.

Two prompt variants, since the base model needs to be told which
framework to judge by:

    minimal  one sentence naming the framework, nothing else. The
             closest thing to "untrained Qwen, un-engineered prompt".
    teacher  the exact refined judge prompts from score_responses.py.
             Answers "could we have skipped training and just prompted
             the small model?"

Scoring: the base model is prompted to reply with a single integer
0-10. We take the logits of the first generated token restricted to
the digit tokens "0".."9"; since Qwen tokenises "10" as "1","0", a
second forward pass splits the mass on "1" between the values 1 and
10 by the probability that the next token is "0". Decoded by expected
value - mirroring the students' EV rule, so ties are effectively
impossible for both.

Output: distil_eval/axioms_untrained.metrics.json

Run:  python3 axiom_untrained.py
"""

import json
from collections import defaultdict
from pathlib import Path

import torch

from axiom_distil import FRAMEWORKS, TEACHER_GRID, grade, load_pairs, show
from eval_distil import BASE_MODEL, pick_device
from score_responses import FRAMEWORKS as TEACHER_PROMPTS

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "distil_eval"

MINIMAL_PROMPTS = {
    "utilitarian": (
        "Score the response to the dilemma from the standpoint of "
        "utilitarian ethics. Reply with ONLY a single integer between "
        "0 and 10. No explanation."),
    "deontological": (
        "Score the response to the dilemma from the standpoint of "
        "deontological (Kantian) ethics. Reply with ONLY a single "
        "integer between 0 and 10. No explanation."),
    "ubuntu": (
        "Score the response to the dilemma from the standpoint of "
        "Ubuntu ethics. Reply with ONLY a single integer between "
        "0 and 10. No explanation."),
}


def user_content(dilemma: str, response: str) -> str:
    # identical to score_responses.score_response
    return f"Dilemma:\n\n{dilemma}\n\nResponse to evaluate:\n\n{response}"


@torch.no_grad()
def ev_score(model, tokenizer, device: str, digit_ids: list,
             msgs: list) -> float:
    """Expected value over 0-10 from at most two forward passes."""
    ids = tokenizer.apply_chat_template(
        msgs, add_generation_prompt=True, return_tensors="pt").to(device)
    logits = model(ids).logits[0, -1].float().cpu()
    p_digit = torch.softmax(logits[digit_ids], dim=-1)  # values 0..9

    # split value 1 vs 10: probability that "0" follows a leading "1"
    one = torch.tensor([[digit_ids[1]]], device=device)
    logits2 = model(torch.cat([ids, one], dim=1)).logits[0, -1].float().cpu()
    q_zero = float(torch.softmax(logits2, dim=-1)[digit_ids[0]])

    probs = torch.zeros(11)
    probs[0] = p_digit[0]
    probs[2:10] = p_digit[2:10]
    probs[1] = p_digit[1] * (1 - q_zero)
    probs[10] = p_digit[1] * q_zero
    probs /= probs.sum()
    return float((probs * torch.arange(11, dtype=torch.float32)).sum())


@torch.no_grad()
def score_variant(pairs: list, prompts: dict, model, tokenizer,
                  device: str, digit_ids: list) -> dict:
    """{judge: {pair_id: (score_a, score_b)}} via first-token EV."""
    out = {}
    for fw in FRAMEWORKS:
        by_pair = defaultdict(dict)
        for i, p in enumerate(pairs):
            for side in ("a", "b"):
                msgs = [
                    {"role": "system", "content": prompts[fw]},
                    {"role": "user",
                     "content": user_content(p["dilemma"],
                                             p[f"response_{side}"])},
                ]
                by_pair[p["pair_id"]][side] = ev_score(
                    model, tokenizer, device, digit_ids, msgs)
            if i % 10 == 0:
                print(f"  {fw}: {i + 1}/{len(pairs)} pairs", flush=True)
        out[fw] = {pid: (v["a"], v["b"]) for pid, v in by_pair.items()}
    return out


def main() -> None:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    pairs = load_pairs()
    device = pick_device()
    print(f"{len(pairs)} pairs, device={device}, model={BASE_MODEL}")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16)
    model.eval().to(device)

    # single-token encodings of the digits "0".."9"
    digit_ids = []
    for v in range(10):
        enc = tokenizer.encode(str(v), add_special_tokens=False)
        assert len(enc) == 1, f"'{v}' is not a single token: {enc}"
        digit_ids.append(enc[0])

    results = {}
    for variant, prompts in (("minimal", MINIMAL_PROMPTS),
                             ("teacher", dict(TEACHER_PROMPTS))):
        print(f"\n=== variant: {variant} ===")
        cells, grids = grade(pairs, score_variant(
            pairs, prompts, model, tokenizer, device, digit_ids))
        results[variant] = {"grids": grids, "cells": cells}
        show(f"UNTRAINED QWEN ({variant} prompt)", grids["main"])
        show(f"UNTRAINED QWEN ({variant} prompt), held-out",
             grids["heldout"])

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "axioms_untrained.metrics.json").write_text(json.dumps({
        "model": BASE_MODEL,
        "variants": {v: r["grids"] for v, r in results.items()},
        "cells": {v: r["cells"] for v, r in results.items()},
        "teacher_reference": TEACHER_GRID,
        "notes": "Base model, no adapter. First-generated-token logits "
                 "over digit tokens; a second pass splits value 1 vs 10 "
                 "by P(next='0'). Decoded by expected value (same rule "
                 "as the students, so no ties). 'minimal' = one-sentence "
                 "framework prompt; 'teacher' = the refined judge "
                 "prompts from score_responses.py.",
    }, indent=2, ensure_ascii=False))
    print(f"\nsaved {OUT_DIR / 'axioms_untrained.metrics.json'}")


if __name__ == "__main__":
    main()
