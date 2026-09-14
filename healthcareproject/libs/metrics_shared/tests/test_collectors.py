from fastapi import FastAPI
from fastapi.testclient import TestClient

from metrics_shared import instrument_metrics, register_gauge_collector, register_labeled_gauge_collector


def _metric_value(text: str, name: str) -> float:
    for line in text.splitlines():
        if line.startswith(f"{name} "):
            return float(line.split(" ")[1])
    raise AssertionError(f"{name} not found in metrics output:\n{text}")


def test_register_gauge_collector_reflects_live_external_state() -> None:
    # Starlette/FastAPI's response preparation calls the registry's
    # collect() more than once per request (e.g. for Content-Length) —
    # this test checks the gauge reflects current state, not an exact
    # call count, which is an implementation detail this shouldn't
    # depend on.
    state = {"value": 1.0}

    def _compute() -> dict[str, tuple[str, float]]:
        return {"test_gauge_value": ("Current external value", state["value"])}

    app = FastAPI()
    instrument_metrics(app)
    register_gauge_collector(_compute)

    with TestClient(app) as client:
        first = client.get("/metrics")
        assert _metric_value(first.text, "test_gauge_value") == 1.0

        state["value"] = 99.0
        second = client.get("/metrics")
        assert _metric_value(second.text, "test_gauge_value") == 99.0


def _metric_value_for_label(text: str, name: str, label_line: str) -> float:
    for line in text.splitlines():
        if line.startswith(name) and label_line in line:
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"{name}{{{label_line}}} not found in metrics output:\n{text}")


def test_register_labeled_gauge_collector_exposes_one_series_per_row() -> None:
    rows = {"open": 3.0, "reserved": 1.0}

    def _compute_rows() -> list[tuple[list[str], float]]:
        return [([status], count) for status, count in rows.items()]

    app = FastAPI()
    instrument_metrics(app)
    register_labeled_gauge_collector(
        "test_labeled_gauge", "Test labeled gauge", ["status"], _compute_rows
    )

    with TestClient(app) as client:
        text = client.get("/metrics").text
        assert _metric_value_for_label(text, "test_labeled_gauge", 'status="open"') == 3.0
        assert _metric_value_for_label(text, "test_labeled_gauge", 'status="reserved"') == 1.0
