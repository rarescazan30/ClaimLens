"""The demo claims' data: valid synthetic identities, the claim form's name/CNP/IBAN, and the photos' metadata."""
from pathlib import Path

import pytest
from PIL import Image

from engine.client import check_client
from engine.documents import read_document, to_claim
from engine.photos import check_photos, read_exif
from engine.validators import cnp_valid, iban_valid

DOCS = Path(__file__).resolve().parents[2] / "demo" / "documents"
PEOPLE = {   # folder: (name, CNP, IBAN)
    "flood": ("Mircea Popescu", "1780514170010", "RO31DEMO1004220715808001"),
    "storm": ("Maria Ionescu", "2850923170021", "RO04DEMO1004220715808002"),
    "paused": ("Andrei Stan", "1900711170033", "RO74DEMO1004220715808003"),
}


def docs(folder):
    return (read_document(DOCS / folder / "claim.pdf", "claim_form"),
            read_document(DOCS / folder / "policy.pdf", "policy"))


@pytest.mark.parametrize("folder", PEOPLE)
def test_synthetic_cnp_and_iban_are_valid_and_on_both_documents(folder):
    name, cnp, iban = PEOPLE[folder]
    assert cnp_valid(cnp) and iban_valid(iban) and iban[4:8] == "DEMO"
    claim, policy = docs(folder)
    assert (claim.fields["nume_asigurat"], claim.fields["cnp"], claim.fields["iban"]) == (name, cnp, iban)
    assert (policy.fields["nume_asigurat"], policy.fields["cnp"], policy.fields["iban"]) == (name, cnp, iban)


@pytest.mark.parametrize("folder", PEOPLE)
async def test_demo_claims_have_no_client_flags(folder, route):
    route({"nominatim": 500})   # the documents carry coordinates: nothing is geocoded
    result, _, _ = await check_client(*docs(folder))
    assert result.flags == []
    assert {i.id for i in result.items} >= {"name", "cnp", "cnp_match", "iban"}


def test_the_third_claim_is_another_person_with_an_expired_policy():
    claim, policy = to_claim(*docs("paused"))
    assert policy["holder_name"] == "Andrei Stan" and policy["valid_to"] < claim["event_date"]
    assert claim["address"].startswith("Str. Principală nr. 40, Pechea") and (claim["lat"], claim["lon"]) == (45.6315, 27.801)


def photo_flags(folder, earlier=()):
    claim, _ = to_claim(*docs(folder))
    result, _ = check_photos([DOCS / folder / "poza.jpg"], claim["event_date"], (claim["lat"], claim["lon"]),
                             list(earlier))
    return [f.code for f in result.flags]


def test_photo_metadata_per_claim():
    with Image.open(DOCS / "flood" / "poza.jpg") as im:
        taken, where = read_exif(im)
    assert taken.isoformat() == "2024-09-15" and where == pytest.approx((45.6319, 27.8017), abs=1e-4)
    assert photo_flags("flood") == []
    assert sorted(photo_flags("storm")) == ["photo_before_event", "photo_far_from_address"]
    assert photo_flags("paused", [DOCS / "flood" / "poza.jpg"]) == []   # its own photo, not a copy of C-8001's
    assert not list(DOCS.glob("*/*.png"))
