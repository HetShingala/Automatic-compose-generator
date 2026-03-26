"""
train.py
Loads dataset, trains a simple sklearn classifier, saves model artifact.
Exposes Prometheus metrics on port 8080 during training.
"""

import os
import pickle
import random
import time
import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn
import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from prometheus_client import start_http_server, Gauge, Counter, Summary, REGISTRY, write_to_textfile

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

DATA_PATH = "data/dataset.csv"
MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "model.pkl")
REPORT_DIR = "reports"
N_ESTIMATORS = 50

# --- Prometheus metrics ---
TRAINING_DURATION  = Summary("training_duration_seconds", "Time taken to train the model")
TRAIN_SAMPLES      = Gauge("train_samples_total", "Number of training samples")
TEST_SAMPLES       = Gauge("test_samples_total", "Number of test samples")
TRAINING_COMPLETED = Counter("training_completed_total", "Number of times training completed successfully")


def load_data(path: str):
    df = pd.read_csv(path)
    X = df.drop(columns=["target"])
    y = df["target"]
    return X, y


def train(X_train, y_train):
    clf = RandomForestClassifier(n_estimators=N_ESTIMATORS, random_state=SEED)
    clf.fit(X_train, y_train)
    return clf


def save_model(model, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model, f)
    print(f"[train] Model saved to {path}")


if __name__ == "__main__":
    # Start Prometheus metrics server on port 8080
    start_http_server(8080)
    print("[train] Prometheus metrics server started on port 8080")

    # Wait for MLflow to be ready
    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    print("[train] Waiting for MLflow to be ready...")
    for i in range(10):
        try:
            r = requests.get(f"{mlflow_uri}/health")
            if r.status_code == 200:
                print("[train] MLflow is ready.")
                break
        except Exception:
            pass
        print(f"[train] MLflow not ready, retrying ({i+1}/10)...")
        time.sleep(3)

    print("[train] Loading data...")
    X, y = load_data(DATA_PATH)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED
    )

    # Record sample counts
    TRAIN_SAMPLES.set(len(X_train))
    TEST_SAMPLES.set(len(X_test))

    print("[train] Training model...")
    mlflow.set_experiment("ml-pipeline")
    with mlflow.start_run():
        # Log parameters to MLflow
        mlflow.log_param("model_type", "RandomForestClassifier")
        mlflow.log_param("n_estimators", N_ESTIMATORS)
        mlflow.log_param("random_state", SEED)
        mlflow.log_param("test_size", 0.2)

        # Train and track duration for Prometheus
        start = time.time()
        model = train(X_train, y_train)
        duration = time.time() - start
        TRAINING_DURATION.observe(duration)
        print(f"[train] Training took {duration:.2f}s")

        # Log model to MLflow
        mlflow.sklearn.log_model(model, artifact_path="model")
        print("[train] Model logged to MLflow.")

        # Save locally for evaluate.py
        save_model(model, MODEL_PATH)

        # Increment success counter
        TRAINING_COMPLETED.inc()

    # Write training metrics to .prom file for node-exporter to pick up
    os.makedirs(REPORT_DIR, exist_ok=True)
    write_to_textfile(f"{REPORT_DIR}/train_metrics.prom", REGISTRY)
    print(f"[train] Prometheus metrics written to {REPORT_DIR}/train_metrics.prom")

    print("[train] Done.")