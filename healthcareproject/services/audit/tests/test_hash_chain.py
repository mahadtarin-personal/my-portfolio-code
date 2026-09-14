from fastapi.testclient import TestClient

from app import crud


def test_first_row_chains_from_genesis(db) -> None:
    row = crud.audit_log.append(db, event_id="e1", event_type="user.logged_in", actor="u1", payload={"a": 1})
    db.commit()
    assert row.prev_hash == "0" * 64
    assert len(row.hash) == 64


def test_second_row_chains_from_first(db) -> None:
    first = crud.audit_log.append(db, event_id="e1", event_type="user.logged_in", actor="u1", payload={})
    db.commit()
    second = crud.audit_log.append(db, event_id="e2", event_type="user.logged_in", actor="u2", payload={})
    db.commit()
    assert second.prev_hash == first.hash
    assert second.hash != first.hash


def test_append_is_idempotent_on_replayed_event_id(db) -> None:
    crud.audit_log.append(db, event_id="e1", event_type="user.logged_in", actor="u1", payload={})
    db.commit()
    result = crud.audit_log.append(db, event_id="e1", event_type="user.logged_in", actor="u1", payload={})
    db.commit()
    assert result is None
    assert len(crud.audit_log.list_recent(db)) == 1


def test_verify_chain_passes_on_untampered_data(db) -> None:
    for i in range(5):
        crud.audit_log.append(db, event_id=f"e{i}", event_type="patient.registered", actor=f"p{i}", payload={"i": i})
        db.commit()

    valid, broken_at_id, rows_checked = crud.audit_log.verify_chain(db)
    assert valid is True
    assert broken_at_id is None
    assert rows_checked == 5


def test_verify_chain_detects_tampering_and_reports_the_broken_row(db) -> None:
    # This is the actual security property design doc §13 describes: a
    # row altered in place (bypassing the INSERT-only DB grant somehow)
    # must be detectable, and *every row after it* should also fail since
    # they all chain forward from the tampered hash.
    for i in range(5):
        crud.audit_log.append(db, event_id=f"e{i}", event_type="patient.registered", actor=f"p{i}", payload={"i": i})
        db.commit()

    tampered = crud.audit_log.list_recent(db, limit=100)[-3]  # the 3rd row inserted (0-indexed: e2)
    tampered.payload = {"i": 999, "tampered": True}
    db.commit()

    valid, broken_at_id, rows_checked = crud.audit_log.verify_chain(db)
    assert valid is False
    assert broken_at_id == tampered.id
    assert rows_checked == 5


def test_verify_endpoint_reports_valid_chain(client: TestClient, db) -> None:
    crud.audit_log.append(db, event_id="e1", event_type="user.logged_in", actor="u1", payload={})
    db.commit()

    response = client.get("/audit/verify")
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["broken_at_id"] is None
    assert body["rows_checked"] == 1


def test_verify_endpoint_reports_broken_chain(client: TestClient, db) -> None:
    crud.audit_log.append(db, event_id="e1", event_type="user.logged_in", actor="u1", payload={})
    db.commit()
    row = crud.audit_log.list_recent(db)[0]
    row.hash = "tampered" * 8
    db.commit()

    response = client.get("/audit/verify")
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["broken_at_id"] == row.id
