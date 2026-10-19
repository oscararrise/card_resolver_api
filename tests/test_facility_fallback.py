"""Regression tests for HID card readers whose facility code differs from roster."""
from fastapi.testclient import TestClient
from app import main
from app.database import Active, Base, Batch, Credential, make_session


def setup_roster(tmp_path, monkeypatch, cards):
    monkeypatch.setenv("SERVICE_TOKEN", "test-service-token")
    main.engine.dispose()
    main.engine, main.Session = make_session(f"sqlite:///{tmp_path}/fallback.db")
    Base.metadata.create_all(main.engine)
    with main.Session() as session:
        batch = Batch(filename="test.csv", sha256="0" * 64, rows_read=len(cards),
                      loaded=len(cards), skipped=0, errors=0, warnings=0,
                      cards_count=len(cards), status="active")
        session.add(batch)
        session.flush()
        session.add(Active(id=1, batch_id=batch.id))
        for index, (eid, facility, number) in enumerate(cards, start=2):
            session.add(Credential(batch_id=batch.id, source_row=index, eid=eid,
                                   full_name="Employee " + eid, facility_code=facility,
                                   card_number=number, source="WFM"))
        session.commit()


def resolve(client, raw):
    return client.post("/api/v1/cards/resolve", json={"raw": raw},
                       headers={"Authorization": "Bearer test-service-token"})


def test_known_card_resolves_despite_facility_discrepancy(tmp_path, monkeypatch):
    setup_roster(tmp_path, monkeypatch, [("12986", 2152, 14618)])
    with TestClient(main.app) as client:
        response = resolve(client, "23785967296")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["employee"]["hibob_id"] == "12986"
    assert body["decoder"]["facility_code"] == 1761
    assert body["decoder"]["card_number"] == 14618
    assert body["source"] == "unique_card_number_fallback"
    assert body["facility_mismatch"] is True
    assert body["roster_facility_codes"] == [2152]


def test_exact_facility_card_still_has_priority(tmp_path, monkeypatch):
    setup_roster(tmp_path, monkeypatch, [("12986", 2152, 14618),
                                          ("99999", 1761, 14618)])
    with TestClient(main.app) as client:
        response = resolve(client, "23785967296")
    assert response.status_code == 200, response.text
    assert response.json()["employee"]["hibob_id"] == "99999"
    assert response.json()["source"] == "exact_facility_card"


def test_ambiguous_fallback_does_not_guess_employee(tmp_path, monkeypatch):
    setup_roster(tmp_path, monkeypatch, [("12986", 2152, 14618),
                                          ("99999", 3000, 14618)])
    with TestClient(main.app) as client:
        response = resolve(client, "23785967296")
    assert response.status_code == 409
    assert "ambiguous" in response.json()["detail"]


def test_missing_card_returns_404(tmp_path, monkeypatch):
    setup_roster(tmp_path, monkeypatch, [("12986", 2152, 14618)])
    with TestClient(main.app) as client:
        response = resolve(client, "57944321056")
    assert response.status_code == 404


def test_same_employee_across_multiple_facilities_is_safe(tmp_path, monkeypatch):
    setup_roster(tmp_path, monkeypatch, [("12986", 2152, 14618),
                                          ("12986", 3000, 14618)])
    with TestClient(main.app) as client:
        response = resolve(client, "23785967296")
    assert response.status_code == 200
    assert response.json()["employee"]["hibob_id"] == "12986"
    assert response.json()["roster_facility_codes"] == [2152, 3000]
