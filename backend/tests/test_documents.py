from pathlib import Path

import pytest

from engine.documents import (
    CLAIM_FIELDS, POLICY_FIELDS, check_documents, check_intake, has_unicode_font, read_document, to_claim, write_document,
)
from engine.models import ReadDocument

CLAIM = {
    "numar_polita": "P-7731", "nume_asigurat": "Persoană Sintetică Unu", "cnp": "1780514170010",
    "iban": "RO31DEMO1004220715808001", "tip_dauna": "inundație", "data_evenimentului": "14.09.2024",
    "data_notificarii": "19.09.2024", "adresa_daunei": "Str. Exemplu 12, Pechea, jud. Galați",
    "latitudine": "45.6059", "longitudine": "27.78329", "descriere": "Apa a intrat în casă",
}
POLICY = {
    "numar_polita": "P-7731", "produs": "PAD", "riscuri_acoperite": "inundații, cutremure de pământ, alunecări de teren",
    "suma_asigurata": "100.000 RON", "nume_asigurat": "Persoană Sintetică Unu", "cnp": "1800101123456",
    "email": "nume@example.ro", "telefon": "0722 123 456", "adresa_titular": "Str. Exemplu 12, Pechea, jud. Galați",
    "valabila_de_la": "01/02/2024", "valabila_pana_la": "31/01/2025", "zile_asteptare": "0 zile",
    "adresa_asigurata": "Str. Exemplu 12, Pechea, jud. Galați", "latitudine": "45.6059", "longitudine": "27.78329",
}
needs_font = pytest.mark.skipif(not has_unicode_font(), reason="no Unicode TrueType font: drawn values lose diacritics")


def doc(**over):
    f = {**CLAIM, **over}
    return ReadDocument(kind="claim_form", fields=f, missing=[k for k in CLAIM_FIELDS if not f.get(k)], readable=True)


def pol(**over):
    f = {**POLICY, **over}
    return ReadDocument(kind="policy", fields=f, missing=[k for k in POLICY_FIELDS if not f.get(k)], readable=True)


@needs_font
def test_round_trip_reads_every_field(tmp_path):
    write_document(CLAIM, "claim_form", tmp_path / "c.pdf")
    d = read_document(tmp_path / "c.pdf", "claim_form")
    assert d.readable and d.missing == []
    assert d.fields == CLAIM  # diacritics survive exactly


@needs_font
def test_policy_round_trip(tmp_path):
    write_document(POLICY, "policy", tmp_path / "p.pdf")
    d = read_document(tmp_path / "p.pdf", "policy")
    assert d.readable and d.fields == POLICY


def test_empty_values_stay_empty_and_do_not_take_the_next_label(tmp_path):
    write_document({**CLAIM, "tip_dauna": "", "descriere": ""}, "claim_form", tmp_path / "c.pdf")
    d = read_document(tmp_path / "c.pdf", "claim_form")
    assert "tip_dauna" not in d.fields and "descriere" not in d.fields
    assert d.missing == ["tip_dauna", "descriere"] and d.fields["data_evenimentului"] == "14.09.2024"


def test_form_field_pdf_is_still_read_by_field_name(tmp_path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(tmp_path / "f.pdf"))
    c.drawString(50, 750, "Cerere")
    for i, (name, value) in enumerate((("numar_polita", "P-1"), ("tip_dauna", "furtuna"))):
        c.acroForm.textfield(name=name, value=value, x=50, y=700 - 30 * i, width=200, height=18)
    c.save()
    d = read_document(tmp_path / "f.pdf", "claim_form")
    assert d.readable and d.fields == {"numar_polita": "P-1", "tip_dauna": "furtuna"}
    assert to_claim(d, pol())[0]["damage_type"] == "storm"


def test_not_a_pdf_is_unreadable_not_an_error(tmp_path):
    (tmp_path / "x.pdf").write_text("hello")
    d = read_document(tmp_path / "x.pdf", "policy")
    assert d.readable is False and d.missing == list(POLICY_FIELDS)


def test_absent_file_is_unreadable(tmp_path):
    d = read_document(tmp_path / "nope.pdf", "claim_form")
    assert d.readable is False and d.missing == list(CLAIM_FIELDS)


def test_to_claim_maps_romanian_values():
    claim, policy = to_claim(doc(tip_dauna="inundatie", data_evenimentului="2024-09-14"),
                             pol(riscuri_acoperite="inundaţie, cutremur", suma_asigurata="48.000,50"))
    assert claim["damage_type"] == "flood" and claim["event_date"] == "2024-09-14"
    assert policy["covered_risks"] == ["flood", "earthquake"] and policy["sum_insured"] == 48000.5


def test_to_claim_full_shape_and_no_personal_data():
    claim, policy = to_claim(doc(), pol())
    assert claim == {
        "policy_id": "P-7731", "damage_type": "flood", "event_date": "2024-09-14", "notified_at": "2024-09-19",
        "address": "Str. Exemplu 12, Pechea, jud. Galați", "description": "Apa a intrat în casă",
        "lat": 45.6059, "lon": 27.78329,
    }
    assert policy == {
        "id": "P-7731", "holder_name": "Persoană Sintetică Unu", "address": "Str. Exemplu 12, Pechea, jud. Galați",
        "lat": 45.6059, "lon": 27.78329, "valid_from": "2024-02-01", "valid_to": "2025-01-31", "waiting_days": 0,
        "covered_risks": ["flood", "earthquake", "landslide"], "sum_insured": 100000.0, "product": "PAD",
    }


def test_claim_without_coordinates_takes_the_policy_location():
    claim, _ = to_claim(doc(latitudine="", longitudine=""), pol(latitudine="45.1", longitudine="27.1"))
    assert (claim["lat"], claim["lon"]) == (45.1, 27.1)


def test_amount_formats_and_storm():
    for raw in ("48.000", "48000", "48 000 RON", "48.000,00"):
        assert to_claim(doc(), pol(suma_asigurata=raw))[1]["sum_insured"] == 48000.0
    assert to_claim(doc(tip_dauna="furtună"), pol())[0]["damage_type"] == "storm"


def test_unparseable_value_is_left_out():
    claim, _ = to_claim(doc(data_evenimentului="ieri", tip_dauna="meteorit"), pol())
    assert "event_date" not in claim and "damage_type" not in claim


def test_missing_and_malformed_fields_are_flagged():
    r = check_documents(doc(data_evenimentului="ieri", descriere=""), pol())
    assert {(f.code, f.field) for f in r.flags} == {("field_malformed", "data_evenimentului"), ("field_missing", "descriere")}
    assert all(f.severity == "warn" and f.step == "documents" for f in r.flags)


def test_clean_documents_have_no_flags_and_one_item_per_field():
    r = check_documents(doc(), pol())
    assert r.flags == [] and r.step == "documents"
    assert len(r.items) == len(CLAIM_FIELDS) + len(POLICY_FIELDS)


def test_optional_fields_may_be_empty():
    r = check_documents(doc(latitudine="", longitudine=""), pol(cnp="", email="", telefon="", adresa_titular=""))
    assert r.flags == []


def test_integer_and_coordinate_fields_malformed():
    r = check_documents(doc(latitudine="nord"), pol(zile_asteptare="zero"))
    assert {(f.code, f.field) for f in r.flags} == {("field_malformed", "latitudine"), ("field_malformed", "zile_asteptare")}


def test_different_policy_numbers_are_a_warning():
    r = check_documents(doc(numar_polita="P-1"), pol())
    assert [(f.code, f.field, f.severity) for f in r.flags] == [("policy_number_mismatch", "numar_polita", "warn")]


def test_missing_policy_document_is_a_fail_flag():
    r = check_intake({"claim_form": Path("c.pdf"), "policy": None}, [], 0)
    assert [f.code for f in r.flags] == ["policy_missing"] and r.flags[0].severity == "fail"


def test_missing_claim_form_and_photo_mismatch():
    r = check_intake({"claim_form": None, "policy": Path("p.pdf")}, [Path("a.jpg")], 3)
    assert {(f.code, f.severity) for f in r.flags} == {("claim_form_missing", "fail"), ("photo_count_mismatch", "warn")}


def test_intake_all_good_and_no_declared_count_means_no_count_check():
    r = check_intake({"claim_form": Path("c.pdf"), "policy": Path("p.pdf")}, [Path("a.jpg")], 1)
    assert r.flags == [] and r.step == "intake" and len(r.items) == 3
    assert check_intake({"claim_form": Path("c.pdf"), "policy": Path("p.pdf")}, [Path("a.png")], None).flags == []


@needs_font
def test_from_claim_round_trips_through_the_pdfs(tmp_path):
    from engine.documents import from_claim
    claim = {"id": "C-7", "policy_id": "P-7", "damage_type": "flood", "event_date": "2024-09-14T00:00:00",
             "notified_at": "2024-09-16", "address": "Str. X 1", "description": "apă", "amount_claimed": 123.456,
             "photos": ["a.jpg", "b.jpg"], "cnp": "1800101123456", "phone": "0722123456"}
    policy = {"id": "P-7", "holder_name": "Ana Pop", "address": "Str. X 1", "lat": 45.6, "lon": 27.8,
              "valid_from": "2024-01-01", "valid_to": "2024-12-31", "waiting_days": 0,
              "covered_risks": ["flood", "earthquake"], "sum_insured": 100000.5, "product": "PAD"}
    cf, pf = from_claim(claim, policy)
    assert cf["tip_dauna"] == "inundație" and cf["data_evenimentului"] == "14.09.2024"
    assert pf["riscuri_acoperite"] == "inundații, cutremure de pământ" and pf["valabila_de_la"] == "01/01/2024"
    assert pf["cnp"] == "1800101123456" and pf["telefon"] == "0722123456"   # the policyholder's data, on the policy
    write_document(cf, "claim_form", tmp_path / "c.pdf")
    write_document(pf, "policy", tmp_path / "p.pdf")
    c, p = to_claim(read_document(tmp_path / "c.pdf", "claim_form"), read_document(tmp_path / "p.pdf", "policy"))
    assert c == {"policy_id": "P-7", "damage_type": "flood", "event_date": "2024-09-14", "notified_at": "2024-09-16",
                 "address": "Str. X 1", "description": "apă", "lat": 45.6, "lon": 27.8}   # the insured location's
    assert p == {**policy, "covered_risks": ["flood", "earthquake"]}


# ---- the demo team's documents (the standard template) ----------------------------------------
TEAM = Path(__file__).resolve().parents[2] / "demo" / "documents"


def team(name):
    return read_document(TEAM / name / "claim.pdf", "claim_form"), read_document(TEAM / name / "policy.pdf", "policy")


def test_team_claim_form_is_read():
    d = read_document(TEAM / "flood" / "claim.pdf", "claim_form")
    assert d.readable
    assert d.fields["tip_dauna"] == "inundație"
    assert d.fields["data_evenimentului"] == "14.09.2024"
    assert d.fields["adresa_daunei"] == "DJ255 nr. 19, Pechea, jud. Galați"
    assert d.fields["latitudine"] == "45.6319"
    assert d.fields["descriere"].startswith("Gospodărie inundată") and "mobilier compromise" in d.fields["descriere"]


def test_team_policy_is_read():
    d = read_document(TEAM / "flood" / "policy.pdf", "policy")
    assert d.readable
    assert d.fields["nume_asigurat"] == "Mircea Popescu"
    assert d.fields["cnp"] == "1780514170010"
    assert d.fields["valabila_de_la"] == "01/02/2024"
    assert d.fields["suma_asigurata"] == "100.000 RON"
    assert d.fields["zile_asteptare"] == "0 zile"
    assert d.fields["adresa_asigurata"] == "DJ255 nr. 19, Pechea, jud. Galați"
    assert d.fields["latitudine"] == "45.6319"


def test_team_documents_map_to_engine_values():
    claim, policy = to_claim(*team("flood"))
    assert claim["damage_type"] == "flood" and claim["event_date"] == "2024-09-14"
    assert claim["notified_at"] == "2024-09-16" and claim["lat"] == 45.6319
    assert policy["covered_risks"] == ["flood", "earthquake", "landslide"]
    assert policy["sum_insured"] == 100000.0 and policy["valid_from"] == "2024-02-01" and policy["waiting_days"] == 0
    claim, policy = to_claim(*team("storm"))
    assert claim["damage_type"] == "storm"
    assert policy["covered_risks"] == ["storm", "flood", "fire"] and policy["sum_insured"] == 250000.0


def test_team_documents_have_no_missing_required_fields():
    for name in ("flood", "storm"):
        r = check_documents(*team(name))
        assert not [f for f in r.flags if f.code in ("field_missing", "field_malformed")], (name, r.flags)
