import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from preprocessing import FEATURE_COLUMNS

QUERIES = {
    "cpu": "avg(process_cpu_seconds_total)",
    "memory": "avg(process_resident_memory_bytes)",
    "request_rate": "sum(rate(http_requests_total[1m]))",
    "http_5xx_ratio": '100 * sum(rate(http_requests_total{status=~"5.."}[1m])) / clamp_min(sum(rate(http_requests_total[1m])), 1)',
    "latency_p95": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le))",
    "backend_failures": "sum(rate(http_dependency_failures_total[1m]))",
}


def query_prometheus(prometheus_url: str, expression: str) -> float:
    url = f"{prometheus_url.rstrip('/')}/api/v1/query?" + urllib.parse.urlencode({"query": expression})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-detector/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("data", {}).get("result", [])
        if not result:
            return 0.0
        return float(result[0]["value"][1])
    except Exception:
        return 0.0


def detect_anomaly(artifact: dict, features: dict) -> dict:
    model = artifact["model"]
    scaler = artifact["scaler"]
    cutoff = artifact["cutoff"]

    vector = pd.DataFrame([features])[FEATURE_COLUMNS]
    scaled = scaler.transform(vector)
    score = float(model.decision_function(scaled)[0])
    is_anomaly = bool(score < cutoff)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "anomaly": is_anomaly,
        "score": round(score, 4),
        "cutoff": round(cutoff, 4),
        "metrics": {k: round(v, 4) for k, v in features.items()},
    }


def main():
    parser = argparse.ArgumentParser(description="AIOps real-time anomaly detector")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--model", default="ai-engine/model.joblib")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=15)
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}. Run evaluate.py first.")

    artifact = joblib.load(model_path)

    while True:
        features = {name: query_prometheus(args.prometheus_url, expr) for name, expr in QUERIES.items()}
        result = detect_anomaly(artifact, features)
        print(json.dumps(result))
        if args.once:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
