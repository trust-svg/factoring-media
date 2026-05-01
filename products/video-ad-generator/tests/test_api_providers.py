"""GET /api/providers/capabilities のテスト。"""

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_capabilities_endpoint_returns_all_providers(client):
    resp = client.get("/api/providers/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    names = {p["name"] for p in data}
    assert names == {"seedance", "veo3_lite", "kling3_pro"}


def test_capabilities_seedance_has_extended_aspects(client):
    resp = client.get("/api/providers/capabilities")
    data = resp.json()
    seedance = next(p for p in data if p["name"] == "seedance")
    assert set(seedance["supported_aspects"]) == {
        "9:16",
        "16:9",
        "1:1",
        "4:3",
        "3:4",
        "21:9",
    }
    assert seedance["cost_basis"] == "per_second"
    assert seedance["rate_map"] == {"low": 0.081, "high": 0.13}
    assert seedance["supported_qualities"] == ["low", "high"]


def test_capabilities_response_shape(client):
    resp = client.get("/api/providers/capabilities")
    data = resp.json()
    expected_keys = {
        "name",
        "supported_aspects",
        "supported_qualities",
        "supported_durations",
        "rate_map",
        "cost_basis",
    }
    for entry in data:
        assert set(entry.keys()) == expected_keys


def test_capabilities_kling_per_video_default(client):
    resp = client.get("/api/providers/capabilities")
    data = resp.json()
    kling = next(p for p in data if p["name"] == "kling3_pro")
    assert kling["cost_basis"] == "per_video"
