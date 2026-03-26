"""
evaluate.py
Loads saved model artifact, runs evaluation, writes metrics report.
Pushes metrics to Prometheus and MLflow.
"""

import os
import json
import pickle
import numpy as np
import pandas as pd
import mlflow
from sklearn.model_selection import train_test_split
from prometheus_client import Gauge, write_to_textfile, REGISTRY

SEED = 42
DATA_PATH = "data/dataset.csv"
MODEL_PATH = "models/model.pkl"
REPORT_DIR = "reports"
REPORT_PATH = os.path.join(REPORT_DIR, "report.json")
METRICS_PATH = os.path.join(REPORT_DIR, "metrics.prom")

# --- Prometheus metrics ---
ACCURACY          = Gauge("model_accuracy", "Model accuracy on test set")
PRECISION_MACRO   = Gauge("model_precision_macro", "Model macro precision on test set")
N_TEST_SAMPLES    = Gauge("model_n_test_samples", "Number of test samples used in evaluation")


def load_model(path: str):
    with open(path, "rb") as f:
        return pickle.load(f)


def load_data(path: str):
    df = pd.read_csv(path)
    X = df.drop(columns=["target"])
    y = df["target"]
    return X, y


def evaluate(model, X_test, y_test):
    y_pred = model.predict(X_test)
    correct = y_pred == y_test.values
    accuracy = float(correct.sum() / len(y_pred))

    classes = np.unique(y_test)
    precisions = []
    for c in classes:
        tp = ((y_pred == c) & (y_test.values == c)).sum()
        fp = ((y_pred == c) & (y_test.values != c)).sum()
        precisions.append(tp / (tp + fp) if (tp + fp) > 0 else 0.0)
    precision = float(np.mean(precisions))

    return {
        "accuracy": accuracy,
        "precision_macro": round(precision, 4),
        "n_test_samples": len(y_test),
    }


def save_report(metrics: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[evaluate] Report saved to {path}")


if __name__ == "__main__":
    print("[evaluate] Loading model...")
    model = load_model(MODEL_PATH)

    print("[evaluate] Loading data...")
    X, y = load_data(DATA_PATH)
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED)

    print("[evaluate] Evaluating...")
    metrics = evaluate(model, X_test, y_test)

    # Push metrics to Prometheus gauges
    ACCURACY.set(metrics["accuracy"])
    PRECISION_MACRO.set(metrics["precision_macro"])
    N_TEST_SAMPLES.set(metrics["n_test_samples"])

    # Write metrics to .prom file so Prometheus can scrape them
    os.makedirs(REPORT_DIR, exist_ok=True)
    write_to_textfile(METRICS_PATH, REGISTRY)
    print(f"[evaluate] Prometheus metrics written to {METRICS_PATH}")
    mlflow.set_experiment("ml-pipeline")

    # Log metrics to MLflow
    with mlflow.start_run():
        mlflow.log_metric("accuracy", metrics["accuracy"])
        mlflow.log_metric("precision_macro", metrics["precision_macro"])
        mlflow.log_metric("n_test_samples", metrics["n_test_samples"])
        mlflow.log_artifact(MODEL_PATH, artifact_path="model")
    print("[evaluate] Metrics logged to MLflow.")

    save_report(metrics, REPORT_PATH)
    print("[evaluate] Done.")