import pytest

from app.decoder import InvalidCard, decode


@pytest.mark.parametrize("raw,facility,card", [
    ("57944321056", 2152, 15339),
    ("54588877856", 2152, 15059),
    ("45864725536", 2152, 15189),
    ("104316604096", 1761, 14625),
    ("73245142048", 2152, 15112),
    ("89910480577", 1761, 167794),
])
def test_verified_scans(raw, facility, card):
    result = decode(raw)
    assert (result["facility_code"], result["card_number"]) == (facility, card)


def test_explicit_format_avoids_legacy_threshold():
    assert decode("12345", "h10304-reversed")["bits"] == 37
    assert decode("763100000")["format"] == "h10304-serbia"


@pytest.mark.parametrize("raw", ["-5", " 123", "12.5", "99999999999999999999"])
def test_invalid_raw(raw):
    with pytest.raises(InvalidCard):
        decode(raw)
