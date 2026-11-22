import importlib.util
from pathlib import Path

import pandas as pd
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("evaluate", ROOT / "evaluate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_chronological_split_never_uses_failures_in_training(tmp_path):
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=20, freq="5min", tz="UTC"),
        "cpu": range(20),
        "memory": range(20),
        "request_rate": range(20),
        "http_5xx_ratio": [0] * 20,
        "latency_p95": range(20),
        "backend_failures": [0] * 20,
        "failure_label": [0] * 16 + [1] * 4,
    })
    training, threshold, holdout = module.chronological_split(frame)
    assert set(training["failure_label"]) == {0}
    assert set(threshold["failure_label"]) == {0}
    assert 1 in set(holdout["failure_label"])
    assert not set(training.index).intersection(holdout.index)


def test_missing_feature_values_are_rejected(tmp_path):
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC"),
        "cpu": [0.1, None, 0.3],
        "memory": [0.1, 0.2, 0.3],
        "request_rate": [1, 2, 3],
        "http_5xx_ratio": [0, 0, 0],
        "latency_p95": [0.1, 0.2, 0.3],
        "backend_failures": [0, 0, 0],
    })
    csv_path = tmp_path / "windows.csv"
    frame.to_csv(csv_path, index=False)

    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("evaluate", ROOT / "evaluate.py")
    evaluation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluation)

    try:
        evaluation.load_windows(csv_path)
    except ValueError as exc:
        assert "missing values" in str(exc)
    else:
        raise AssertionError("Missing feature values must be rejected")


def test_detector_identifies_anomaly(tmp_path):
    spec_det = importlib.util.spec_from_file_location("detector", ROOT / "detector.py")
    detector_mod = importlib.util.module_from_spec(spec_det)
    spec_det.loader.exec_module(detector_mod)

    model_path = tmp_path / "model.joblib"
    data_path = ROOT / "data" / "windows.csv"
    module.evaluate(str(data_path), str(model_path))

    import joblib
    artifact = joblib.load(model_path)

    normal_metrics = {
        "cpu": 0.20,
        "memory": 0.44,
        "request_rate": 15.0,
        "http_5xx_ratio": 0.0,
        "latency_p95": 0.14,
        "backend_failures": 0.0,
    }
    result_normal = detector_mod.detect_anomaly(artifact, normal_metrics)
    assert result_normal["anomaly"] is False

    failure_metrics = {
        "cpu": 0.85,
        "memory": 0.78,
        "request_rate": 48.0,
        "http_5xx_ratio": 0.30,
        "latency_p95": 1.85,
        "backend_failures": 12.0,
    }
    result_failure = detector_mod.detect_anomaly(artifact, failure_metrics)
    assert result_failure["anomaly"] is True

