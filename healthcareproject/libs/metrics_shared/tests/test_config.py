from fastapi import FastAPI
from fastapi.testclient import TestClient

from metrics_shared import instrument_metrics


def test_instrument_metrics_exposes_default_endpoint() -> None:
    app = FastAPI()
    instrument_metrics(app)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        client.get("/ping")  # generate at least one data point
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_instrument_metrics_supports_a_custom_endpoint() -> None:
    app = FastAPI()
    instrument_metrics(app, endpoint="/prom-metrics")

    with TestClient(app) as client:
        response = client.get("/prom-metrics")
        not_found = client.get("/metrics")

    assert response.status_code == 200
    assert not_found.status_code == 404
