from engine.geocode import GeoHit
from engine.rules import check_policy, context_term, policy_flags

POLICY = {"id": "P", "address": "Str. Exemplu 12, Pechea", "valid_from": "2024-02-01", "valid_to": "2025-01-31",
          "waiting_days": 5, "covered_risks": ["flood"], "sum_insured": 100000}
CLAIM = {"id": "C", "damage_type": "flood", "event_date": "2024-09-14", "notified_at": "2024-09-19",
         "address": "str. exemplu 12,  Pechea", "amount_claimed": 40000}


def flags(claim=None, policy=None):
    return {f.rule: f for f in check_policy({**CLAIM, **(claim or {})}, {**POLICY, **(policy or {})})}


def test_all_six_rules_pass_for_a_clean_claim():
    f = flags()
    assert sorted(f) == ["address_match", "amount_within_sum_insured", "notified_in_time", "policy_active", "risk_covered",
                       "waiting_period"]
    assert all(x.passed for x in f.values())


def test_event_inside_waiting_period_fails():
    assert not flags(claim={"event_date": "2024-02-03"})["waiting_period"].passed


def test_event_after_expiry_fails_policy_active():
    assert not flags(claim={"event_date": "2025-03-01", "notified_at": "2025-03-02"})["policy_active"].passed


def test_uncovered_risk_fails():
    assert not flags(claim={"damage_type": "storm"})["risk_covered"].passed


def test_notification_on_day_61_fails_and_day_60_passes():
    assert not flags(claim={"notified_at": "2024-11-14"})["notified_in_time"].passed
    assert flags(claim={"notified_at": "2024-11-13"})["notified_in_time"].passed


def test_different_address_fails():
    assert not flags(claim={"address": "Str. Alta 3, Galați"})["address_match"].passed


def test_missing_fields_fail_the_rule_instead_of_raising():
    f = flags(claim={"event_date": None, "notified_at": None}, policy={"covered_risks": None})
    assert len(f) == 6 and not f["policy_active"].passed and not f["risk_covered"].passed
    assert all(x.reason for x in f.values())


def test_context_term_is_zero_for_a_normal_claim_and_negative_for_odd_ones():
    assert context_term(CLAIM, POLICY) == 0
    late = context_term({**CLAIM, "notified_at": "2024-10-30"}, POLICY)
    assert -1 <= late < 0
    assert context_term({**CLAIM, "amount_claimed": 1e9}, {**POLICY, "sum_insured": 1}) == 0.0


def _rules(claim=None, policy=None, a=None, b=None):
    return {r.rule: r for r in check_policy({**CLAIM, **(claim or {})}, {**POLICY, **(policy or {})}, a, b)}


def test_rule_order():
    assert [r.rule for r in check_policy(CLAIM, POLICY)] == [
        "policy_active", "waiting_period", "risk_covered", "address_match", "notified_in_time",
        "amount_within_sum_insured"]


def test_amount_above_sum_insured_fails_the_new_rule():
    assert _rules(claim={"amount_claimed": 120000})["amount_within_sum_insured"].passed is False


def test_sum_insured_missing_fails_the_rule_when_an_amount_is_stated():
    assert _rules(policy={"sum_insured": None})["amount_within_sum_insured"].passed is False


def test_address_match_by_points_within_100_m():
    a, b = GeoHit(lat=45.6059, lon=27.78329, precision="house"), GeoHit(lat=45.6065, lon=27.78329, precision="house")
    assert _rules(policy={"address": "altă scriere"}, a=a, b=b)["address_match"].passed is True  # ~67 m


def test_address_match_by_points_far_apart_fails_even_with_equal_text():
    a, b = GeoHit(lat=45.6059, lon=27.78329, precision="house"), GeoHit(lat=45.62, lon=27.78329, precision="house")
    assert _rules(a=a, b=b)["address_match"].passed is False


def test_address_match_by_text_ignores_street_prefix_and_diacritics():
    r = _rules(claim={"address": "Strada Exemplu 12, Pechea"}, policy={"address": "Str. Exemplu 12, Pechea"})
    assert r["address_match"].passed
    r = _rules(claim={"address": "Str. Școlii nr. 4, jud. Galați"}, policy={"address": "strada Scolii 4, judetul Galati"})
    assert r["address_match"].passed


def test_context_term_no_longer_counts_the_amount():
    assert context_term({**CLAIM, "amount_claimed": 1e9}, {**POLICY, "sum_insured": 1}) == 0.0


def test_policy_flags_items_and_flags():
    res = policy_flags(check_policy({**CLAIM, "damage_type": "storm"}, POLICY))
    assert res.step == "policy" and len(res.items) == 6
    by = {i.id: i for i in res.items}
    assert by["risk_covered"].status == "fail" and by["policy_active"].status == "ok"
    assert [(f.code, f.severity, f.step, f.field) for f in res.flags] == [("risk_covered", "fail", "policy", None)]


def test_no_amount_on_the_claim_does_not_fail_the_amount_rule():
    r = _rules(claim={"amount_claimed": None})["amount_within_sum_insured"]
    assert r.passed is True and r.reason == "Cererea nu declară o sumă; regula nu se aplică"


def test_stated_amount_above_sum_insured_still_fails():
    assert _rules(claim={"amount_claimed": 100001})["amount_within_sum_insured"].passed is False
