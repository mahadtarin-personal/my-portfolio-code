import httpx

from app.tasks.audit_verify import verify_audit_chain_task


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def test_valid_chain_logs_info_not_critical(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "app.tasks.audit_verify.httpx.get",
        lambda url, timeout=None: _FakeResponse({"valid": True, "broken_at_id": None, "rows_checked": 12}),
    )

    with caplog.at_level("INFO"):
        result = verify_audit_chain_task.delay().get()

    assert result == {"valid": True, "broken_at_id": None, "rows_checked": 12}
    assert not any(r.levelname == "CRITICAL" for r in caplog.records)
    assert any("verified clean" in r.message for r in caplog.records)


def test_broken_chain_pages(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "app.tasks.audit_verify.httpx.get",
        lambda url, timeout=None: _FakeResponse({"valid": False, "broken_at_id": 7, "rows_checked": 12}),
    )

    with caplog.at_level("CRITICAL"):
        result = verify_audit_chain_task.delay().get()

    assert result["valid"] is False
    critical_records = [r for r in caplog.records if r.levelname == "CRITICAL"]
    assert len(critical_records) == 1
    assert "PAGE" in critical_records[0].message
    assert "7" in critical_records[0].message


def test_unreachable_audit_service_does_not_page(monkeypatch, caplog) -> None:
    def _raise(url, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.tasks.audit_verify.httpx.get", _raise)

    with caplog.at_level("ERROR"):
        result = verify_audit_chain_task.delay().get()

    assert result is None
    assert not any(r.levelname == "CRITICAL" for r in caplog.records)
    assert any("could not reach audit service" in r.message for r in caplog.records)
