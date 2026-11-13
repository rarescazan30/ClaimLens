from engine.rules import check_policy, context_term

POLICY = {"id": "P", "address": "Str. Exemplu 12, Pechea", "valid_from": "2024-02-01", "valid_to": "2025-01-31",
          "waiting_days": 5, "covered_risks": ["flood"], "sum_insured": 100000}
CLAIM = {"id": "C", "damage_type": "flood", "event_date": "2024-09-14", "notified_at": "2024-09-19",
         "address": "str. exemplu 12,  Pechea", "amount_claimed": 40000}


def flags(claim=None, policy=None):
    return {f.rule: f for f in check_policy({**CLAIM, **(claim or {})}, {**POLICY, **(policy or {})})}


def test_all_five_rules_pass_for_a_clean_claim():
    f = flags()
    assert sorted(f) == ["address_match", "notified_in_time", "policy_active", "risk_covered", "waiting_period"]
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
    assert len(f) == 5 and not f["policy_active"].passed and not f["risk_covered"].passed
    assert all(x.reason for x in f.values())


def test_context_term_is_zero_for_a_normal_claim_and_negative_for_odd_ones():
    assert context_term(CLAIM, POLICY) == 0
    late = context_term({**CLAIM, "notified_at": "2024-10-30"}, POLICY)
    over = context_term({**CLAIM, "amount_claimed": 150000}, POLICY)
    assert -1 <= late < 0 and -1 <= over < 0
