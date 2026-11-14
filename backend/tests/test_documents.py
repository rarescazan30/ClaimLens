from pathlib import Path

import pytest

from engine.documents import (
    CLAIM_FIELDS, POLICY_FIELDS, check_documents, check_intake, has_unicode_font, read_document, to_claim, write_document,
)
from engine.models import ReadDocument

CLAIM = {
    "numar_dosar": "C-1042", "numar_polita": "P-7731", "nume_asigurat": "Persoană Sintetică Unu",
    "cnp": "1800101123456", "telefon": "+40 700 000 000", "email": "nume@example.ro",
    "iban": "RO49AAAA1B31007593840000", "adresa_daunei": "Str. Exemplu 12, Pechea, jud. Galați",
    "tip_dauna": "inundație", "data_evenimentului": "2024-09-14", "data_notificarii": "2024-09-19",
    "descriere": "Apa a intrat în casă", "suma_solicitata": "48000", "numar_fotografii": "3",
}
POLICY = {
    "numar_polita": "P-7731", "produs": "PAD", "nume_asigurat": "Persoană Sintetică Unu",
    "cnp": "1800101123456", "adresa_asigurata": "Str. Exemplu 12, Pechea, jud. Galați",
    "valabila_de_la": "2024-02-01", "valabila_pana_la": "2025-01-31", "zile_asteptare": "0",
    "riscuri_acoperite": "inundație, cutremur, alunecare de teren", "suma_asigurata": "100000",
}


def doc(**over):
    f = {**CLAIM, **over}
    return ReadDocument(kind="claim_form", fields=f, missing=[k for k in CLAIM_FIELDS if not f.get(k)], readable=True)


def pol(**over):
    f = {**POLICY, **over}
    return ReadDocument(kind="policy", fields=f, missing=[k for k in POLICY_FIELDS if not f.get(k)], readable=True)


def test_round_trip_reads_every_field(tmp_path):
    write_document(CLAIM, "claim_form", tmp_path / "c.pdf")
    d = read_document(tmp_path / "c.pdf", "claim_form")
    assert d.readable and d.missing == [] and d.fields["suma_solicitata"] == "48000"
    assert d.fields == CLAIM  # diacritics survive exactly


def test_policy_round_trip(tmp_path):
    write_document(POLICY, "policy", tmp_path / "p.pdf")
    d = read_document(tmp_path / "p.pdf", "policy")
    assert d.readable and d.fields == POLICY


def test_flat_text_pdf_is_read_by_labels(tmp_path):
    if not has_unicode_font():
        pytest.skip("no Unicode TrueType font on this machine; the flat writer cannot draw diacritic labels")
    from engine.documents import write_flat_document
    write_flat_document(POLICY, "policy", tmp_path / "f.pdf")
    d = read_document(tmp_path / "f.pdf", "policy")
    assert d.readable and d.missing == []
    assert d.fields["numar_polita"] == "P-7731"
    assert d.fields["riscuri_acoperite"] == POLICY["riscuri_acoperite"]
    assert d.fields["nume_asigurat"] == POLICY["nume_asigurat"]


def test_not_a_pdf_is_unreadable_not_an_error(tmp_path):
    (tmp_path / "x.pdf").write_text("hello")
    d = read_document(tmp_path / "x.pdf", "policy")
    assert d.readable is False and d.missing == list(POLICY_FIELDS)


def test_absent_file_is_unreadable(tmp_path):
    d = read_document(tmp_path / "nope.pdf", "claim_form")
    assert d.readable is False and d.missing == list(CLAIM_FIELDS)


def test_to_claim_maps_romanian_values():
    claim, policy = to_claim(
        doc(tip_dauna="inundație", data_evenimentului="14.09.2024", suma_solicitata="48.000 RON"),
        pol(riscuri_acoperite="inundație, cutremur"),
    )
    assert claim["damage_type"] == "flood" and claim["event_date"] == "2024-09-14" and claim["amount_claimed"] == 48000.0
    assert policy["covered_risks"] == ["flood", "earthquake"]


def test_to_claim_full_shape_and_no_personal_data():
    claim, policy = to_claim(doc(), pol())
    assert claim == {
        "id": "C-1042", "policy_id": "P-7731", "damage_type": "flood", "event_date": "2024-09-14",
        "notified_at": "2024-09-19", "address": "Str. Exemplu 12, Pechea, jud. Galați",
        "description": "Apa a intrat în casă", "amount_claimed": 48000.0, "declared_photos": 3,
    }
    assert policy == {
        "id": "P-7731", "holder_name": "Persoană Sintetică Unu", "address": "Str. Exemplu 12, Pechea, jud. Galați",
        "valid_from": "2024-02-01", "valid_to": "2025-01-31", "waiting_days": 0,
        "covered_risks": ["flood", "earthquake", "landslide"], "sum_insured": 100000.0, "product": "PAD",
    }


def test_amount_formats_and_storm():
    for raw in ("48.000", "48000", "48 000 RON"):
        assert to_claim(doc(suma_solicitata=raw), pol())[0]["amount_claimed"] == 48000.0
    assert to_claim(doc(tip_dauna="furtună"), pol())[0]["damage_type"] == "storm"


def test_unparseable_value_is_left_out():
    claim, _ = to_claim(doc(data_evenimentului="ieri", tip_dauna="meteorit"), pol())
    assert "event_date" not in claim and "damage_type" not in claim


def test_missing_and_malformed_fields_are_flagged():
    r = check_documents(doc(data_evenimentului="ieri", telefon=""), pol())
    assert {(f.code, f.field) for f in r.flags} == {("field_malformed", "data_evenimentului"), ("field_missing", "telefon")}
    assert all(f.severity == "warn" and f.step == "documents" for f in r.flags)


def test_clean_documents_have_no_flags_and_one_item_per_field():
    r = check_documents(doc(), pol())
    assert r.flags == [] and r.step == "documents"
    assert len(r.items) == len(CLAIM_FIELDS) + len(POLICY_FIELDS)


def test_optional_fields_may_be_empty():
    r = check_documents(doc(email="", iban="", numar_fotografii=""), pol())
    assert r.flags == []


def test_integer_fields_malformed():
    r = check_documents(doc(numar_fotografii="trei"), pol(zile_asteptare="zero"))
    assert {(f.code, f.field) for f in r.flags} == {("field_malformed", "numar_fotografii"), ("field_malformed", "zile_asteptare")}


def test_missing_policy_document_is_a_fail_flag():
    r = check_intake({"claim_form": Path("c.pdf"), "policy": None}, [], 0)
    assert [f.code for f in r.flags] == ["policy_missing"] and r.flags[0].severity == "fail"


def test_missing_claim_form_and_photo_mismatch():
    r = check_intake({"claim_form": None, "policy": Path("p.pdf")}, [Path("a.jpg")], 3)
    assert {(f.code, f.severity) for f in r.flags} == {("claim_form_missing", "fail"), ("photo_count_mismatch", "warn")}


def test_intake_all_good():
    r = check_intake({"claim_form": Path("c.pdf"), "policy": Path("p.pdf")}, [Path("a.jpg")], 1)
    assert r.flags == [] and r.step == "intake" and len(r.items) == 3
