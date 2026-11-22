import importlib.util
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

module_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
spec = importlib.util.spec_from_file_location("service_a_main", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_metrics_exposes_prometheus_data():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


@pytest.mark.asyncio
async def test_http500_failure_is_explicit(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/admin/failure?mode=http500&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
        response = await client.get("/api/process")
        await client.post(
            "/admin/failure?mode=&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_http500_failure_requires_token(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/admin/failure?mode=http500&duration_seconds=1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_alertmanager_receiver_accepts_payload():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/admin/alertmanager",
            json={"alerts": [{"status": "firing"}]},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_alertmanager_events_can_be_read():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/alertmanager/events")
    assert response.status_code == 200
    assert "alerts" in response.json()


@pytest.mark.asyncio
async def test_latency_failure(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/admin/failure?mode=latency&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
        response = await client.get("/api/process")
        await client.post(
            "/admin/failure?mode=&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
    assert response.status_code in (200, 502)


@pytest.mark.asyncio
async def test_api_documentation_is_disabled():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        openapi = await client.get("/openapi.json")
        docs = await client.get("/docs")
    assert openapi.status_code == 404
    assert docs.status_code == 404


@pytest.mark.asyncio
async def test_dependency_failure(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/admin/failure?mode=dependency&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
        response = await client.get("/api/process")
        await client.post(
            "/admin/failure?mode=&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_cpu_failure(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("CPU_BURN_SECONDS", "0.01")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/admin/failure?mode=cpu&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
        response = await client.get("/api/process")
        await client.post(
            "/admin/failure?mode=&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
    assert response.status_code in (200, 502)


@pytest.mark.asyncio
async def test_invalid_failure_mode(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/admin/failure?mode=unknown&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_replacing_active_failure(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/admin/failure?mode=http500&duration_seconds=60",
            headers={"X-Failure-Token": "test-token"},
        )
        replacement = await client.post(
            "/admin/failure?mode=latency&duration_seconds=60",
            headers={"X-Failure-Token": "test-token"},
        )
        await client.post(
            "/admin/failure?mode=&duration_seconds=60",
            headers={"X-Failure-Token": "test-token"},
        )
    assert first.status_code == 200
    assert replacement.status_code == 200


@pytest.mark.asyncio
async def test_circuit_breaker_lifecycle():
    cb = module.circuit_breaker
    cb.reset()
    assert cb.state == "closed"
    assert cb.can_execute() is True

    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"

    cb.record_failure()
    assert cb.state == "open"
    assert cb.can_execute() is False

    cb.reset()
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_circuit_breaker_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/admin/circuit-breaker")
        assert res.status_code == 200
        assert "state" in res.json()

        reset_res = await client.post("/admin/circuit-breaker/reset")
        assert reset_res.status_code == 200
        assert reset_res.json()["circuit_breaker"]["state"] == "closed"


@pytest.mark.asyncio
async def test_alertmanager_resolved_resets_circuit():
    cb = module.circuit_breaker
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/admin/alertmanager",
            json={"alerts": [{"status": "resolved", "labels": {"alertname": "ServiceBUnavailable"}}]},
        )
    assert response.status_code == 200
    assert cb.state == "closed"

