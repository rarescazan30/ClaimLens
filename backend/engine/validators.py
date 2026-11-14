"""Format checks for the client's identity and contact data. Pure functions, no network."""
from __future__ import annotations

import re

_CNP_WEIGHTS = "279146358279"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^(07|\+407)\d{8}$")


def cnp_valid(s: str) -> bool:
    s = (s or "").strip()
    if not (len(s) == 13 and s.isascii() and s.isdigit()):
        return False
    check = sum(int(d) * int(w) for d, w in zip(s, _CNP_WEIGHTS)) % 11
    return (1 if check == 10 else check) == int(s[12])


def iban_valid(s: str) -> bool:
    s = re.sub(r"\s+", "", s or "").upper()
    if not (15 <= len(s) <= 34 and s.isascii() and s.isalnum()):
        return False
    moved = s[4:] + s[:4]
    number = "".join(str(int(c, 36)) for c in moved)  # A=10 … Z=35
    return int(number) % 97 == 1


def phone_valid(s: str) -> bool:
    return bool(_PHONE.match(re.sub(r"[\s-]", "", s or "")))


def email_valid(s: str) -> bool:
    return bool(_EMAIL.match((s or "").strip()))
