"""One-time safe bootstrap for verified facility card scans.

Run with the service environment (DATABASE_URL) and installed venv.
Aborts on mismatched physical card numbers or conflicting existing overrides.
"""
import os
from sqlalchemy import select
from app.database import Base, CardMapping, make_session
from app.decoder import decode

ROWS = [["44737","15110","26000501792"],
    ["46662","15223","64118336544"],
    ["45193","15158","29221727264"],
    ["43040","14653","50629512896"],
    ["13609","14615","131160149696"],
    ["42741","167556","8977190593"],
    ["44383","14837","115859328704"],
    ["43465","14666","22175354560"],
    ["44180","14839","64319721152"],
    ["46955","14638","100021636800"],
    ["46979","15281","38080097312"],
    ["46915","15182","30832340000"],
    ["43045","14617","40965836480"],
    ["43431","14681","110222184128"],
    ["43429","14680","7142969024"],
    ["42689","14591","68480470720"],
    ["45191","14619","126865182400"],
    ["46674","15221","115657944096"],
    ["45391","15083","126529580064"],
    ["44992","15099","59957586976"],
    ["43601","14689","36133998272"],
    ["43466","14672","71567478464"],
    ["47295","15342","32174517280"],
    ["43039","15022","31503428640"],
    ["43052","14641","37744611008"],
    ["43162","168175","135032803009"],
    ["42655","14583","132904980160"],
    ["13619","137743","136618249921"],
    ["44587","15263","67071126560"],
    ["47772","15186","88814398496"],
    ["43879","14808","76130881216"],
    ["45631","15062","28819074080"],
    ["13840","14606","30228418240"],
    ["13894","14519","63648632512"],
    ["45841","15053","48146426912"]]

def main():
    if not os.environ.get("DATABASE_URL") and not os.environ.get("DATABASE_URL_PARAMETER"):
        raise SystemExit("Set production DATABASE_URL or DATABASE_URL_PARAMETER; refusing sqlite fallback")
    engine, sessions = make_session()
    Base.metadata.create_all(engine)
    verified, rejected = [], []
    for eid, physical, raw in ROWS:
        decoded = decode(raw)
        if decoded["card_number"] != int(physical):
            rejected.append((eid, physical, raw, decoded["card_number"]))
        else:
            verified.append((eid, raw, decoded))
    print("verified:", len(verified), "rejected:", len(rejected))
    for bad in rejected:
        print("SKIPPED physical mismatch (eid, physical, raw, decoded):", bad)
    with sessions() as session:
        keys = [(d["facility_code"], d["card_number"]) for _, _, d in verified]
        if len(keys) != len(set(keys)):
            raise SystemExit("Duplicate decoded card keys; nothing inserted")
        for eid, raw, d in verified:
            existing = session.scalar(select(CardMapping).where(
                CardMapping.facility_code == d["facility_code"],
                CardMapping.card_number == d["card_number"]))
            if existing and existing.hibob_id != eid:
                raise SystemExit(f"Conflicting mapping for card {raw}; no changes committed")
            if not existing:
                session.add(CardMapping(
                    facility_code=d["facility_code"], card_number=d["card_number"],
                    hibob_id=eid, raw=raw, format=d["format"]))
        session.commit()
    print("Bootstrap finished (idempotent). Rejected rows require manual verification.")

if __name__ == "__main__":
    main()
