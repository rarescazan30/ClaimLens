from engine.client import check_client
from engine.geocode import GeoHit, geocode
from engine.models import ReadDocument
from engine.documents import CLAIM_FIELDS, POLICY_FIELDS
from engine.validators import cnp_valid, email_valid, iban_valid, phone_valid

CLAIM = {
    "nume_asigurat": "Persoană Sintetică", "cnp": "1960101170000", "telefon": "0722 123 456",
    "email": "nume@example.ro", "iban": "RO49 AAAA 1B31 0075 9384 0000",
    "adresa_daunei": "Str. Exemplu 12, Pechea, jud. Galați",
}
POLICY = {"nume_asigurat": "Persoană Sintetică", "cnp": "1960101170000",
          "adresa_asigurata": "Str. Exemplu 12, Pechea, jud. Galați"}
HOUSE = {"nominatim": [{"lat": "45.6", "lon": "27.7", "addresstype": "house"}]}


def doc(**over):
    f = {**CLAIM, **over}
    return ReadDocument(kind="claim_form", fields=f, missing=[k for k in CLAIM_FIELDS if not f.get(k)], readable=True)


def pol(**over):
    f = {**POLICY, **over}
    return ReadDocument(kind="policy", fields=f, missing=[k for k in POLICY_FIELDS if not f.get(k)], readable=True)


def codes(result):
    return [f.code for f in result.flags]


def test_cnp_and_iban_checksums():
    assert cnp_valid("1960101170000") and not cnp_valid("1960101170001")
    assert iban_valid("RO49 AAAA 1B31 0075 9384 0000") and not iban_valid("RO49AAAA1B31007593840001")


def test_phone_and_email_formats():
    assert phone_valid("0722 123 456") and phone_valid("+40722123456") and phone_valid("0722-123-456")
    assert not phone_valid("072212345")
    assert email_valid("a@b.ro") and not email_valid("a@b") and not email_valid("a b@c.ro")


async def test_geocode_precision(route):
    route({"nominatim": [{"lat": "45.6", "lon": "27.7", "addresstype": "road"}]})
    assert await geocode("Str. X, Pechea") == GeoHit(lat=45.6, lon=27.7, precision="street")


async def test_geocode_town_and_failures(route):
    route({"nominatim": [{"lat": "45.6", "lon": "27.7", "addresstype": "village"}]})
    assert (await geocode("Pechea")).precision == "town"
    route({"nominatim": []})
    assert await geocode("nicăieri") is None
    route({"nominatim": 500})
    assert await geocode("x") is None


async def test_clean_claim_has_no_flags(route):
    route(HOUSE)
    result, claim_pt, pol_pt = await check_client(doc(), pol())
    assert result.step == "client" and result.flags == []
    assert claim_pt == pol_pt == GeoHit(lat=45.6, lon=27.7, precision="house")


async def test_address_not_found_is_a_flag_not_an_error(route):
    route({"nominatim": []})
    result, point, _ = await check_client(doc(), pol())
    assert point is None and "address_not_found" in codes(result)


async def test_imprecise_address(route):
    route({"nominatim": [{"lat": "45.6", "lon": "27.7", "addresstype": "village"}]})
    result, point, _ = await check_client(doc(), pol())
    assert point.precision == "town" and "address_imprecise" in codes(result)


async def test_mismatched_cnp_and_bad_phone(route):
    route(HOUSE)
    result, _, _ = await check_client(doc(cnp="1960101170000", telefon="123"), pol(cnp="2960101170000"))
    assert {f.code for f in result.flags} >= {"cnp_mismatch", "phone_invalid"}


async def test_names_match_without_diacritics(route):
    route(HOUSE)
    result, _, _ = await check_client(doc(nume_asigurat="Persoană Sintetică"), pol(nume_asigurat="PERSOANA SINTETICA"))
    assert "name_mismatch" not in codes(result)
    result, _, _ = await check_client(doc(nume_asigurat="Alt Nume"), pol())
    assert "name_mismatch" in codes(result)


async def test_bad_cnp_email_iban_flagged(route):
    route(HOUSE)
    result, _, _ = await check_client(doc(cnp="1960101170001", email="nu-e-email", iban="RO00X"), pol(cnp="1960101170001"))
    assert {"cnp_invalid", "email_invalid", "iban_invalid"} <= set(codes(result))
    assert "cnp_mismatch" not in codes(result)


async def test_empty_optional_and_required_fields_give_info_not_flags(route):
    route(HOUSE)
    result, _, _ = await check_client(doc(email="", iban="", cnp="", telefon=""), pol())
    assert result.flags == []
    by_id = {i.id: i for i in result.items}
    assert by_id["email"].status == "info" and by_id["email"].reason == "nu este completat"
    assert by_id["iban"].status == "info" and by_id["cnp"].status == "info" and by_id["telefon"].status == "info"


async def test_cnp_and_iban_are_masked_in_items(route):
    route(HOUSE)
    result, _, _ = await check_client(doc(), pol())
    by_id = {i.id: i for i in result.items}
    assert by_id["cnp"].value == "•••••••••0000"
    assert by_id["iban"].value.endswith("0000") and "RO49" not in by_id["iban"].value
    assert "1960101170000" not in str([i.value for i in result.items])
