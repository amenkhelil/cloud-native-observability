import argparse
import json
from datetime import timedelta

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_score, recall_score, f1_score
from sklearn.preprocessing import StandardScaler

from preprocessing import FEATURE_COLUMNS, load_windows


def chronological_split(frame, train_ratio=0.70, threshold_ratio=0.15):
    normal = frame[frame["failure_label"] == 0].copy()
    train_end = int(len(normal) * train_ratio)
    threshold_end = train_end + int(len(normal) * threshold_ratio)
    training = normal.iloc[:train_end]
    threshold = normal.iloc[train_end:threshold_end]
    if len(threshold) == 0:
        raise ValueError("Chronological split requires threshold-validation observations")
    holdout_start = threshold["timestamp"].max()
    holdout = frame[frame["timestamp"] > holdout_start].copy()
    if len(training) == 0 or len(threshold) == 0:
        raise ValueError("Chronological split requires normal training and threshold-validation observations")
    return training, threshold, holdout


def evaluate(csv_path, model_output):
    frame = load_windows(csv_path)
    training, threshold, holdout = chronological_split(frame)

    scaler = StandardScaler()
    training_scaled = scaler.fit_transform(training[FEATURE_COLUMNS])
    threshold_scaled = scaler.transform(threshold[FEATURE_COLUMNS])

    model = IsolationForest(
        n_estimators=100,
        contamination="auto",
        random_state=42,
    )
    model.fit(training_scaled)

    threshold_scores = model.decision_function(threshold_scaled)
    cutoff = float(np.quantile(threshold_scores, 0.05))

    holdout_scaled = scaler.transform(holdout[FEATURE_COLUMNS])
    holdout_scores = model.decision_function(holdout_scaled)
    predictions = (holdout_scores < cutoff).astype(int)
    labels = holdout["failure_label"].astype(int).to_numpy()

    precision = float(precision_score(labels, predictions, zero_division=0))
    recall = float(recall_score(labels, predictions, zero_division=0))
    f1 = float(f1_score(labels, predictions, zero_division=0))

    joblib.dump({"model": model, "scaler": scaler, "cutoff": cutoff}, model_output)
    return {
        "training_observations": len(training),
        "threshold_validation_observations": len(threshold),
        "holdout_observations": len(holdout),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_alerts": int(np.sum((predictions == 1) & (labels == 0))),
        "detected_failures": int(np.sum((predictions == 1) & (labels == 1))),
        "model_output": model_output,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--model-output", required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.input, args.model_output), indent=2))


if __name__ == "__main__":
    main()
