"""Compatibility with Lunch Control's decimal keyboard-wedge decoder.

The decimal alone does not identify a Wiegand format. 'auto' implements the
legacy heuristic; callers with known reader configuration should set format.
"""
import re


class InvalidCard(ValueError):
    pass


def decode(raw: str, format: str = "auto") -> dict:
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,20}", raw):
        raise InvalidCard("raw must be 1–20 ASCII decimal digits as a string")
    n = int(raw)
    if format not in {"auto", "h10301", "h10304-reversed", "h10304-serbia"}:
        raise InvalidCard("unsupported format")
    if format == "auto":
        format = ("h10301" if n < 100_000_000 else
                  "h10304-serbia" if 763_000_000 <= n <= 764_000_000 else
                  "h10304-reversed")
    width = 26 if format == "h10301" else 37
    if n >= 1 << width:
        raise InvalidCard("raw exceeds the selected format's bit width")
    bits = f"{n:0{width}b}"
    if format != "h10304-serbia":
        bits = bits[::-1]
    if width == 26:
        facility, card = int(bits[1:9], 2), int(bits[9:25], 2)
    else:
        facility, card = int(bits[1:17], 2), int(bits[17:36], 2)
    return {"format": format, "bits": width, "facility_code": facility,
            "card_number": card}
