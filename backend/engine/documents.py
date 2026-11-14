"""Reading and writing the claim form and the policy (PDF), and the first two intake checks.

The documents are read by code, never by an AI. The standard is the demo team's template (`demo/documents/flood`,
`demo/documents/storm`): flat typed PDFs. On the claim form each label has its own line and its value is on the
next one; the policy has "Label:" lines in blocks (ASIGURAT, PERIOADA DE VALABILITATE, LOCAȚIA ASIGURATĂ …), where
only the first occurrence inside the right block counts. A PDF with form fields named as in CLAIM_FIELDS /
POLICY_FIELDS is still read by field name first. Labels are matched without diacritics or case, so a PDF drawn
without a Unicode font still reads.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Literal

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from engine.models import CheckItem, Flag, ReadDocument, StepResult

Kind = Literal["claim_form", "policy"]

# field name → label shown in the checks
CLAIM_FIELDS: dict[str, str] = {
    "numar_polita": "Număr poliță",
    "tip_dauna": "Tip de daună",
    "data_evenimentului": "Data evenimentului",
    "data_notificarii": "Data avizării",
    "adresa_daunei": "Adresa daunei",
    "latitudine": "Latitudine",
    "longitudine": "Longitudine",
    "descriere": "Descrierea daunei",
}

POLICY_FIELDS: dict[str, str] = {
    "numar_polita": "Număr poliță",
    "produs": "Produs",
    "riscuri_acoperite": "Riscuri acoperite",
    "suma_asigurata": "Suma asigurată",
    "nume_asigurat": "Nume asigurat",
    "cnp": "CNP/CUI",
    "email": "E-mail",
    "telefon": "Telefon",
    "adresa_titular": "Adresa asiguratului",
    "valabila_de_la": "Valabilă de la",
    "valabila_pana_la": "Valabilă până la",
    "zile_asteptare": "Perioadă de așteptare",
    "adresa_asigurata": "Adresa asigurată",
    "latitudine": "Latitudine",
    "longitudine": "Longitudine",
}

_FIELDS: dict[str, dict[str, str]] = {"claim_form": CLAIM_FIELDS, "policy": POLICY_FIELDS}
_OPTIONAL = {"latitudine", "longitudine", "cnp", "email", "telefon", "adresa_titular"}

# ---- the template's layout (the reader and the writer share it)
_CLAIM_TITLE = ("CERERE DE DESPĂGUBIRE", "Formular de avizare a daunei")
_CLAIM_LAYOUT: list[tuple[str | None, str, str]] = [   # (section starting here, label line, field)
    ("I. POLIȚA DE ASIGURARE", "NUMĂR POLIȚĂ", "numar_polita"),
    ("II. EVENIMENTUL ASIGURAT", "TIP DE DAUNĂ", "tip_dauna"),
    (None, "DATA EVENIMENTULUI", "data_evenimentului"),
    (None, "DATA AVIZĂRII", "data_notificarii"),
    ("III. LOCUL PRODUCERII DAUNEI", "ADRESA", "adresa_daunei"),
    (None, "LATITUDINE", "latitudine"),
    (None, "LONGITUDINE", "longitudine"),
]
_DESCRIPTION_FROM, _DESCRIPTION_TO = "IV. DESCRIEREA DAUNEI", "V. DECLARAȚIA ASIGURATULUI"

_POLICY_TITLE = ("Poliță de asigurare", "a locuinței")
_HOLDER, _LOCATION = "ASIGURAT", "LOCAȚIA ASIGURATĂ / CLĂDIREA CU DESTINAȚIE DE LOCUINȚĂ"
_POLICY_BLOCKS: list[tuple[str | None, list[tuple[str, str]]]] = [   # (block header, [(label, field)])
    (None, [("Nr.:", "numar_polita"), ("PRODUS:", "produs"), ("Riscuri acoperite prin contract:", "riscuri_acoperite"),
            ("SUMA ASIGURATĂ", "suma_asigurata")]),
    (_HOLDER, [("Nume/Denumire:", "_nume"), ("Prenume:", "_prenume"), ("CNP/CUI:", "cnp"), ("E-mail:", "email"),
               ("Telefon:", "telefon"), ("Adresa:", "adresa_titular")]),
    ("PERIOADA DE VALABILITATE", [("De la:", "valabila_de_la"), ("Până la:", "valabila_pana_la"),
                                  ("Perioadă de așteptare:", "zile_asteptare")]),
    (_LOCATION, [("Adresa:", "adresa_asigurata"), ("Latitudine:", "latitudine"), ("Longitudine:", "longitudine")]),
]
_SAME_LINE = {"Nr.:", "PRODUS:"}   # written "Nr.: P-8001"; the other labels have the value on the next line
_POLICY_HEADERS = {_HOLDER, "CONTRACTANT", "BENEFICIAR", "PERIOADA DE VALABILITATE", _LOCATION,
                   "MENȚIUNI SPECIALE"}

_DAMAGE = {"inundatie": "flood", "inundatii": "flood", "furtuna": "storm", "furtuni": "storm"}
_RISKS = {**_DAMAGE, "cutremur": "earthquake", "cutremure": "earthquake", "cutremur de pamant": "earthquake",
          "cutremure de pamant": "earthquake", "alunecare de teren": "landslide", "alunecari de teren": "landslide",
          "incendiu": "fire", "incendii": "fire"}
_DAMAGE_RO = {"flood": "inundație", "storm": "furtună"}
_RISKS_RO = {"flood": "inundații", "storm": "furtună", "earthquake": "cutremure de pământ",
             "landslide": "alunecări de teren", "fire": "incendiu"}


# ---------------------------------------------------------------- parsing helpers

def _cedilla(s: str) -> str:
    """ş/ţ with a cedilla (old encodings) → ș/ț with a comma below."""
    return s.translate(str.maketrans("şţŞŢ", "șțȘȚ"))


def _key(s: str) -> str:
    """For matching: no diacritics, no case, single spaces."""
    decomposed = unicodedata.normalize("NFKD", s or "")
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).casefold().split())


def _parse_date(raw: str | None) -> str | None:
    s = (raw or "").strip()
    for pat, order in ((r"(\d{4})-(\d{2})-(\d{2})", (0, 1, 2)), (r"(\d{2})[./](\d{2})[./](\d{4})", (2, 1, 0))):
        m = re.fullmatch(pat, s)
        if m:
            g = [int(x) for x in m.groups()]
            try:
                return date(g[order[0]], g[order[1]], g[order[2]]).isoformat()
            except ValueError:
                return None
    return None


def _parse_amount(raw: str | None) -> float | None:
    s = re.sub(r"(?i)\s*(ron|lei)\s*$", "", (raw or "").strip())
    s = s.replace(" ", "").replace("\u00a0", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d{1,2})?", s):  # Romanian: 100.000 / 48.000,50
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,2}", s):
        s = s.replace(",", ".")
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def _parse_days(raw: str | None) -> int | None:
    m = re.fullmatch(r"(\d+)(\s*(zile|zi))?", _key(raw or ""))
    return int(m.group(1)) if m else None


def _parse_coord(raw: str | None, limit: float) -> float | None:
    s = (raw or "").strip().replace(",", ".")
    if not re.fullmatch(r"-?\d{1,3}(\.\d+)?", s):
        return None
    x = float(s)
    return x if -limit <= x <= limit else None


def _parse_lat(raw: str | None) -> float | None:
    return _parse_coord(raw, 90)


def _parse_lon(raw: str | None) -> float | None:
    return _parse_coord(raw, 180)


def _parse_damage(raw: str | None) -> str | None:
    return _DAMAGE.get(_key(raw or ""))


def _parse_risks(raw: str | None) -> list[str] | None:
    parts = [_key(p) for p in (raw or "").split(",") if p.strip()]
    if not parts or any(p not in _RISKS for p in parts):
        return None
    return [_RISKS[p] for p in parts]


# ---------------------------------------------------------------- reading

def _unreadable(kind: Kind) -> ReadDocument:
    return ReadDocument(kind=kind, fields={}, missing=list(_FIELDS[kind]), readable=False)


def _text_lines(reader: PdfReader) -> list[str]:
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    return [_cedilla(" ".join(line.split())) for line in text.splitlines() if line.strip()]


def _blank(value: str) -> str:
    return "" if value.strip() in ("-", "—", "–") else value.strip()


def _index(lines: list[str], text: str, start: int = 0, end: int | None = None) -> int | None:
    k = _key(text)
    return next((i for i in range(start, len(lines) if end is None else end) if _key(lines[i]) == k), None)


def _value_after(lines: list[str], label: str, stops: set[str], start: int = 0, end: int | None = None) -> str:
    """The value of the first `label` in lines[start:end]: the next line, or the rest of the line for "Label: value"."""
    k = _key(label)
    for i in range(start, len(lines) if end is None else end):
        line = _key(lines[i])
        if line == k:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            return "" if _key(nxt) in stops else _blank(nxt)   # an empty value leaves the next label right after
        if label.endswith(":") and line.startswith(k):
            return _blank(lines[i].split(":", 1)[1])
    return ""


def _read_claim_lines(lines: list[str]) -> dict[str, str]:
    stops = {_key(x) for sec, label, _ in _CLAIM_LAYOUT for x in (sec, label) if x}
    stops |= {_key(_DESCRIPTION_FROM), _key(_DESCRIPTION_TO)}
    out: dict[str, str] = {}
    for section, label, field in _CLAIM_LAYOUT:
        start = (_index(lines, section) or 0) if section else 0
        out[field] = _value_after(lines, label, stops, start)
    begin = _index(lines, _DESCRIPTION_FROM)
    if begin is not None:
        stop = _index(lines, _DESCRIPTION_TO, begin + 1)
        out["descriere"] = _blank(" ".join(lines[begin + 1:stop]))
    return out


def _read_policy_lines(lines: list[str]) -> dict[str, str]:
    stops = {_key(label) for _, pairs in _POLICY_BLOCKS for label, _ in pairs} | {_key(h) for h in _POLICY_HEADERS}
    headers = {_key(h) for h in _POLICY_HEADERS}
    out: dict[str, str] = {}
    for header, pairs in _POLICY_BLOCKS:
        start, end = 0, None
        if header is not None:
            at = _index(lines, header)
            if at is None:   # no such block: its fields are missing (never read from another block)
                continue
            start = at + 1
            end = next((i for i in range(start, len(lines)) if _key(lines[i]) in headers), None)
        for label, field in pairs:
            out[field] = _value_after(lines, label, stops, start, end)
    out["nume_asigurat"] = " ".join(x for x in (out.pop("_prenume", ""), out.pop("_nume", "")) if x)
    return out


def read_document(path: Path, kind: Kind) -> ReadDocument:
    labels = _FIELDS[kind]
    try:
        reader = PdfReader(str(path))
        form = reader.get_fields() or {}
        if any(name in form for name in labels):
            values = {}
            for name in labels:
                v = form.get(name, {}).get("/V") if name in form else None
                values[name] = "" if v is None else _cedilla(str(v).strip())
        else:
            lines = _text_lines(reader)
            values = _read_claim_lines(lines) if kind == "claim_form" else _read_policy_lines(lines)
    except Exception:  # not a PDF, encrypted, corrupt, absent: unreadable, not an error
        return _unreadable(kind)
    fields = {k: values[k] for k in labels if values.get(k)}
    return ReadDocument(kind=kind, fields=fields, missing=[k for k in labels if k not in fields], readable=True)


# ---------------------------------------------------------------- writing (PDFs in the template's layout)

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_font_name: str | None = None


def _font() -> str:
    """A TrueType font that can draw ș/ț if this machine has one; otherwise Helvetica (drawn text loses diacritics)."""
    global _font_name
    if _font_name is None:
        _font_name = "Helvetica"
        for p in _FONT_CANDIDATES:
            if Path(p).exists():
                try:
                    pdfmetrics.registerFont(TTFont("ClaimLensSans", p))
                    _font_name = "ClaimLensSans"
                    break
                except Exception:
                    continue
    return _font_name


def has_unicode_font() -> bool:
    """True when a TrueType font with Romanian diacritics was found on this machine (the writer can draw them)."""
    return _font() != "Helvetica"


def _drawable(s: str) -> str:
    # Explicit fallback: without a Unicode TTF, Helvetica cannot draw ș/ț, so drawn text is transliterated to ASCII.
    # The labels still read (they are matched without diacritics); values lose their diacritics.
    if _font() != "Helvetica":
        return s
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _claim_lines(fields: dict[str, str]) -> list[str]:
    out = list(_CLAIM_TITLE)
    for section, label, field in _CLAIM_LAYOUT:
        out += ([section] if section else []) + [label, fields.get(field) or "-"]
    return out + [_DESCRIPTION_FROM, fields.get("descriere") or "-", _DESCRIPTION_TO]


def _policy_lines(fields: dict[str, str]) -> list[str]:
    name = (fields.get("nume_asigurat") or "").split()
    values = {**fields, "_nume": name[-1] if name else "", "_prenume": " ".join(name[:-1])}
    out = list(_POLICY_TITLE)
    for header, pairs in _POLICY_BLOCKS:
        out += [header] if header else []
        for label, field in pairs:
            value = values.get(field) or "-"
            out += [f"{label} {value}"] if label in _SAME_LINE else [label, value]
    return out


def write_document(fields: dict[str, str], kind: Kind, path: Path) -> None:
    """A flat typed PDF in the team template's layout (text lines, not their design), read by read_document."""
    lines = _claim_lines(fields) if kind == "claim_form" else _policy_lines(fields)
    c = canvas.Canvas(str(path), pagesize=A4)
    font, size, width = _font(), 10, A4[0] - 100
    c.setFont(font, size)
    y = 800
    for line in lines:
        for part in simpleSplit(_drawable(line), font, size, width) or [""]:   # a long description wraps
            if y < 50:
                c.showPage()
                c.setFont(font, size)
                y = 800
            c.drawString(50, y, part)
            y -= 16
    c.save()


# ---------------------------------------------------------------- engine dicts

def to_claim(claim_doc: ReadDocument, policy_doc: ReadDocument) -> tuple[dict, dict]:
    """Engine values from the two documents. The claim form has no claim number, no amount and no photo count;
    its coordinates (else the insured location's) locate the house."""
    c, p = claim_doc.fields, policy_doc.fields
    plat, plon = _parse_lat(p.get("latitudine")), _parse_lon(p.get("longitudine"))
    clat, clon = _parse_lat(c.get("latitudine")), _parse_lon(c.get("longitudine"))
    lat, lon = (clat, clon) if clat is not None and clon is not None else (plat, plon)
    claim = {
        "policy_id": c.get("numar_polita") or None,
        "damage_type": _parse_damage(c.get("tip_dauna")),
        "event_date": _parse_date(c.get("data_evenimentului")),
        "notified_at": _parse_date(c.get("data_notificarii")),
        "address": c.get("adresa_daunei") or None,
        "description": c.get("descriere") or None,
        "lat": lat if lon is not None else None,
        "lon": lon if lat is not None else None,
    }
    policy = {
        "id": p.get("numar_polita") or None,
        "holder_name": p.get("nume_asigurat") or None,
        "address": p.get("adresa_asigurata") or None,
        "lat": plat if plon is not None else None,
        "lon": plon if plat is not None else None,
        "valid_from": _parse_date(p.get("valabila_de_la")),
        "valid_to": _parse_date(p.get("valabila_pana_la")),
        "waiting_days": _parse_days(p.get("zile_asteptare")),
        "covered_risks": _parse_risks(p.get("riscuri_acoperite")),
        "sum_insured": _parse_amount(p.get("suma_asigurata")),
        "product": p.get("produs") or None,
    }
    return ({k: v for k, v in claim.items() if v is not None}, {k: v for k, v in policy.items() if v is not None})


def _amount_text(x) -> str:
    x = float(x)
    return str(int(x)) if x.is_integer() else f"{x:.2f}"   # never "123.456" (read as a thousands separator)


def from_claim(claim: dict, policy: dict) -> tuple[dict[str, str], dict[str, str]]:
    """The reverse of to_claim: the fields of the two PDFs, from the API's claim and policy dicts.

    Only what the template has is written. The claim's coordinates are not (the run locates the address); the amount
    and the photo count have no place on the form (the API keeps the amount on the claim). The policyholder's data
    goes on the policy: cnp, telefon (or phone) and email from the policy, else from the claim. Values the dicts do
    not have stay empty (the checks flag them, as they would on a paper form).
    """
    def text(v) -> str:
        return "" if v is None else str(v).strip()

    def day(v, sep: str) -> str:
        iso = _parse_date(text(v)[:10])
        return sep.join(reversed(iso.split("-"))) if iso else text(v)

    def amount(v) -> str:
        try:
            return f"{_amount_text(v)} RON" if v is not None and v != "" else ""
        except (TypeError, ValueError):
            return text(v)

    def either(key: str, *alt: str) -> str:
        return text(policy.get(key) or next((claim.get(k) for k in (key, *alt) if claim.get(k)), None))

    covered = policy.get("covered_risks")
    waiting = policy.get("waiting_days")
    claim_fields = {
        "numar_polita": text(claim.get("policy_id") or policy.get("id")),
        "tip_dauna": _DAMAGE_RO.get(claim.get("damage_type"), text(claim.get("damage_type"))),
        "data_evenimentului": day(claim.get("event_date"), "."),
        "data_notificarii": day(claim.get("notified_at"), "."),
        "adresa_daunei": text(claim.get("address")),
        "descriere": text(claim.get("description")),
    }
    policy_fields = {
        "numar_polita": text(policy.get("id")),
        "produs": text(policy.get("product")),
        "riscuri_acoperite": (", ".join(_RISKS_RO.get(r, text(r)) for r in covered) if isinstance(covered, list)
                              else text(covered)),
        "suma_asigurata": amount(policy.get("sum_insured")),
        "nume_asigurat": text(policy.get("holder_name") or claim.get("holder_name")),
        "cnp": either("cnp"),
        "email": either("email"),
        "telefon": either("telefon", "phone"),
        "adresa_titular": text(policy.get("holder_address") or policy.get("address")),
        "valabila_de_la": day(policy.get("valid_from"), "/"),
        "valabila_pana_la": day(policy.get("valid_to"), "/"),
        "zile_asteptare": f"{waiting} zile" if isinstance(waiting, int) else text(waiting),
        "adresa_asigurata": text(policy.get("address")),
        "latitudine": text(policy.get("lat")),
        "longitudine": text(policy.get("lon")),
    }
    return claim_fields, policy_fields


# ---------------------------------------------------------------- steps

def check_intake(docs: dict[str, Path | None], photos: list[Path], declared_photos: int | None) -> StepResult:
    """declared_photos is None when the claim form has no photo count (the team's template): no count check."""
    items: list[CheckItem] = []
    flags: list[Flag] = []
    for key, label, code in (("claim_form", "Cererea de despăgubire", "claim_form_missing"),
                             ("policy", "Polița", "policy_missing")):
        path = docs.get(key)
        if path is None:
            items.append(CheckItem(id=key, label=label, value=None, status="fail", reason="Document lipsă"))
            flags.append(Flag(step="intake", code=code, severity="fail", reason=f"{label}: document lipsă."))
        else:
            items.append(CheckItem(id=key, label=label, value=Path(path).name, status="ok"))
    n = len(photos)
    if declared_photos is not None and declared_photos != n:
        reason = f"Fotografii declarate: {declared_photos}, încărcate: {n}."
        items.append(CheckItem(id="photos", label="Fotografii", value=str(n), status="flag", reason=reason))
        flags.append(Flag(step="intake", code="photo_count_mismatch", field="photos", severity="warn", reason=reason))
    else:
        items.append(CheckItem(id="photos", label="Fotografii", value=str(n), status="ok"))
    return StepResult(step="intake", items=items, flags=flags)


_VALIDATORS = {
    "data_evenimentului": _parse_date, "data_notificarii": _parse_date,
    "valabila_de_la": _parse_date, "valabila_pana_la": _parse_date,
    "suma_asigurata": _parse_amount, "tip_dauna": _parse_damage, "riscuri_acoperite": _parse_risks,
    "zile_asteptare": _parse_days, "latitudine": _parse_lat, "longitudine": _parse_lon,
}


def check_documents(claim_doc: ReadDocument, policy_doc: ReadDocument) -> StepResult:
    items: list[CheckItem] = []
    flags: list[Flag] = []
    for doc, labels, prefix in ((claim_doc, CLAIM_FIELDS, "cerere"), (policy_doc, POLICY_FIELDS, "polita")):
        for name, label in labels.items():
            value = (doc.fields.get(name) or "").strip()
            item_id = f"{prefix}.{name}"
            if not value:
                if name in _OPTIONAL:
                    items.append(CheckItem(id=item_id, label=label, value=None, status="ok", reason="Câmp opțional necompletat"))
                    continue
                reason = f"{label}: câmp lipsă."
                items.append(CheckItem(id=item_id, label=label, value=None, status="flag", reason=reason))
                flags.append(Flag(step="documents", code="field_missing", field=name, severity="warn", reason=reason))
                continue
            validator = _VALIDATORS.get(name)
            if validator is not None and validator(value) is None:
                reason = f"{label}: valoarea „{value}” nu poate fi citită."
                items.append(CheckItem(id=item_id, label=label, value=value, status="flag", reason=reason))
                flags.append(Flag(step="documents", code="field_malformed", field=name, severity="warn", reason=reason))
                continue
            items.append(CheckItem(id=item_id, label=label, value=value, status="ok"))
    on_claim, on_policy = (claim_doc.fields.get("numar_polita") or "").strip(), (policy_doc.fields.get("numar_polita") or "").strip()
    if on_claim and on_policy and _key(on_claim) != _key(on_policy):
        reason = f"Numărul poliței din cerere („{on_claim}”) diferă de cel din poliță („{on_policy}”)."
        items.append(CheckItem(id="numar_polita_match", label="Același număr de poliță", value=on_claim, status="flag",
                               reason=reason))
        flags.append(Flag(step="documents", code="policy_number_mismatch", field="numar_polita", severity="warn",
                          reason=reason))
    return StepResult(step="documents", items=items, flags=flags)
