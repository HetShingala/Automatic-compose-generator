#!/bin/bash
set -e

echo "[entrypoint] Starting ML pipeline..."

python train.py

echo "[entrypoint] Training complete. Running evaluation..."

python evaluate.py

echo "[entrypoint] Pipeline finished."