"""Missing WFM facility may be recovered from same-row SE facility, never guessed across EIDs."""
from sqlalchemy import select
from app.database import Base, Credential, Issue, make_session
from app.importer import stage


def test_missing_wfm_facility_recovers_known_employee(tmp_path):
    engine, sessions = make_session(f"sqlite:///{tmp_path}/cards.db")
    Base.metadata.create_all(engine)
    payload = (
        "EID,NOMBRE,APELLIDOS,No TARJETA,No TARJETA SEC,Facility Code WFM,Facility Code SE\n"
        "53307,Luna,Jimenez,168086-11151054316-1,37014,,1761\n"
    ).encode()
    with sessions() as session:
        batch = stage(session, "sample.csv", payload)
        cards = session.scalars(select(Credential).where(Credential.batch_id == batch.id)).all()
        assert {(c.eid, c.facility_code, c.card_number, c.source) for c in cards} == {
            ("53307", 1761, 168086, "WFM"), ("53307", 1761, 37014, "SE")
        }
        assert batch.errors == 0
        assert any(i.code == "WFM_FACILITY_FROM_SE" for i in
                   session.scalars(select(Issue).where(Issue.batch_id == batch.id)).all())


def test_missing_both_facilities_stays_excluded(tmp_path):
    engine, sessions = make_session(f"sqlite:///{tmp_path}/cards.db")
    Base.metadata.create_all(engine)
    payload = (
        "EID,NOMBRE,No TARJETA,Facility Code WFM,Facility Code SE\n"
        "53307,Luna,168086,,\n"
        "12345,Other,37014,1761,\n"
    ).encode()
    with sessions() as session:
        batch = stage(session, "sample.csv", payload)
        cards = session.scalars(select(Credential).where(Credential.batch_id == batch.id)).all()
        assert {(c.eid, c.card_number) for c in cards} == {("12345", 37014)}
        assert any(i.code == "MISSING_FACILITY" for i in
                   session.scalars(select(Issue).where(Issue.batch_id == batch.id)).all())


def test_inferred_facility_collision_is_excluded(tmp_path):
    engine, sessions = make_session(f"sqlite:///{tmp_path}/cards.db")
    Base.metadata.create_all(engine)
    payload = (
        "EID,NOMBRE,No TARJETA,Facility Code WFM,Facility Code SE\n"
        "53307,Luna,168086,,1761\n"
        "99999,Other,168086,1761,\n"
        "12345,Third,37014,1761,\n"
    ).encode()
    with sessions() as session:
        batch = stage(session, "sample.csv", payload)
        cards = session.scalars(select(Credential).where(Credential.batch_id == batch.id)).all()
        assert {(c.eid, c.card_number) for c in cards} == {("12345", 37014)}
        assert any(i.code == "AMBIGUOUS_CARD" for i in
                   session.scalars(select(Issue).where(Issue.batch_id == batch.id)).all())
