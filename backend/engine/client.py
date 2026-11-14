"""Client data step: identity, contact, bank account and address checks. Findings are warnings, never verdicts.

The claim form carries the insured's name, CNP and IBAN; the policy carries the policyholder's data (CNP, phone,
e-mail). Claim-vs-policy comparisons run only when the claim side has the value. Coordinates written on
the documents locate the two points directly; only an address without coordinates is geocoded.
"""
from __future__ import annotations

import unicodedata

from engine.documents import _parse_lat, _parse_lon
from engine.geocode import GeoHit, geocode
from engine.models import CheckItem, Flag, ReadDocument, StepResult
from engine.validators import cnp_valid, email_valid, iban_valid, phone_valid


def _norm(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s or "")
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).casefold().split())


def _mask(s: str) -> str:
    s = "".join(s.split())
    return "•" * max(len(s) - 4, 0) + s[-4:]


async def check_client(claim_doc: ReadDocument, policy_doc: ReadDocument) -> tuple[StepResult, GeoHit | None, GeoHit | None]:
    c, p = claim_doc.fields, policy_doc.fields
    items: list[CheckItem] = []
    flags: list[Flag] = []

    def add(item_id: str, label: str, value: str | None, status: str, reason: str | None = None,
            code: str | None = None, field: str | None = None) -> None:
        items.append(CheckItem(id=item_id, label=label, value=value, status=status, reason=reason))
        if code:
            flags.append(Flag(step="client", code=code, field=field or item_id, severity="warn", reason=reason or ""))

    def get(d: dict, k: str) -> str:
        return (d.get(k) or "").strip()

    # Name
    name, pname = get(c, "nume_asigurat"), get(p, "nume_asigurat")
    if name and pname:
        if _norm(name) == _norm(pname):
            add("name", "Numele asiguratului", name, "ok")
        else:
            add("name", "Numele asiguratului", name, "flag",
                f"Numele din cerere („{name}”) diferă de cel din poliță („{pname}”).", "name_mismatch", "nume_asigurat")
    elif pname:
        add("name", "Numele asiguratului", pname, "info", "din poliță (cererea nu are numele asiguratului)")
    else:
        add("name", "Numele asiguratului", None, "info", "nu este completat")

    # CNP
    ccnp, pcnp = get(c, "cnp"), get(p, "cnp")
    cnp = ccnp or pcnp
    where = "din cerere" if ccnp else "asiguratului (din poliță)"
    if not cnp:
        add("cnp", "CNP", None, "info", "nu este completat")
    elif not cnp_valid(cnp):
        add("cnp", "CNP", _mask(cnp), "flag", f"CNP-ul {where} nu are un format valid (cifra de control nu corespunde).",
            "cnp_invalid", "cnp")
    else:
        add("cnp", "CNP", _mask(cnp), "ok")
    if ccnp and pcnp:
        if "".join(ccnp.split()) == "".join(pcnp.split()):
            add("cnp_match", "CNP identic în cerere și poliță", _mask(pcnp), "ok")
        else:
            add("cnp_match", "CNP identic în cerere și poliță", _mask(pcnp), "flag",
                "CNP-ul din cerere diferă de cel din poliță.", "cnp_mismatch", "cnp")

    # Phone
    phone = get(c, "telefon") or get(p, "telefon")
    if not phone:
        add("telefon", "Telefon", None, "info", "nu este completat")
    elif phone_valid(phone):
        add("telefon", "Telefon", phone, "ok")
    else:
        add("telefon", "Telefon", phone, "flag", "Numărul de telefon nu are un format românesc valid.", "phone_invalid", "telefon")

    # Email (optional)
    email = get(c, "email") or get(p, "email")
    if not email:
        add("email", "E-mail", None, "info", "nu este completat")
    elif email_valid(email):
        add("email", "E-mail", email, "ok")
    else:
        add("email", "E-mail", email, "flag", "Adresa de e-mail nu are un format valid.", "email_invalid", "email")

    # IBAN (optional)
    iban = get(c, "iban") or get(p, "iban")
    if not iban:
        add("iban", "IBAN", None, "info", "nu este completat")
    elif iban_valid(iban):
        add("iban", "IBAN", _mask(iban), "ok")
    else:
        add("iban", "IBAN", _mask(iban), "flag", "IBAN-ul nu este valid (cifra de control nu corespunde).", "iban_invalid", "iban")

    def written(d: dict) -> GeoHit | None:
        lat, lon = _parse_lat(d.get("latitudine")), _parse_lon(d.get("longitudine"))
        return GeoHit(lat=lat, lon=lon, precision="house") if lat is not None and lon is not None else None

    # Addresses: coordinates on the document first; otherwise looked up one after the other (Nominatim allows
    # about one request per second)
    claim_addr, policy_addr = get(c, "adresa_daunei"), get(p, "adresa_asigurata")
    claim_pt, policy_pt = written(c), written(p)
    claim_written, policy_written = claim_pt is not None, policy_pt is not None
    if claim_pt is None and claim_addr:
        claim_pt = await geocode(claim_addr)
    if policy_pt is None and policy_addr:
        policy_pt = await geocode(policy_addr)

    if claim_written:
        add("adresa_daunei", "Adresa daunei", claim_addr or None, "ok",
            f"Coordonate din cerere: {claim_pt.lat}, {claim_pt.lon}")
    elif not claim_addr:
        add("adresa_daunei", "Adresa daunei", None, "info", "nu este completat")
    elif claim_pt is None:
        add("adresa_daunei", "Adresa daunei", claim_addr, "flag", "Adresa daunei nu a putut fi localizată pe hartă.",
            "address_not_found", "adresa_daunei")
    elif claim_pt.precision == "town":
        add("adresa_daunei", "Adresa daunei", claim_addr, "flag",
            "Adresa a fost găsită doar la nivel de localitate, nu de stradă sau număr.", "address_imprecise", "adresa_daunei")
    else:
        add("adresa_daunei", "Adresa daunei", claim_addr, "ok")

    if policy_written:
        add("adresa_asigurata", "Adresa asigurată", policy_addr or None, "ok",
            f"Coordonate din poliță: {policy_pt.lat}, {policy_pt.lon}")
    elif not policy_addr:
        add("adresa_asigurata", "Adresa asigurată", None, "info", "nu este completat")
    elif policy_pt is None:
        add("adresa_asigurata", "Adresa asigurată", policy_addr, "info", "Adresa din poliță nu a putut fi localizată pe hartă.")
    else:
        add("adresa_asigurata", "Adresa asigurată", policy_addr, "ok")

    return StepResult(step="client", items=items, flags=flags), claim_pt, policy_pt
