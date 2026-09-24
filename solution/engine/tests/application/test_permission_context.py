"""LEASH-154: the context bundle a permission conversation may see.

Background suggests questions; it never becomes authority. Every entry names its scope and its
source row, history summaries stop at the evaluation cutoff, and the two datasets in data/ and
additional-data-history/ are separate customer populations that can never borrow each other's rows.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from leash.adapters.pack.loader import Pack
from leash.application.permission_context import (
    ConfirmedPermission,
    Scope,
    SourceRef,
    UnknownScope,
    build_context,
    resolve_scope,
)
from leash.domain.clock import SimTime

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
EXTRA = ROOT / "additional-data-history"

CUTOFF = SimTime.parse("2026-08-09T00:00:00Z")


@pytest.fixture(scope="module")
def pack() -> Pack:
    return Pack(DATA)


@pytest.fixture(scope="module")
def extra() -> Pack:
    return Pack(EXTRA)


def context(pack: Pack, card_id: str, instruction: str, cutoff: SimTime = CUTOFF, **kw):
    return build_context(pack, resolve_scope(pack, card_id), instruction, cutoff=cutoff, **kw)


# --- the jacket example from the ticket -------------------------------------------------------

def test_clothing_return_preference_asks_a_question_and_grants_nothing(pack):
    # CU0012 (card CA0024) records "Italian or Swiss fashion retailers with returns".
    bundle = context(pack, "CA0024", "Buy me a jacket for the autumn")
    prefs = [e for e in bundle.entries if e.kind == "preference"]
    assert prefs, "the recorded clothing preference is relevant to a jacket"
    assert any("return" in q.text.lower() for q in bundle.suggested_questions)
    assert bundle.hard_rules() == ()  # background never compiles to a rule
    assert all(not e.grants_authority for e in bundle.entries)


def test_explicit_intent_overrides_a_preference_and_marks_it_conflicting(pack):
    bundle = context(pack, "CA0024", "Buy me a jacket, returns do not matter this time")
    prefs = [e for e in bundle.entries if e.kind == "preference" and "return" in e.text.lower()]
    assert prefs and all(e.conflicting for e in prefs)
    assert not any("return" in q.text.lower() for q in bundle.suggested_questions)


def test_irrelevant_preferences_and_other_personas_are_not_exposed(pack):
    bundle = context(pack, "CA0024", "Buy me a jacket for the autumn")
    assert {e.scope.customer_id for e in bundle.entries} == {"CU0012"}
    assert not any("photograph" in e.text.lower() for e in bundle.entries)  # CU0015's hobby
    assert len(bundle.entries) <= bundle.MAX_ENTRIES


def test_absent_preference_yields_no_entry_rather_than_a_guess(pack):
    bundle = context(pack, "CA0024", "Buy me a litre of engine oil")
    assert not any(e.kind == "preference" and "return" in e.text.lower() for e in bundle.entries)


def test_profile_freshness_is_unknown_and_shown_as_such(pack):
    bundle = context(pack, "CA0024", "Buy me a jacket for the autumn")
    prefs = [e for e in bundle.entries if e.kind == "preference"]
    assert all(e.observed_at is None and e.freshness == "unknown" for e in prefs)


def test_history_older_than_the_staleness_horizon_is_labelled_stale(pack):
    late = SimTime.parse("2027-08-09T00:00:00Z")  # a year after the pack's last rows
    bundle = context(pack, "CA0024", "Buy me a jacket", cutoff=late)
    history = [e for e in bundle.entries if e.kind == "history"]
    assert history and all(e.stale for e in history)


# --- isolation --------------------------------------------------------------------------------

def test_unknown_card_raises_rather_than_inheriting_a_persona(pack):
    with pytest.raises(UnknownScope):
        resolve_scope(pack, "CA9999")


def test_scope_is_resolved_by_id_never_by_persona_name(pack):
    scope = resolve_scope(pack, "CA0024")
    assert (scope.customer_id, scope.account_id, scope.card_id) == ("CU0012", "AC0019", "CA0024")
    assert scope.dataset == "data"


def test_the_same_persona_name_is_two_unrelated_customers(pack, extra):
    """"Giulia Rossi" is CU0012 in data/ and CU1493 in additional-data-history/."""
    here = {c.customer_id for c in pack.customers().values() if c.persona_name == "Giulia Rossi"}
    there = {c.customer_id for c in extra.customers().values() if c.persona_name == "Giulia Rossi"}
    assert here == {"CU0012"} and there == {"CU1493"} and here != there
    bundle = context(pack, "CA0024", "Buy me a jacket for the autumn")
    assert {e.scope.customer_id for e in bundle.entries} == {"CU0012"}
    assert all(e.source.dataset == "data" for e in bundle.entries)


def test_the_two_datasets_are_separate_populations(pack, extra):
    assert set(pack.customers()) & set(extra.customers()) == set()
    scope = resolve_scope(extra, next(iter(extra.cards())))
    assert scope.dataset == "additional-data-history"
    with pytest.raises(UnknownScope):
        resolve_scope(extra, "CA0024")  # a data/ card is unknown in the other population
    with pytest.raises(UnknownScope):
        resolve_scope(pack, scope.card_id)


def test_entries_carry_their_source_record_for_evidence(pack):
    bundle = context(pack, "CA0024", "Buy me a jacket for the autumn")
    assert bundle.entries
    for e in bundle.entries:
        assert e.source.dataset == "data" and e.source.file and e.source.row_id
    assert bundle.as_evidence()["scope"]["card_id"] == "CA0024"


# --- history summaries ------------------------------------------------------------------------

def test_summary_uses_only_rows_at_or_before_the_cutoff(pack):
    early = context(pack, "CA0024", "Buy me a jacket", cutoff=SimTime.parse("2025-09-02T00:00:00Z"))
    late = context(pack, "CA0024", "Buy me a jacket", cutoff=SimTime.parse("2026-08-09T00:00:00Z"))
    assert early.summary.completed_purchases < late.summary.completed_purchases


def test_summary_counts_approved_purchases_only(pack):
    card = "CA0024"  # has refunds, declines and a cash withdrawal in the pack
    scope = resolve_scope(pack, card)
    rows = [r for r in pack.transactions(card) if r.sim_time <= CUTOFF]
    assert {r.transaction_type for r in rows} >= {"purchase", "refund", "cash_withdrawal"}
    assert "declined" in {r.status for r in rows}
    summary = build_context(pack, scope, "Buy me trail shoes", cutoff=CUTOFF).summary
    approved = [r for r in rows if r.transaction_type == "purchase" and r.status == "approved"]
    assert summary.completed_purchases == len(approved)
    assert summary.spend_chf == sum((r.billing_amount_chf for r in approved), Decimal("0.00"))


def test_refunds_are_accounted_separately_and_never_net_off_the_spend(pack):
    summary = context(pack, "CA0024", "Buy me trail shoes").summary
    assert summary.refunds_chf > Decimal("0.00")
    assert summary.spend_chf != summary.net_of_refunds_chf
    assert summary.net_of_refunds_chf == summary.spend_chf - summary.refunds_chf


def test_summary_is_scoped_to_the_card_not_the_whole_customer(pack):
    scope = resolve_scope(pack, "CA0024")
    card = build_context(pack, scope, "Buy me trail shoes", cutoff=CUTOFF).summary
    whole = build_context(pack, scope.for_account(), "Buy me trail shoes", cutoff=CUTOFF).summary
    assert card.card_id == "CA0024" and whole.card_id is None
    assert whole.completed_purchases >= card.completed_purchases


def test_spend_uses_each_row_own_chf_amount_never_the_raw_amount(pack):
    scope = resolve_scope(pack, "CA0024")
    rows = [r for r in pack.transactions("CA0024") if r.sim_time <= CUTOFF]
    approved = [r for r in rows if r.transaction_type == "purchase" and r.status == "approved"]
    assert {r.currency for r in approved} > {"CHF"}, "CA0024 has foreign-currency purchases"
    summary = build_context(pack, scope, "Buy me trail shoes", cutoff=CUTOFF).summary
    assert summary.spend_chf == sum((r.billing_amount_chf for r in approved), Decimal("0.00"))
    # summing the rows' own amounts instead would give a different total, so this pins the conversion
    assert sum((r.amount for r in approved), Decimal("0.00")) != summary.spend_chf


def test_the_merchant_histogram_is_capped_so_a_summary_is_never_a_history(pack):
    summary = context(pack, "CA0024", "Buy me trail shoes").summary
    scope = resolve_scope(pack, "CA0024")
    used = {r.merchant_id for r in pack.transactions("CA0024")
            if r.sim_time <= CUTOFF and r.transaction_type == "purchase" and r.status == "approved"}
    assert len(used) > summary.MAX_MERCHANTS, "CA0024 uses more shops than the cap"
    assert len(summary.merchants) == summary.MAX_MERCHANTS
    assert summary.completed_purchases > sum(summary.merchants.values())  # the count is not truncated


# --- previously confirmed permissions ----------------------------------------------------------

def _permission(text: str, scope: Scope) -> ConfirmedPermission:
    return ConfirmedPermission(text, scope, SourceRef(scope.dataset, "policy_drafts", "LD-1", "confirmed"))


def test_a_confirmed_permission_is_shown_inside_its_recorded_scope(pack):
    scope = resolve_scope(pack, "CA0024")
    bundle = build_context(pack, scope, "Buy me a jacket", cutoff=CUTOFF,
                           confirmed=[_permission("Groceries up to CHF 50", scope)])
    settled = [e for e in bundle.entries if e.kind == "confirmed"]
    assert [e.text for e in settled] == ["Groceries up to CHF 50"]
    assert all(not e.grants_authority for e in settled)  # still background, not a grant
    assert bundle.hard_rules() == () and bundle.confirmed_rules() == ()


def test_a_permission_recorded_for_another_card_never_applies_here(pack):
    here, other = resolve_scope(pack, "CA0024"), resolve_scope(pack, "CA0023")
    assert here.customer_id == other.customer_id, "same customer, different cards"
    bundle = build_context(pack, here, "Buy me a jacket", cutoff=CUTOFF,
                           confirmed=[_permission("Groceries up to CHF 50", other)])
    assert not [e for e in bundle.entries if e.kind == "confirmed"]


def test_a_permission_recorded_for_the_customer_covers_their_cards(pack):
    scope = resolve_scope(pack, "CA0024")
    bundle = build_context(pack, scope, "Buy me a jacket", cutoff=CUTOFF,
                           confirmed=[_permission("Groceries up to CHF 50", scope.for_customer())])
    assert [e.kind for e in bundle.entries if e.kind == "confirmed"] == ["confirmed"]


def test_a_permission_from_the_other_population_never_applies(pack, extra):
    scope = resolve_scope(pack, "CA0024")
    foreign = Scope("additional-data-history", "CU1493", None, None)  # the other "Giulia Rossi"
    bundle = build_context(pack, scope, "Buy me a jacket", cutoff=CUTOFF,
                           confirmed=[_permission("Anything up to CHF 900", foreign)])
    assert not [e for e in bundle.entries if e.kind == "confirmed"]


def test_many_confirmations_squeeze_history_out_rather_than_growing_the_bundle(pack):
    scope = resolve_scope(pack, "CA0024")
    many = [_permission(f"Settled rule {n}", scope) for n in range(20)]
    bundle = build_context(pack, scope, "Buy me a jacket", cutoff=CUTOFF, confirmed=many)
    assert len(bundle.entries) == bundle.MAX_ENTRIES
    assert not [e for e in bundle.entries if e.kind == "history"]


def test_a_bundle_says_when_the_cap_dropped_entries(pack):
    """A reader that cannot see everything is told, rather than taking a partial view for the whole."""
    scope = resolve_scope(pack, "CA0024")
    plenty = [_permission(f"Settled rule {n}", scope) for n in range(20)]
    assert build_context(pack, scope, "Buy me a jacket", cutoff=CUTOFF, confirmed=plenty).truncated
    assert not build_context(pack, scope, "Buy me a jacket", cutoff=CUTOFF).truncated
    assert build_context(pack, scope, "Buy me a jacket", cutoff=CUTOFF).as_evidence()["truncated"] is False


def test_budget_style_is_shown_only_when_the_customer_raises_a_budget(pack):
    plain = context(pack, "CA0024", "Buy me a jacket for the autumn")
    asked = context(pack, "CA0024", "Buy me a jacket, stay in my usual budget")
    assert not [e for e in plain.entries if e.source.field == "budget_style"]
    assert [e for e in asked.entries if e.source.field == "budget_style"]


# --- what background may and may not claim -----------------------------------------------------

def test_usual_budget_is_offered_as_a_question_never_as_an_amount(pack):
    bundle = context(pack, "CA0024", "Buy me trail shoes, stay in my usual budget")
    budget = [q for q in bundle.suggested_questions if "budget" in q.text.lower()]
    assert budget and all(q.needs_confirmation for q in budget)
    assert bundle.hard_rules() == ()


def test_shops_i_use_is_answered_from_id_based_history(pack):
    bundle = context(pack, "CA0024", "Only shops I use", cutoff=CUTOFF)
    shops = [e for e in bundle.entries if e.kind == "history" and e.merchant_id]
    assert shops and all(e.source.file == "authorization_history.csv" for e in shops)
    assert all(e.merchant_id.startswith("ME") for e in shops)


def test_history_without_baskets_cannot_confirm_an_exact_item(pack):
    bundle = context(pack, "CA0024", "Buy the same trail shoes I bought before")
    assert bundle.item_history == "unavailable"
    assert any("which" in q.text.lower() or "confirm" in q.text.lower() for q in bundle.suggested_questions)


def test_a_suggested_question_is_not_an_answer(pack):
    bundle = context(pack, "CA0024", "Buy me a jacket for the autumn")
    assert all(not q.answered for q in bundle.suggested_questions)
    assert bundle.confirmed_rules() == ()


def test_profile_text_is_data_and_never_reaches_the_assistant_as_instructions(pack):
    bundle = context(pack, "CA0024", "Buy me a jacket for the autumn")
    for e in bundle.entries:
        assert e.role == "data"


def test_bundle_excludes_sensitive_identifiers_from_ordinary_logs(pack):
    bundle = context(pack, "CA0024", "Buy me a jacket for the autumn")
    assert "Giulia" not in bundle.log_line()
    assert "CA0024" in bundle.log_line()
