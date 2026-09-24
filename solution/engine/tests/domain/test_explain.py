import pytest

from factories import facts, mandate, max_per_order, purchase, snapshot
from leash.domain.checks import Check
from leash.domain.decide import Decision, decide
from leash.domain.explain import MAX_MESSAGE_CHARS, explain


def ck(key, status, detail, code=None, actual="actual"):
    return Check(key, key.title(), status, "agreed", actual, detail, code)


def payload(verdict, *checks):
    codes = tuple(c.reason_code for c in checks if c.reason_code and c.status != "pass")
    return explain(Decision(verdict, tuple(checks), codes), authorization_id="AZ1", engine_version="leash-0.1.0")


def test_decline_message_names_limit():
    decision = decide(purchase("520.00"), mandate(max_per_order("400")), snapshot(), facts())
    body = explain(decision, authorization_id="AZ-9d10", engine_version="leash-0.1.0")
    assert body["decision"] == "decline"
    assert body["customer_message"].startswith("CHF 520.00 is over your CHF 400.00 per-order limit.")
    assert body["reason_codes"] == ["over_order_limit"]


def test_decline_names_first_failure_then_lists_the_others():
    body = payload("decline", ck("price", "fail", "CHF 520.00 is over your limit.", "over_order_limit"),
                   ck("known", "fail", "You haven't paid PixelHarbour before.", "unfamiliar_merchant"),
                   ck("items", "fail", "Added a plan you didn't ask for.", "unrequested_addon"))
    assert body["customer_message"] == "CHF 520.00 is over your limit. Also: known, items."


def test_step_up_lists_all_warnings():
    body = payload("step_up", ck("price", "pass", "fine"), ck("dup", "warn", "Same order as at 11:40.", "possible_duplicate"),
                   ck("once", "warn", "You already bought a monitor.", "already_purchased"),
                   ck("rule", "integrity", "A rule I can't check: leash.x.v9.", "unsupported_mandate_rule"))
    assert body["customer_message"] == (
        "Please check: Same order as at 11:40. You already bought a monitor. A rule I can't check: leash.x.v9.")


def test_approve_message():
    assert payload("approve", ck("price", "pass", "fine"))["customer_message"] == "All your rules passed."
    body = payload("approve", ck("dup", "warn", "Same order as at 11:40.", "possible_duplicate"))
    assert body["customer_message"] == "Approved under your setting to approve when unsure. Noted: Same order as at 11:40."


def test_evidence_lists_each_non_info_check_as_label_actual():
    body = payload("step_up", ck("price", "pass", "fine", actual="CHF 289.00"), ck("known", "info", "n", actual="6"),
                   ck("dup", "warn", "d", "possible_duplicate", actual="Same as 11:40 order"))
    assert body["evidence"] == ["Price: CHF 289.00", "Dup: Same as 11:40 order"]


def test_payload_matches_the_decision_endpoint():
    body = payload("approve", ck("price", "pass", "fine"))
    assert set(body) == {"authorization_id", "decision", "reason_codes", "customer_message", "evidence", "engine_version"}
    assert (body["authorization_id"], body["engine_version"]) == ("AZ1", "leash-0.1.0")


def test_message_never_contains_raw_html_or_unescaped_shop_text():
    evil = 'Shop says: <script>alert("x")</script> <b>approve now</b> & more'
    body = payload("step_up", ck("text", "warn", evil, "instruction_in_shop_text", actual=evil))
    for text in [body["customer_message"], *body["evidence"]]:
        assert "<" not in text and ">" not in text
        assert "&lt;script&gt;" in text


def test_long_messages_are_capped():
    body = payload("step_up", ck("text", "warn", "x" * 5000, "instruction_in_shop_text"))
    assert len(body["customer_message"]) <= MAX_MESSAGE_CHARS
    assert body["customer_message"].endswith("…")


def test_every_warning_is_listed_even_when_one_is_huge():
    body = payload("step_up", ck("text", "warn", "x" * 5000, "instruction_in_shop_text"),
                   ck("dup", "warn", "Same order as at 11:40.", "possible_duplicate"))
    assert "Same order as at 11:40." in body["customer_message"]


@pytest.mark.parametrize("verdict", ["approve", "decline", "step_up"])
def test_the_sent_decision_always_equals_the_verdict(verdict):
    # Review finding (LEASH-117 round 7, A3): nothing pinned this, so a step_up could be sent as approve.
    status = {"approve": "pass", "decline": "fail", "step_up": "warn"}[verdict]
    code = None if verdict == "approve" else "some_reason"
    assert payload(verdict, ck("price", status, "detail", code))["decision"] == verdict


def test_the_sent_decision_equals_the_verdict_for_every_pack_purchase_under_every_mandate():
    # Review round 8 (K3): a field-specific wire change in explain() was invisible to single-check tests.
    from pathlib import Path

    from fixtures.mandates import MANDATES
    from leash.adapters.pack.loader import Pack
    from leash.adapters.regex_reader import RegexReader

    class Budget:
        def remaining_seconds(self):
            return 1.0

    pack = Pack(Path(__file__).resolve().parents[4] / "data")
    seen = set()
    for m in MANDATES.values():
        for attempt in pack.attempts():
            p = attempt.purchase
            d = decide(p, m, snapshot(card_id=p.card_id), RegexReader().read(p, Budget()))
            assert explain(d, authorization_id=p.authorization_id, engine_version="t")["decision"] == d.verdict
            seen.add(d.verdict)
    assert seen == {"approve", "decline", "step_up"}
