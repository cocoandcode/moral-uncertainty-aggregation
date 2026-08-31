#!/usr/bin/env bash
# Run the full distillation training plan on a rented GPU box.
# Usage: bash run_all_training.sh
# Order: smoke test, then utilitarian (classification), the one-off
# regression sanity run, then the remaining two judges.
set -euo pipefail
cd "$(dirname "$0")"

BS="${BS:-8}"   # per-step batch; grad accum keeps effective batch at 16

python3 train_distil.py --framework utilitarian --smoke --batch-size "$BS"
python3 train_distil.py --framework utilitarian --batch-size "$BS"
python3 train_distil.py --framework utilitarian --head regression --batch-size "$BS"
python3 train_distil.py --framework deontological --batch-size "$BS"
python3 train_distil.py --framework ubuntu --batch-size "$BS"

echo "ALL TRAINING DONE"
ls -la distil_models/
