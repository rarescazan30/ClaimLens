"""One-off patch of the demo team's PDFs (`demo/documents/flood|storm`): valid synthetic CNPs, an IBAN, and the
insured's name, CNP and IBAN on the claim form. Run once on the team's originals; the patched PDFs are committed.

- policy.pdf: the old CNP is replaced in the page's own text (same font, same digit count, so the look is unchanged
  and the text layer no longer holds the old value); an "IBAN:" line is added in the ASIGURAT block, right of Adresa.
- claim.pdf: NUME ASIGURAT and CNP in section I (columns 2 and 3), IBAN above the signatures, and the insured's name
  under "Asigurat" in the signature area. Labels and values are drawn in the reader's "label line, value next line"
  layout.

    cd backend && .venv/bin/python scripts/patch_team_pdfs.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pypdf import PdfReader, PdfWriter  # noqa: E402
from pypdf.generic import ContentStream, NameObject  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from engine.documents import _font, has_unicode_font  # noqa: E402

DOCS = Path(__file__).resolve().parents[2] / "demo" / "documents"
PEOPLE = {   # folder: (name, old CNP, new CNP, IBAN)
    "flood": ("Mircea Popescu", "1780514170015", "1780514170010", "RO31DEMO1004220715808001"),
    "storm": ("Maria Ionescu", "2850923170020", "2850923170021", "RO04DEMO1004220715808002"),
}
LABEL_RGB, VALUE_RGB = (0.3725, 0.4196, 0.4627), (0.102, 0.102, 0.102)   # the template's grey labels, dark values


def _overlay(page, draw) -> None:
    box = page.mediabox
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(float(box.width), float(box.height)))
    draw(c)
    c.save()
    page.merge_page(PdfReader(buf).pages[0])


def _bold() -> str:
    """Arial Bold next to the reader's font when there is one (the policy's labels are bold), else that font."""
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(p).exists():
            pdfmetrics.registerFont(TTFont("ClaimLensSansBold", p))
            return "ClaimLensSansBold"
    return _font()


def _text(c, x, y, s, size, rgb, font: str | None = None) -> None:
    c.setFillColorRGB(*rgb)
    c.setFont(font or _font(), size)
    c.drawString(x, y, s)


def patch_policy(path: Path, old: str, new: str, iban: str) -> None:
    reader = PdfReader(str(path))
    writer = PdfWriter()
    writer.append(reader)
    page = writer.pages[0]
    data = page.get_contents().get_data()
    hits = data.count(f"({old})".encode())
    if hits == 0:
        sys.exit(f"{path}: old CNP not found (already patched?)")
    content = ContentStream(None, writer)
    content.set_data(data.replace(f"({old})".encode(), f"({new})".encode()))
    page[NameObject("/Contents")] = writer._add_object(content)

    def draw(c):   # right half of the ASIGURAT block's Adresa row (x of "Fax:", y of "Adresa:")
        bold = _bold()
        _text(c, 307.73, 545.39, "IBAN:", 7.6, VALUE_RGB, bold)
        _text(c, 307.73 + stringWidth("IBAN:", bold, 7.6) + 4, 545.39, iban, 7.8, VALUE_RGB)
    _overlay(page, draw)
    with open(path, "wb") as f:
        writer.write(f)
    print(f"{path.relative_to(DOCS.parent)}: CNP replaced {hits}x, IBAN added")


def patch_claim(path: Path, name: str, cnp: str, iban: str) -> None:
    writer = PdfWriter()
    writer.append(PdfReader(str(path)))

    def draw(c):
        for x, label, value in ((215.43, "NUME ASIGURAT", name), (379.84, "CNP", cnp)):   # section I, columns 2, 3
            _text(c, x, 639.21, label, 7, LABEL_RGB)
            _text(c, x + 2.27, 623.34, value, 10.3, VALUE_RGB)
        _text(c, 51.02, 190, "IBAN", 7, LABEL_RGB)   # between the declaration and the signatures
        _text(c, 53.29, 174.13, iban, 10.3, VALUE_RGB)
        _text(c, 51.02, 58, name, 10.3, VALUE_RGB)   # signature area, under "Asigurat / Semnătură"
    _overlay(writer.pages[0], draw)
    with open(path, "wb") as f:
        writer.write(f)
    print(f"{path.relative_to(DOCS.parent)}: name, CNP, IBAN added")


def main() -> None:
    if not has_unicode_font():
        sys.exit("No Unicode TrueType font found: names would lose their diacritics. Not patching.")
    for folder, (name, old, new, iban) in PEOPLE.items():
        patch_policy(DOCS / folder / "policy.pdf", old, new, iban)
        patch_claim(DOCS / folder / "claim.pdf", name, new, iban)


if __name__ == "__main__":
    main()
