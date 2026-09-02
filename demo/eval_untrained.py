"""Untrained-Qwen baseline on the held-out fidelity test.

The missing rung of the baseline ladder. The BoW floor shows what
supervised vocabulary statistics earn; this shows what the base model
earns with NO training at all. Qwen2.5-1.5B-Instruct (no adapter)
scores the same 1,600 held-out responses the students were graded on,
and the same metrics() function compares its scores to the teacher's.

Two prompt variants:

    teacher  the exact refined judge prompts from score_responses.py,
             one pass per framework ("prompting alone").
    generic  a single no-framework quality prompt, one pass total; its
             one score column is compared against all three teachers
             ("quality alone" - contains zero framework differentiation
             by construction).

Scoring matches axiom_untrained.py: first-generated-token logits over
the digit tokens, a KV-cached second step splits value 1 vs 10 by
P(next='0'), decoded by expected value. Inputs use the students'
1,024-token budget. Deterministic, so one run suffices.

Uses eager attention: the MPS SDPA kernel returns NaN logits for any
padded row in a batch. Any row that still comes out NaN is rescored
alone (batch of one needs no padding).

Outputs to distil_eval/:
    untrained_teacher_<framework>.predictions.jsonl
    untrained_generic.predictions.jsonl
    untrained.metrics.json

Run:  python3 eval_untrained.py
"""

import json
import time
from pathlib import Path

import numpy as np
import torch

from eval_distil import BASE_MODEL, MAX_LEN, build_text, metrics, pick_device
from score_responses import FRAMEWORKS as TEACHER_PROMPTS

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "distil_eval"
FRAMEWORKS = ("utilitarian", "deontological", "ubuntu")
BATCH_SIZE = 8

GENERIC_PROMPT = (
    "You will be shown a dilemma and a response to it. Rate the response. "
    "Reply with ONLY a single integer between 0 and 10. No explanation."
)


@torch.no_grad()
def score_rows(rows: list, system_prompt: str, model, tokenizer,
               device: str, digit_ids: list, label: str) -> np.ndarray:
    """EV score per row, batched with left padding."""
    values = torch.arange(11, dtype=torch.float32)

    # respect the students' input budget, then wrap in the chat template
    prompts = []
    for r in rows:
        content_ids = tokenizer(build_text(r), truncation=True,
                                max_length=MAX_LEN)["input_ids"]
        content = tokenizer.decode(content_ids)
        prompts.append(tokenizer.apply_chat_template(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": content}],
            add_generation_prompt=True, tokenize=False))

    encs = [tokenizer(p, padding=False, add_special_tokens=False)
            for p in prompts]
    order = sorted(range(len(rows)), key=lambda i: len(encs[i]["input_ids"]))
    scores = np.zeros(len(rows))

    t0 = time.time()
    for start in range(0, len(order), BATCH_SIZE):
        idx = order[start:start + BATCH_SIZE]
        batch = tokenizer.pad([encs[i] for i in idx], return_tensors="pt")
        batch = {k: v.to(device) for k, v in batch.items()}

        out = model(**batch, use_cache=True)
        logits = out.logits[:, -1].float().cpu()
        p_digit = torch.softmax(logits[:, digit_ids], dim=-1)  # values 0..9

        # one cached step with "1" appended: P(next='0') splits 1 vs 10
        ones = torch.full((len(idx), 1), digit_ids[1], device=device)
        mask = torch.cat([batch["attention_mask"],
                          torch.ones((len(idx), 1), device=device,
                                     dtype=batch["attention_mask"].dtype)],
                         dim=1)
        logits2 = model(input_ids=ones, attention_mask=mask,
                        past_key_values=out.past_key_values,
                        ).logits[:, -1].float().cpu()
        q_zero = torch.softmax(logits2, dim=-1)[:, digit_ids[0]]

        probs = torch.zeros(len(idx), 11)
        probs[:, 0] = p_digit[:, 0]
        probs[:, 2:10] = p_digit[:, 2:10]
        probs[:, 1] = p_digit[:, 1] * (1 - q_zero)
        probs[:, 10] = p_digit[:, 1] * q_zero
        probs /= probs.sum(dim=1, keepdim=True)
        ev = (probs * values).sum(dim=1)

        for i, s in zip(idx, ev.tolist()):
            scores[i] = s
        done = start + len(idx)
        if (start // BATCH_SIZE) % 25 == 0:
            rate = done / (time.time() - t0)
            print(f"  {label}: {done}/{len(order)} ({rate:.1f} rows/s)",
                  flush=True)

    bad = [i for i in range(len(rows)) if np.isnan(scores[i])]
    if bad:
        print(f"  {label}: rescoring {len(bad)} NaN rows unbatched",
              flush=True)
        for i in bad:
            ids = torch.tensor([encs[i]["input_ids"]], device=device)
            out = model(ids, use_cache=True)
            l1 = out.logits[0, -1].float().cpu()
            p_digit = torch.softmax(l1[digit_ids], dim=-1)
            one = torch.full((1, 1), digit_ids[1], device=device)
            l2 = model(input_ids=one,
                       past_key_values=out.past_key_values,
                       ).logits[0, -1].float().cpu()
            q_zero = float(torch.softmax(l2, dim=-1)[digit_ids[0]])
            probs = torch.zeros(11)
            probs[0] = p_digit[0]
            probs[2:10] = p_digit[2:10]
            probs[1] = p_digit[1] * (1 - q_zero)
            probs[10] = p_digit[1] * q_zero
            probs /= probs.sum()
            scores[i] = float((probs * values).sum())
    assert not np.isnan(scores).any(), f"{label}: NaN scores remain"
    return scores


def save_predictions(path: Path, rows: list, preds: np.ndarray) -> None:
    with path.open("w") as f:
        for r, s in zip(rows, preds):
            f.write(json.dumps({
                "slug": r["slug"], "id": r["id"],
                "score_ev": round(float(s), 4),
                "score_int": int(np.clip(round(float(s)), 0, 10)),
            }) + "\n")


def load_saved(path: Path, n_rows: int):
    """Resume support: reuse a complete predictions file if present."""
    if not path.exists():
        return None
    saved = [json.loads(l) for l in path.open()]
    if len(saved) != n_rows:
        return None
    print(f"resuming: loaded {path.name}")
    return np.array([r["score_ev"] for r in saved])


def main() -> None:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = pick_device()
    rows = [json.loads(l)
            for l in (ROOT / "distil_data" / "heldout.jsonl").open()]
    print(f"{len(rows)} rows, device={device}, model={BASE_MODEL}")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    # eager attention: MPS SDPA yields NaN logits for padded rows
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16, attn_implementation="eager")
    model.eval().to(device)

    digit_ids = []
    for v in range(10):
        enc = tokenizer.encode(str(v), add_special_tokens=False)
        assert len(enc) == 1, f"'{v}' is not a single token: {enc}"
        digit_ids.append(enc[0])

    OUT_DIR.mkdir(exist_ok=True)
    all_metrics = {"teacher_prompt": {}, "generic_prompt": {}}

    for fw in FRAMEWORKS:
        path = OUT_DIR / f"untrained_teacher_{fw}.predictions.jsonl"
        preds = load_saved(path, len(rows))
        if preds is None:
            preds = score_rows(rows, TEACHER_PROMPTS[fw], model, tokenizer,
                               device, digit_ids, f"teacher/{fw}")
            save_predictions(path, rows, preds)
        m = metrics(rows, fw, preds)
        all_metrics["teacher_prompt"][fw] = m
        print(f"teacher-prompt {fw}: {json.dumps(m)}", flush=True)

    generic_path = OUT_DIR / "untrained_generic.predictions.jsonl"
    generic = load_saved(generic_path, len(rows))
    if generic is None:
        generic = score_rows(rows, GENERIC_PROMPT, model, tokenizer,
                             device, digit_ids, "generic")
        save_predictions(generic_path, rows, generic)
    for fw in FRAMEWORKS:
        m = metrics(rows, fw, generic)
        all_metrics["generic_prompt"][fw] = m
        print(f"generic vs {fw}: {json.dumps(m)}", flush=True)

    (OUT_DIR / "untrained.metrics.json").write_text(json.dumps({
        "model": BASE_MODEL,
        "metrics": all_metrics,
        "notes": "No adapter, no training. teacher_prompt = refined judge "
                 "prompts from score_responses.py, one pass per framework. "
                 "generic_prompt = single no-framework pass; the same score "
                 "column is compared against all three teacher columns. "
                 "EV decoding over digit tokens with a cached second step "
                 "splitting 1 vs 10. Same held-out rows, input budget and "
                 "metrics() as the students.",
    }, indent=2))
    print(f"saved {OUT_DIR / 'untrained.metrics.json'}")


if __name__ == "__main__":
    main()
