# ml_pipeline

A simple ML training pipeline used to test the Docker Compose Generator.

## What it does

1. `train.py` — loads `data/dataset.csv`, trains a RandomForest classifier, saves artifact to `models/model.pkl`
2. `evaluate.py` — loads the saved model, evaluates on test split, writes metrics to `reports/report.json`

## Expected outputs after a successful run

- `models/model.pkl` — trained model artifact
- `reports/report.json` — evaluation metrics (accuracy, precision)

## Running locally (without Docker)

```bash
pip install -r requirements.txt
python train.py
python evaluate.py
```

## Running with Docker Compose (your task)

Use the Docker Compose Generator to produce a `Dockerfile` and `docker-compose.yml` for this pipeline.

Volume mounts you'll want to configure:
- `./models:/app/models`
- `./reports:/app/reports`

The pipeline should run automatically on `docker compose up` and produce the output files on your host machine.
