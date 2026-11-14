"""Reading and writing the claim form and the policy (PDF), and the first two intake checks.

The documents are read by code, never by an AI. A fillable form is read by field name; a flat typed PDF is read
from "<label>: <value>" lines. CLAIM_FIELDS / POLICY_FIELDS are the only place to change when the demo team's
real template arrives.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Literal

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from engine.models import CheckItem, Flag, ReadDocument, StepResult

Kind = Literal["claim_form", "policy"]

CLAIM_FIELDS: dict[str, str] = {
    "numar_dosar": "Număr dosar",
    "numar_polita": "Număr poliță",
    "nume_asigurat": "Nume asigurat",
    "cnp": "CNP",
    "telefon": "Telefon",
    "email": "E-mail",
    "iban": "IBAN",
    "adresa_daunei": "Adresa daunei",
    "tip_dauna": "Tip daună",
    "data_evenimentului": "Data evenimentului",
    "data_notificarii": "Data notificării",
    "descriere": "Descriere",
    "suma_solicitata": "Suma solicitată",
    "numar_fotografii": "Număr fotografii",
}

POLICY_FIELDS: dict[str, str] = {
    "numar_polita": "Număr poliță",
    "produs": "Produs",
    "nume_asigurat": "Nume asigurat",
    "cnp": "CNP",
    "adresa_asigurata": "Adresa asigurată",
    "valabila_de_la": "Valabilă de la",
    "valabila_pana_la": "Valabilă până la",
    "zile_asteptare": "Zile de așteptare",
    "riscuri_acoperite": "Riscuri acoperite",
    "suma_asigurata": "Suma asigurată",
}

_FIELDS: dict[str, dict[str, str]] = {"claim_form": CLAIM_FIELDS, "policy": POLICY_FIELDS}
_OPTIONAL = {"email", "iban", "numar_fotografii"}
_DAMAGE = {"inundație": "flood", "furtună": "storm"}
_RISKS = {**_DAMAGE, "cutremur": "earthquake", "alunecare de teren": "landslide", "incendiu": "fire"}


# ---------------------------------------------------------------- parsing helpers

def _parse_date(raw: str | None) -> str | None:
    s = (raw or "").strip()
    for pat, order in ((r"(\d{4})-(\d{2})-(\d{2})", (0, 1, 2)), (r"(\d{2})\.(\d{2})\.(\d{4})", (2, 1, 0))):
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
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # Romanian thousands separator
        s = s.replace(".", "")
    elif re.fullmatch(r"\d+,\d{1,2}", s):
        s = s.replace(",", ".")
    try:
        return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    s = (raw or "").strip()
    return int(s) if re.fullmatch(r"\d+", s) else None


def _norm(s: str) -> str:
    return s.strip().lower()


def _parse_damage(raw: str | None) -> str | None:
    return _DAMAGE.get(_norm(raw or ""))


def _parse_risks(raw: str | None) -> list[str] | None:
    parts = [_norm(p) for p in (raw or "").split(",") if p.strip()]
    if not parts or any(p not in _RISKS for p in parts):
        return None
    return [_RISKS[p] for p in parts]


# ---------------------------------------------------------------- reading

def _unreadable(kind: Kind) -> ReadDocument:
    return ReadDocument(kind=kind, fields={}, missing=list(_FIELDS[kind]), readable=False)


def _flat_fields(reader: PdfReader, labels: dict[str, str]) -> dict[str, str]:
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        for name, label in labels.items():
            if name not in out and line.startswith(label + ":"):
                out[name] = line[len(label) + 1:].strip()
                break
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
                values[name] = "" if v is None else str(v).strip()
        else:
            values = _flat_fields(reader, labels)
    except Exception:  # not a PDF, encrypted, corrupt, absent: unreadable, not an error
        return _unreadable(kind)
    fields = {k: v for k, v in values.items() if v}
    return ReadDocument(kind=kind, fields=fields, missing=[k for k in labels if k not in fields], readable=True)


# ---------------------------------------------------------------- writing (stand-in PDFs)

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
    # Form-field values are unaffected (set as text by pypdf), and the readers never depend on fonts.
    if _font() != "Helvetica":
        return s
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _write(fields: dict[str, str], kind: Kind, path: Path, *, fillable: bool) -> None:
    labels = _FIELDS[kind]
    c = canvas.Canvas(str(path), pagesize=A4)
    font = _font()
    c.setFont(font, 14)
    title = "Cerere de despăgubire" if kind == "claim_form" else "Poliță de asigurare"
    c.drawString(50, 800, _drawable(title))
    c.setFont(font, 10)
    y = 765
    for name, label in labels.items():
        value = fields.get(name, "")
        if fillable:
            c.drawString(50, y + 4, _drawable(label))
            c.acroForm.textfield(name=name, value="", x=190, y=y, width=350, height=18,
                                 fontName="Helvetica", fontSize=9, borderStyle="inset", forceBorder=True)
        else:
            c.drawString(50, y, _drawable(f"{label}: {value}"))
        y -= 28 if fillable else 20
    c.save()
    if fillable:
        _fill_form(fields, labels, path)


def _fill_form(fields: dict[str, str], labels: dict[str, str], path: Path) -> None:
    """reportlab cannot store non-Latin-1 text in a form field (ș, ț), so the values are set with pypdf."""
    writer = PdfWriter(clone_from=str(path))
    values = {name: fields.get(name, "") for name in labels}
    for page in writer.pages:
        writer.update_page_form_field_values(page, values, auto_regenerate=False)
    writer.set_need_appearances_writer(True)
    with open(path, "wb") as fh:
        writer.write(fh)


def write_document(fields: dict[str, str], kind: Kind, path: Path) -> None:
    """A stand-in fillable PDF whose form fields are named as in CLAIM_FIELDS / POLICY_FIELDS."""
    _write(fields, kind, path, fillable=True)


def write_flat_document(fields: dict[str, str], kind: Kind, path: Path) -> None:
    """A stand-in flat typed PDF ("<label>: <value>" lines), for testing the flat reader."""
    _write(fields, kind, path, fillable=False)


# ---------------------------------------------------------------- engine dicts

def to_claim(claim_doc: ReadDocument, policy_doc: ReadDocument) -> tuple[dict, dict]:
    c, p = claim_doc.fields, policy_doc.fields
    claim = {
        "id": c.get("numar_dosar") or None,
        "policy_id": c.get("numar_polita") or None,
        "damage_type": _parse_damage(c.get("tip_dauna")),
        "event_date": _parse_date(c.get("data_evenimentului")),
        "notified_at": _parse_date(c.get("data_notificarii")),
        "address": c.get("adresa_daunei") or None,
        "description": c.get("descriere") or None,
        "amount_claimed": _parse_amount(c.get("suma_solicitata")),
        "declared_photos": _parse_int(c.get("numar_fotografii")),
    }
    policy = {
        "id": p.get("numar_polita") or None,
        "holder_name": p.get("nume_asigurat") or None,
        "address": p.get("adresa_asigurata") or None,
        "valid_from": _parse_date(p.get("valabila_de_la")),
        "valid_to": _parse_date(p.get("valabila_pana_la")),
        "waiting_days": _parse_int(p.get("zile_asteptare")),
        "covered_risks": _parse_risks(p.get("riscuri_acoperite")),
        "sum_insured": _parse_amount(p.get("suma_asigurata")),
        "product": p.get("produs") or None,
    }
    return ({k: v for k, v in claim.items() if v is not None}, {k: v for k, v in policy.items() if v is not None})


def _amount_text(x) -> str:
    x = float(x)
    return str(int(x)) if x.is_integer() else f"{x:.2f}"   # never "123.456" (read as a thousands separator)


def from_claim(claim: dict, policy: dict) -> tuple[dict[str, str], dict[str, str]]:
    """The reverse of to_claim: form fields for the two PDFs, from the API's claim and policy dicts.

    The claim may also carry the policyholder's data, which has no column of its own: holder_name, cnp, phone,
    email, iban. Values the dicts do not have stay empty (the documents check flags them).
    """
    damage = {v: k for k, v in _DAMAGE.items()}
    risks = {v: k for k, v in _RISKS.items()}

    def text(v) -> str:
        return "" if v is None else str(v).strip()

    def day(v) -> str:
        return text(v)[:10]

    def amount(v) -> str:
        try:
            return _amount_text(v) if v is not None and v != "" else ""
        except (TypeError, ValueError):
            return text(v)
    photos = claim.get("photos")
    claim_fields = {
        "numar_dosar": text(claim.get("id")),
        "numar_polita": text(claim.get("policy_id") or policy.get("id")),
        "nume_asigurat": text(claim.get("holder_name") or policy.get("holder_name")),
        "cnp": text(claim.get("cnp")),
        "telefon": text(claim.get("phone")),
        "email": text(claim.get("email")),
        "iban": text(claim.get("iban")),
        "adresa_daunei": text(claim.get("address")),
        "tip_dauna": damage.get(claim.get("damage_type"), text(claim.get("damage_type"))),
        "data_evenimentului": day(claim.get("event_date")),
        "data_notificarii": day(claim.get("notified_at")),
        "descriere": text(claim.get("description")),
        "suma_solicitata": amount(claim.get("amount_claimed")),
        "numar_fotografii": str(len(photos)) if isinstance(photos, list) else "",
    }
    covered = policy.get("covered_risks")
    policy_fields = {
        "numar_polita": text(policy.get("id")),
        "produs": text(policy.get("product")),
        "nume_asigurat": text(policy.get("holder_name")),
        "cnp": text(policy.get("cnp")),
        "adresa_asigurata": text(policy.get("address")),
        "valabila_de_la": day(policy.get("valid_from")),
        "valabila_pana_la": day(policy.get("valid_to")),
        "zile_asteptare": text(policy.get("waiting_days")),
        "riscuri_acoperite": ", ".join(risks.get(r, text(r)) for r in covered) if isinstance(covered, list) else text(covered),
        "suma_asigurata": amount(policy.get("sum_insured")),
    }
    return claim_fields, policy_fields


# ---------------------------------------------------------------- steps

def check_intake(docs: dict[str, Path | None], photos: list[Path], declared_photos: int | None) -> StepResult:
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
        flags.append(Flag(step="intake", code="photo_count_mismatch", field="numar_fotografii",
                          severity="warn", reason=reason))
    else:
        items.append(CheckItem(id="photos", label="Fotografii", value=str(n), status="ok"))
    return StepResult(step="intake", items=items, flags=flags)


_VALIDATORS = {
    "data_evenimentului": _parse_date, "data_notificarii": _parse_date,
    "valabila_de_la": _parse_date, "valabila_pana_la": _parse_date,
    "suma_solicitata": _parse_amount, "suma_asigurata": _parse_amount,
    "tip_dauna": _parse_damage, "riscuri_acoperite": _parse_risks,
    "zile_asteptare": _parse_int, "numar_fotografii": _parse_int,
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
    return StepResult(step="documents", items=items, flags=flags)
