"""Step 4: grade the distilled judges on the frozen held-out set.

Runs a trained adapter over distil_data/heldout.jsonl (100 dilemmas x 16
responses, never seen in training) and compares its scores to the
teacher's. Decoding follows the frozen rule in DISTILLATION_EXTENSION.md:
expected value over the 11 class probabilities for the correlation
metrics; the rounded expected value is also saved per row for the
step-5 aggregation replay.

Reported per run: Pearson, Spearman, MAE, and mean within-dilemma
Kendall tau (tau-b, ties handled; dilemmas where either side is constant
are skipped and counted).

Outputs to distil_eval/:
    <run>.predictions.jsonl   one row per response (slug, id, teacher,
                              student_ev, student_int)
    <run>.metrics.json        the summary numbers

Run:  python3 eval_distil.py --run utilitarian_classification
      python3 eval_distil.py --run all
"""

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from scipy import stats

ROOT = Path(__file__).parent
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
MAX_LEN = 1024
OUT_DIR = ROOT / "distil_eval"

ALL_RUNS = [
    "utilitarian_classification",
    "utilitarian_regression",
    "deontological_classification",
    "ubuntu_classification",
]


def build_text(row: dict) -> str:
    return f"Dilemma:\n\n{row['dilemma']}\n\nResponse to evaluate:\n\n{row['response']}"


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def autocast(device: str):
    return torch.autocast(device_type=device, dtype=torch.bfloat16,
                          enabled=device != "cpu")


@torch.no_grad()
def predict(run: str, rows: list, device: str, batch_size: int) -> np.ndarray:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    from peft import PeftModel

    framework, head = run.rsplit("_", 1)
    adapter_dir = ROOT / "distil_models" / run
    # tokenizer from the base, not the adapter dir: the pod's newer
    # transformers saved a tokenizer_config the local version can't parse,
    # and training never changed the tokenizer anyway
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokenizer.pad_token = tokenizer.eos_token

    num_labels = 11 if head == "classification" else 1
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=num_labels, torch_dtype=torch.bfloat16)
    model.config.pad_token_id = tokenizer.pad_token_id
    model = PeftModel.from_pretrained(model, adapter_dir)
    model.eval().to(device)

    # sort by token length so batches pad efficiently, then restore order
    encs = [tokenizer(build_text(r), truncation=True, max_length=MAX_LEN,
                      padding=False) for r in rows]
    order = sorted(range(len(rows)), key=lambda i: len(encs[i]["input_ids"]))
    scores = np.zeros(len(rows))

    t0 = time.time()
    for start in range(0, len(order), batch_size):
        idx = order[start:start + batch_size]
        batch = tokenizer.pad([encs[i] for i in idx], return_tensors="pt")
        batch = {k: v.to(device) for k, v in batch.items()}
        with autocast(device):
            logits = model(**batch).logits.float().cpu()
        if head == "classification":
            probs = torch.softmax(logits, dim=-1)
            ev = (probs * torch.arange(11, dtype=torch.float32)).sum(-1)
        else:
            ev = logits.squeeze(-1)
        for i, s in zip(idx, ev.tolist()):
            scores[i] = s
        done = start + len(idx)
        if (start // batch_size) % 25 == 0:
            rate = done / (time.time() - t0)
            print(f"  {run}: {done}/{len(order)} ({rate:.0f} rows/s)",
                  flush=True)

    del model
    if device == "mps":
        torch.mps.empty_cache()
    return scores


def metrics(rows: list, framework: str, student: np.ndarray) -> dict:
    teacher = np.array([r[framework] for r in rows], dtype=float)
    pearson = float(stats.pearsonr(student, teacher)[0])
    spearman = float(stats.spearmanr(student, teacher)[0])
    mae = float(np.abs(student - teacher).mean())

    by_dilemma = defaultdict(list)
    for i, r in enumerate(rows):
        by_dilemma[r["slug"]].append(i)
    taus, skipped = [], 0
    for slug, idx in by_dilemma.items():
        t, s = teacher[idx], student[idx]
        if len(set(t)) < 2 or len(set(np.round(s, 6))) < 2:
            skipped += 1
            continue
        tau = stats.kendalltau(t, s)[0]
        if np.isnan(tau):
            skipped += 1
        else:
            taus.append(tau)
    return {
        "pearson": round(pearson, 4),
        "spearman": round(spearman, 4),
        "mae": round(mae, 4),
        "mean_within_dilemma_kendall_tau": round(float(np.mean(taus)), 4),
        "tau_dilemmas_used": len(taus),
        "tau_dilemmas_skipped_constant": skipped,
        "n_rows": len(rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True,
                    choices=ALL_RUNS + ["all"])
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()
    runs = ALL_RUNS if args.run == "all" else [args.run]

    device = pick_device()
    print(f"device={device}")
    rows = [json.loads(l)
            for l in (ROOT / "distil_data" / "heldout.jsonl").open()]
    OUT_DIR.mkdir(exist_ok=True)

    for run in runs:
        framework = run.rsplit("_", 1)[0]
        student = predict(run, rows, device, args.batch_size)

        with (OUT_DIR / f"{run}.predictions.jsonl").open("w") as f:
            for r, s in zip(rows, student):
                f.write(json.dumps({
                    "slug": r["slug"], "id": r["id"],
                    "teacher": r[framework],
                    "student_ev": round(float(s), 4),
                    "student_int": int(np.clip(round(s), 0, 10)),
                }) + "\n")

        m = metrics(rows, framework, student)
        (OUT_DIR / f"{run}.metrics.json").write_text(json.dumps(m, indent=2))
        print(f"{run}: {json.dumps(m)}", flush=True)


if __name__ == "__main__":
    main()
