import asyncio
import os
import time
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
    generate_latest,
)

SERVICE_NAME = "service-a"
BACKEND_URL = os.getenv("BACKEND_URL", "http://service-b:8081")
METRICS = CollectorRegistry()

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests processed",
    ("method", "path", "status"),
    registry=METRICS,
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ("method", "path"),
    registry=METRICS,
)
BACKEND_FAILURES = Counter(
    "http_dependency_failures_total",
    "Dependency request failures",
    ("dependency",),
    registry=METRICS,
)
BACKEND_LATENCY = Histogram(
    "backend_request_duration_seconds",
    "Backend request latency",
    ("dependency",),
    registry=METRICS,
)
AVAILABILITY = Gauge(
    "application_availability",
    "Application availability indicator",
    ("service",),
    registry=METRICS,
)
FAILURE_SIMULATION = Gauge(
    "failure_simulation_active",
    "Whether controlled failure simulation is active",
    ("mode",),
    registry=METRICS,
)
CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state: 0=closed, 1=open, 2=half_open",
    ("dependency",),
    registry=METRICS,
)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 10.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "closed"
        self.opened_at = 0.0
        self._update_metric()

    def _update_metric(self):
        val = 0 if self.state == "closed" else (1 if self.state == "open" else 2)
        CIRCUIT_BREAKER_STATE.labels(dependency="service-b").set(val)

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.monotonic() - self.opened_at >= self.recovery_timeout:
                self.state = "half_open"
                self._update_metric()
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = "closed"
        self._update_metric()

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold or self.state == "half_open":
            self.state = "open"
            self.opened_at = time.monotonic()
        self._update_metric()

    def reset(self):
        self.failure_count = 0
        self.state = "closed"
        self.opened_at = 0.0
        self._update_metric()

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


circuit_breaker = CircuitBreaker()

app = FastAPI(
    title="Service A",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
AVAILABILITY.labels(service=SERVICE_NAME).set(1)
failure_task = None


def consume_cpu(duration_seconds: float = 0.5):
    deadline = time.perf_counter() + duration_seconds
    value = 1
    while time.perf_counter() < deadline:
        value = (value * 1664525 + 1013904223) & 0xFFFFFFFF


@app.middleware("http")
async def observe_request(request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        print(f'{{"level":"error","service":"{SERVICE_NAME}","path":"{request.url.path}","error":"{type(exc).__name__}"}}')
        raise
    elapsed = time.perf_counter() - started
    path = request.url.path
    print(f'{{"level":"info","service":"{SERVICE_NAME}","method":"{request.method}","path":"{path}","status":{response.status_code},"duration_seconds":{elapsed:.6f}}}')
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    REQUEST_LATENCY.labels(request.method, path).observe(elapsed)
    return response


@app.get("/health")
async def health():
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/ready")
async def ready():
    mode = os.getenv("FAILURE_MODE", "")
    if mode == "dependency":
        return Response(
            content='{"status":"not_ready","service":"service-a"}',
            media_type="application/json",
            status_code=503,
        )
    return {"status": "ready", "service": SERVICE_NAME}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(METRICS), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/process")
async def process():
    if os.getenv("FAILURE_MODE", "") == "cpu":
        await asyncio.to_thread(consume_cpu, float(os.getenv("CPU_BURN_SECONDS", "0.5")))

    if os.getenv("FAILURE_MODE", "") == "http500":
        return Response(
            content='{"detail":"controlled HTTP 500 failure"}',
            media_type="application/json",
            status_code=500,
        )

    if os.getenv("FAILURE_MODE", "") == "latency":
        await asyncio.sleep(float(os.getenv("LATENCY_SECONDS", "1")))

    if os.getenv("FAILURE_MODE", "") == "dependency":
        BACKEND_FAILURES.labels("service-b").inc()
        return Response(
            content='{"detail":"controlled dependency failure"}',
            media_type="application/json",
            status_code=502,
        )

    if not circuit_breaker.can_execute():
        BACKEND_FAILURES.labels("service-b").inc()
        return Response(
            content='{"detail":"circuit breaker open: backend unavailable"}',
            media_type="application/json",
            status_code=503,
        )

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{BACKEND_URL}/api/work")
        BACKEND_LATENCY.labels("service-b").observe(time.perf_counter() - started)
        response.raise_for_status()
        circuit_breaker.record_success()
        return {
            "service": SERVICE_NAME,
            "backend": response.json(),
        }
    except (httpx.HTTPError, httpx.TimeoutException):
        circuit_breaker.record_failure()
        BACKEND_FAILURES.labels("service-b").inc()
        return Response(
            content='{"detail":"backend dependency unavailable"}',
            media_type="application/json",
            status_code=502,
        )


@app.post("/admin/failure")
async def set_failure(
    mode: str = "",
    duration_seconds: int = 60,
    x_failure_token: str | None = Header(default=None, alias="X-Failure-Token"),
):
    expected_token = os.getenv("FAILURE_ADMIN_TOKEN", "")
    if not expected_token or x_failure_token != expected_token:
        raise HTTPException(status_code=401, detail="failure admin authorization required")
    if os.getenv("FAILURE_SIMULATION_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="failure simulation is disabled")
    global failure_task
    if failure_task is not None:
        failure_task.cancel()
        failure_task = None
    duration_seconds = max(1, min(duration_seconds, 300))
    if mode not in ("", "http500", "latency", "dependency", "cpu"):
        raise HTTPException(status_code=400, detail="invalid failure mode")
    os.environ["FAILURE_MODE"] = mode
    for metric_mode in ("http500", "latency", "dependency", "cpu"):
        FAILURE_SIMULATION.labels(mode=metric_mode).set(
            1 if mode == metric_mode else 0
        )
    if mode:
        failure_task = asyncio.create_task(disable_failure_after(duration_seconds))
    return {
        "failure_mode": mode,
        "duration_seconds": duration_seconds,
        "note": "Disable the mode through POST /admin/failure with mode empty",
    }


async def disable_failure_after(duration_seconds: int):
    await asyncio.sleep(duration_seconds)
    os.environ["FAILURE_MODE"] = ""
    for metric_mode in ("http500", "latency", "dependency", "cpu"):
        FAILURE_SIMULATION.labels(mode=metric_mode).set(0)


@app.post("/admin/alertmanager")
async def receive_alertmanager(payload: dict):
    alerts = payload.get("alerts", [])
    event_file = Path(os.getenv("ALERTMANAGER_EVENT_FILE", "/tmp/alertmanager-events.jsonl"))
    event_file.parent.mkdir(parents=True, exist_ok=True)
    with event_file.open("a", encoding="utf-8") as log:
        for alert in alerts:
            status = alert.get("status", "")
            log.write(json.dumps({
                "status": status,
                "alertname": alert.get("labels", {}).get("alertname", ""),
                "service": alert.get("labels", {}).get("service", ""),
                "summary": alert.get("annotations", {}).get("summary", ""),
            }) + "\n")
            if status == "resolved":
                circuit_breaker.reset()
    return {"status": "received"}


@app.get("/admin/alertmanager/events")
async def alertmanager_events():
    event_file = Path(os.getenv("ALERTMANAGER_EVENT_FILE", "/tmp/alertmanager-events.jsonl"))
    if not event_file.exists():
        return {"alerts": []}
    with event_file.open("r", encoding="utf-8") as log:
        alerts = [json.loads(line) for line in log if line.strip()]
    return {"alerts": alerts[-50:]}


@app.get("/admin/circuit-breaker")
async def get_circuit_breaker():
    return circuit_breaker.snapshot()


@app.post("/admin/circuit-breaker/reset")
async def reset_circuit_breaker():
    circuit_breaker.reset()
    return {"status": "reset", "circuit_breaker": circuit_breaker.snapshot()}
