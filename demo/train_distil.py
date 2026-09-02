"""Train one LoRA adapter that imitates one gpt-4o-mini framework judge.

Base: Qwen/Qwen2.5-1.5B-Instruct. Head: classification over scores 0-10
(frozen decision, DISTILLATION_EXTENSION.md); --head regression exists only
for the one-off sanity comparison on the utilitarian judge.

Input text mirrors what the teacher saw in score_responses.py:
    Dilemma:\n\n{dilemma}\n\nResponse to evaluate:\n\n{response}

Data: distil_data/train.jsonl (400 dilemmas). 40 dilemmas are carved out
(deterministic, seed 42) as a validation set for monitoring only. The 100
held-out dilemmas in heldout.jsonl are never read here.

Run:  python3 train_distil.py --framework utilitarian
      python3 train_distil.py --framework utilitarian --head regression
      python3 train_distil.py --framework utilitarian --smoke   # tiny test
"""

import argparse
import json
import math
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).parent
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
SEED = 42
MAX_LEN = 1024
N_VAL_DILEMMAS = 40

LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LR = 1e-4
EPOCHS = 2
BATCH_SIZE = 2
GRAD_ACCUM = 8


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def build_text(row: dict) -> str:
    return f"Dilemma:\n\n{row['dilemma']}\n\nResponse to evaluate:\n\n{row['response']}"


class ScoreDataset(Dataset):
    def __init__(self, rows, tokenizer, framework):
        self.rows = rows
        self.tokenizer = tokenizer
        self.framework = framework

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        row = self.rows[i]
        enc = self.tokenizer(
            build_text(row), truncation=True, max_length=MAX_LEN,
            padding=False, return_tensors=None,
        )
        enc["label"] = row[self.framework]
        return enc


def collate(batch, tokenizer, head):
    labels = [b.pop("label") for b in batch]
    padded = tokenizer.pad(batch, return_tensors="pt")
    if head == "classification":
        padded["labels"] = torch.tensor(labels, dtype=torch.long)
    else:
        padded["labels"] = torch.tensor(labels, dtype=torch.float32)
    return padded


def autocast(device):
    return torch.autocast(device_type=device, dtype=torch.bfloat16,
                          enabled=device != "cpu")


@torch.no_grad()
def evaluate(model, loader, device, head):
    """Returns (pearson, mae) on decoded scores vs teacher scores."""
    model.eval()
    preds, targets = [], []
    for batch in loader:
        labels = batch.pop("labels")
        batch = {k: v.to(device) for k, v in batch.items()}
        with autocast(device):
            logits = model(**batch).logits.float().cpu()
        if head == "classification":
            probs = torch.softmax(logits, dim=-1)
            scores = (probs * torch.arange(11, dtype=torch.float32)).sum(-1)
        else:
            scores = logits.squeeze(-1)
        preds.extend(scores.tolist())
        targets.extend(labels.float().tolist())
    model.train()
    preds, targets = np.array(preds), np.array(targets)
    pearson = float(np.corrcoef(preds, targets)[0, 1])
    mae = float(np.abs(preds - targets).mean())
    return pearson, mae


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--framework", required=True,
                    choices=["utilitarian", "deontological", "ubuntu"])
    ap.add_argument("--head", default="classification",
                    choices=["classification", "regression"])
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--smoke", action="store_true",
                    help="64 train / 32 val rows, 8 optimiser steps")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                    help="per-step batch; grad accum adjusts to keep the "
                         "effective batch at 16, so results don't depend on it")
    args = ap.parse_args()
    batch_size = args.batch_size
    grad_accum = max(1, 16 // batch_size)

    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    from peft import LoraConfig, get_peft_model

    set_seed(SEED)
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    out_dir = ROOT / "distil_models" / f"{args.framework}_{args.head}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [json.loads(l) for l in (ROOT / "distil_data" / "train.jsonl").open()]
    slugs = sorted({r["slug"] for r in rows})
    rng = random.Random(SEED)
    val_slugs = set(rng.sample(slugs, N_VAL_DILEMMAS))
    train_rows = [r for r in rows if r["slug"] not in val_slugs]
    val_rows = [r for r in rows if r["slug"] in val_slugs]
    if args.smoke:
        train_rows, val_rows = train_rows[:64], val_rows[:32]
    print(f"train rows: {len(train_rows)}  val rows: {len(val_rows)}")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokenizer.pad_token = tokenizer.eos_token

    num_labels = 11 if args.head == "classification" else 1
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=num_labels, torch_dtype=torch.bfloat16,
    )
    model.config.pad_token_id = tokenizer.pad_token_id
    if args.head == "regression":
        model.config.problem_type = "regression"

    lora = LoraConfig(
        r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        modules_to_save=["score"], task_type="SEQ_CLS",
    )
    model = get_peft_model(model, lora)
    # Trainable params (LoRA matrices + score head) kept as fp32 master
    # copies; the forward pass runs under bf16 autocast, which reconciles
    # them with the bf16 base. Full-precision optimiser updates, bf16 speed.
    for p in model.parameters():
        if p.requires_grad:
            p.data = p.data.float()
    model.print_trainable_parameters()
    model.to(device)
    model.train()

    train_loader = DataLoader(
        ScoreDataset(train_rows, tokenizer, args.framework),
        batch_size=batch_size, shuffle=True,
        collate_fn=lambda b: collate(b, tokenizer, args.head),
        generator=torch.Generator().manual_seed(SEED),
    )
    val_loader = DataLoader(
        ScoreDataset(val_rows, tokenizer, args.framework),
        batch_size=batch_size, shuffle=False,
        collate_fn=lambda b: collate(b, tokenizer, args.head),
    )

    steps_per_epoch = math.ceil(len(train_loader) / grad_accum)
    total_steps = 8 if args.smoke else steps_per_epoch * args.epochs
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=LR)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: max(0.05, 1 - s / total_steps))

    print(f"device={device} head={args.head} framework={args.framework} "
          f"total optimiser steps={total_steps}")

    step = 0
    t0 = time.time()
    done = False
    for epoch in range(args.epochs):
        if done:
            break
        for i, batch in enumerate(train_loader):
            batch = {k: v.to(device) for k, v in batch.items()}
            with autocast(device):
                loss = model(**batch).loss / grad_accum
            loss.backward()
            if (i + 1) % grad_accum == 0 or i + 1 == len(train_loader):
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                step += 1
                if step % 10 == 0 or args.smoke:
                    elapsed = time.time() - t0
                    print(f"epoch {epoch} step {step}/{total_steps} "
                          f"loss {loss.item() * grad_accum:.4f} "
                          f"({elapsed / step:.1f}s/step)", flush=True)
                if step >= total_steps:
                    done = True
                    break
        pearson, mae = evaluate(model, val_loader, device, args.head)
        print(f"end epoch {epoch}: val pearson {pearson:.4f} mae {mae:.4f}",
              flush=True)

    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    meta = {
        "framework": args.framework, "head": args.head, "base": BASE_MODEL,
        "seed": SEED, "epochs": args.epochs, "lr": LR,
        "lora_r": LORA_R, "lora_alpha": LORA_ALPHA,
        "batch": batch_size, "grad_accum": grad_accum, "max_len": MAX_LEN,
        "val_slugs": sorted(val_slugs), "smoke": args.smoke,
        "minutes": round((time.time() - t0) / 60, 1),
    }
    (out_dir / "training_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"saved adapter to {out_dir}")


if __name__ == "__main__":
    main()
