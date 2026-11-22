import argparse
import csv
import time
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone


QUERIES = {
    "cpu": 'avg(process_cpu_seconds_total)',
    "memory": 'avg(process_resident_memory_bytes)',
    "request_rate": 'sum(rate(http_requests_total[1m]))',
    "http_5xx_ratio": '100 * sum(rate(http_requests_total{status=~"5.."}[1m])) / clamp_min(sum(rate(http_requests_total[1m])), 1)',
    "latency_p95": 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le))',
    "backend_failures": 'sum(rate(http_dependency_failures_total[1m]))',
}


def query(prometheus_url, expression):
    url = f"{prometheus_url.rstrip('/')}/api/v1/query?" + urllib.parse.urlencode({"query": expression})
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("data", {}).get("result", [])
    if not result:
        return 0.0
    return float(result[0]["value"][1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--output", default="ai-engine/data/windows.csv")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--failure-label", type=int, choices=[0, 1], default=0)
    args = parser.parse_args()

    with open(args.output, "w", newline="", encoding="utf-8") as output:
        fields = ["timestamp", *QUERIES, "failure_label"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for _ in range(args.samples):
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "failure_label": args.failure_label,
            }
            for name, expression in QUERIES.items():
                row[name] = query(args.prometheus_url, expression)
            writer.writerow(row)
            time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
