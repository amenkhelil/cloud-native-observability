import pandas as pd


FEATURE_COLUMNS = [
    "cpu",
    "memory",
    "request_rate",
    "http_5xx_ratio",
    "latency_p95",
    "backend_failures",
]


def load_windows(csv_path):
    frame = pd.read_csv(csv_path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    missing = set(FEATURE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {sorted(missing)}")
    if frame[FEATURE_COLUMNS].isna().any().any():
        raise ValueError("Feature columns must not contain missing values")
    if "failure_label" not in frame.columns:
        frame["failure_label"] = 0
    frame = frame.sort_values("timestamp")
    return frame

