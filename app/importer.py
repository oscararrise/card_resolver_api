"""Parse a whole roster into an immutable, reviewable dataset."""
import csv
import hashlib
import io
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select

from .database import Batch, Credential, Issue


class InvalidUpload(ValueError):
    pass


def normalize(value):
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def parse_card(value):
    s = str(value or "").strip()
    if not s:
        return None
    # Both "167794-1151022584-1" and "* 14570-..." are present.
    match = re.fullmatch(r"\*?\s*(\d{1,6})(?:\s*[- ]\s*\d{1,14}\s*[- ]\s*\d+)?\s*", s)
    if not match:
        raise ValueError("card value does not match a supported card number or compound card ID")
    return int(match.group(1))


def parse_facility(value):
    s = str(value or "").strip()
    if not s:
        return None
    if not re.fullmatch(r"\d{1,5}", s) or int(s) > 65535:
        raise ValueError("facility code must be an integer between 0 and 65535")
    return int(s)


def read_rows(filename, payload):
    suffix = Path(filename).suffix.lower()
    if suffix == ".xlsx":
        try:
            wb = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
            sheet = wb.active
            rows = list(sheet.values)
            wb.close()
            return rows
        except Exception as exc:
            raise InvalidUpload("invalid XLSX file") from exc
    if suffix == ".csv":
        decoded = None
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                decoded = payload.decode(encoding)
                break
            except UnicodeDecodeError:
                pass
        if decoded is None:
            raise InvalidUpload("CSV must be UTF-8 or Windows-1252")
        try:
            sample = decoded[:8192]
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = ","
        return list(csv.reader(io.StringIO(decoded), delimiter=delimiter))
    raise InvalidUpload("only CSV and XLSX files are supported")


def stage(session, filename, payload):
    if not payload:
        raise InvalidUpload("empty file")
    rows = read_rows(filename, payload)
    if len(rows) < 2:
        raise InvalidUpload("missing header or data rows")
    headers = [normalize(v) for v in rows[0]]

    def col(*names, required=True):
        indices = [headers.index(normalize(name)) for name in names if normalize(name) in headers]
        if indices:
            return indices[0]
        if required:
            raise InvalidUpload("missing required column: " + names[0])
        return None

    eid_col = col("EID", "HiBob ID", required=False)
    if eid_col is None:
        # The supplied BASE GENERAL has an unlabeled EID column B.
        if len(headers) > 1 and headers[0] in ("nro", "nro.") and not headers[1]:
            eid_col = 1
        else:
            raise InvalidUpload("missing EID column (unlabeled B is accepted only after Nro)")
    name_col = col("NOMBRE", "Nombre Completo")
    surname_col = col("APELLIDOS", required=False)
    primary_col = col("No TARJETA", "ID")
    secondary_col = col("No TARJETA SEC", required=False)
    fc_primary_col = col("Facility Code WFM")
    fc_secondary_col = col("Facility Code SE", required=False)
    replacement_cols = [col("REPOSICIÓN", required=False), col("SEGUNDA REPOSICIÓN", required=False)]

    batch = Batch(filename=Path(filename).name[:255], sha256=hashlib.sha256(payload).hexdigest(),
                  rows_read=0, loaded=0, skipped=0, errors=0, warnings=0, cards_count=0)
    session.add(batch)
    session.flush()

    def issue(row, level, code, detail):
        session.add(Issue(batch_id=batch.id, source_row=row, level=level, code=code, detail=detail))
        if level == "error":
            batch.errors += 1
        else:
            batch.warnings += 1

    candidates = []
    names_by_eid = defaultdict(set)
    for row_no, values in enumerate(rows[1:], start=2):
        if not any(str(v or "").strip() for v in values):
            continue
        batch.rows_read += 1

        def cell(index):
            return values[index] if index is not None and index < len(values) else None

        eid, name = str(cell(eid_col) or "").strip(), " ".join(
            str(cell(i) or "").strip() for i in (name_col, surname_col) if i is not None).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", eid) or not name:
            batch.skipped += 1
            issue(row_no, "error", "INVALID_EMPLOYEE", "missing or invalid EID/name; row skipped")
            continue
        names_by_eid[eid].add(normalize(name))
        if any(str(cell(i) or "").strip() for i in replacement_cols if i is not None):
            issue(row_no, "warning", "REPLACEMENT_UNVERIFIED", "replacement fields ignored pending validity rule")
        for source, card_col, fc_col in (("WFM", primary_col, fc_primary_col),
                                          ("SE", secondary_col, fc_secondary_col)):
            if card_col is None or not str(cell(card_col) or "").strip():
                continue
            try:
                card, fc = parse_card(cell(card_col)), parse_facility(cell(fc_col))
            except ValueError as exc:
                issue(row_no, "error", "INVALID_CARD", f"{source}: {exc}")
                continue
            if fc is None:
                issue(row_no, "error", "MISSING_FACILITY", f"{source}: card has no facility code")
                continue
            candidates.append((row_no, eid, name[:255], fc, card, source))

    for eid, names in names_by_eid.items():
        if len(names) > 1:
            issue(0, "error", "DUPLICATE_EID", f"EID {eid} has multiple names; all its cards excluded")

    by_key = defaultdict(list)
    for candidate in candidates:
        by_key[candidate[3:5]].append(candidate)
    loaded_rows = set()
    accepted_cards = 0
    for key, entries in by_key.items():
        eids = {item[1] for item in entries}
        if len(eids) > 1:
            issue(0, "error", "AMBIGUOUS_CARD", f"facility {key[0]}, card {key[1]} maps to multiple EIDs; excluded")
            continue
        if any(len(names_by_eid[eid]) > 1 for eid in eids):
            continue
        entry = entries[0]
        if len(entries) > 1:
            issue(entry[0], "warning", "DUPLICATE_CARD", f"facility {key[0]}, card {key[1]} repeated for the same EID")
        accepted_cards += 1
        loaded_rows.add(entry[0])
        session.add(Credential(batch_id=batch.id, source_row=entry[0], eid=entry[1],
                               full_name=entry[2], facility_code=key[0], card_number=key[1], source=entry[5]))
    for row_no, values in enumerate(rows[1:], start=2):
        if any(str(v or "").strip() for v in values) and row_no not in loaded_rows:
            issue(row_no, "warning", "ROW_NOT_LOADED", "no usable unambiguous card for this row")
    batch.cards_count = accepted_cards
    batch.loaded = len(loaded_rows)
    batch.skipped = batch.rows_read - batch.loaded
    if not batch.cards_count:
        raise InvalidUpload("no unambiguous cards could be imported")
    session.commit()
    return batch
