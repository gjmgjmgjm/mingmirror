"""Tests for event calibration REST endpoints."""

import pytest

from tools.destiny.calibrator import LifeEvent

try:
    from fastapi.testclient import TestClient  # type: ignore
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)


from config import ConfigLoader
from server.app import build_app


def _mock_analyzer():
    async def analyzer(chart, question):
        return {
            "per_system": [
                {
                    "system": "bazi",
                    "raw_result": {
                        "domain_analysis": {
                            "career": {"text": "今年事业晋升，工作顺利"}
                        }
                    },
                },
                {
                    "system": "qizheng",
                    "raw_result": {
                        "domain_analysis": {
                            "career": {"text": "官禄宫有吉星"}
                        }
                    },
                },
            ]
        }

    return analyzer


def test_create_and_list_events(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/charts/庚午%20辛巳%20庚辰%20壬午/events",
            json={
                "event_type": "job_change",
                "happened_at": "2020-06-01",
                "description": "跳槽到新公司",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chart_id"] == "庚午 辛巳 庚辰 壬午"
        assert data["event_type"] == "job_change"
        event_id = data["id"]

        resp = client.get("/api/v1/charts/庚午%20辛巳%20庚辰%20壬午/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        assert events[0]["id"] == event_id


def test_calibrate_endpoint(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)
    # Replace the analyzer to avoid real LLM calls.
    assert app.state.calibrator is not None
    app.state.calibrator.analyzer = _mock_analyzer()

    # Pre-seed an event directly in the store.
    event = LifeEvent.create(
        chart_id="庚午 辛巳 庚辰 壬午",
        event_type="job_change",
        happened_at="2020-06-01",
        description="跳槽到新公司",
    )
    app.state.event_store.add(event)

    with TestClient(app) as client:
        resp = client.post("/api/v1/charts/庚午%20辛巳%20庚辰%20壬午/calibrate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chart_id"] == "庚午 辛巳 庚辰 壬午"
        assert data["event_count"] == 1
        assert data["average_score"] > 0.0
        assert "bazi" in data["system_scores"]
        assert "qizheng" in data["system_scores"]
        assert sum(data["adjusted_weights"].values()) <= 1.05


def test_create_event_invalid_type(tmp_path):
    config = ConfigLoader(None)
    config.update(path=str(tmp_path))
    app = build_app(config)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/charts/庚午%20辛巳%20庚辰%20壬午/events",
            json={
                "event_type": "not_a_real_type",
                "happened_at": "2020-06-01",
            },
        )
        assert resp.status_code == 400
