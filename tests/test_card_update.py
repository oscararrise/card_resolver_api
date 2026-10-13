import base64

from fastapi.testclient import TestClient

from app import main
from app.database import Base, make_session


def test_mapping_create_resolve_conflict_and_reassign(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "long-admin-password")
    monkeypatch.setenv("SERVICE_TOKEN", "read-only-test-token")
    main.engine.dispose()
    main.engine, main.Session = make_session(f"sqlite:///{tmp_path}/mapping.db")
    Base.metadata.create_all(main.engine)
    basic = "Basic " + base64.b64encode(b"admin:long-admin-password").decode()
    with TestClient(main.app) as client:
        url = "/api/v1/cards/update"
        card = {"card_number_raw": "37744611008", "hibob_id": "43052"}
        assert client.post(url, json=card).status_code == 401
        assert client.post(url, json=card, headers={"Authorization": "Bearer read-only-test-token"}).status_code == 401
        created = client.post(url, json=card, headers={"Authorization": basic})
        assert created.status_code == 200, created.text
        assert created.json()["status"] == "created"
        assert created.json()["decoder"]["facility_code"] == 1761
        assert created.json()["decoder"]["card_number"] == 14641
        lookup = client.post("/api/v1/cards/resolve", json={"raw": "37744611008"},
                             headers={"Authorization": "Bearer read-only-test-token"})
        assert lookup.status_code == 200, lookup.text
        assert lookup.json()["employee"]["hibob_id"] == "43052"
        assert lookup.json()["source"] == "manual_mapping"
        repeat = client.post(url, json=card, headers={"Authorization": basic})
        assert repeat.status_code == 200 and repeat.json()["status"] == "unchanged"
        change = {**card, "hibob_id": "99999"}
        assert client.post(url, json=change, headers={"Authorization": basic}).status_code == 409
        change["overwrite"] = True
        updated = client.post(url, json=change, headers={"Authorization": basic})
        assert updated.status_code == 200 and updated.json()["status"] == "updated"
        lookup = client.post("/api/v1/cards/resolve", json={"raw": "37744611008"},
                             headers={"Authorization": "Bearer read-only-test-token"})
        assert lookup.json()["employee"]["hibob_id"] == "99999"


def test_mapping_requires_numeric_hibob_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "long-admin-password")
    main.engine.dispose()
    main.engine, main.Session = make_session(f"sqlite:///{tmp_path}/validation.db")
    Base.metadata.create_all(main.engine)
    basic = "Basic " + base64.b64encode(b"admin:long-admin-password").decode()
    with TestClient(main.app) as client:
        response = client.post("/api/v1/cards/update",
            json={"card_number_raw": "37744611008", "hibob_id": "someone-else"},
            headers={"Authorization": basic})
        assert response.status_code == 422
