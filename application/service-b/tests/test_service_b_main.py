import importlib.util
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

module_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
spec = importlib.util.spec_from_file_location("service_b_main", module_path)
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
    assert "application_availability" in response.text


@pytest.mark.asyncio
async def test_http500_failure_is_explicit(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/admin/failure?mode=http500&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
        response = await client.get("/api/work")
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
async def test_unavailable_failure(monkeypatch):
    monkeypatch.setenv("FAILURE_SIMULATION_ENABLED", "true")
    monkeypatch.setenv("FAILURE_ADMIN_TOKEN", "test-token")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/admin/failure?mode=unavailable&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
        response = await client.get("/ready")
        await client.post(
            "/admin/failure?mode=&duration_seconds=1",
            headers={"X-Failure-Token": "test-token"},
        )
    assert response.status_code == 503


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
