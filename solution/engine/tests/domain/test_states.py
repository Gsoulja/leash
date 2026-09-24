import pytest

from leash.domain.states import IllegalTransition, mandate_transition, purchase_transition


def test_cannot_resolve_already_declined():
    with pytest.raises(IllegalTransition):
        purchase_transition("declined", "approved", by="customer")


def test_revoked_mandate_cannot_activate():
    with pytest.raises(IllegalTransition):
        mandate_transition("revoked", "active", by="customer")


@pytest.mark.parametrize("current,target,by", [
    (None, "received", "engine"),
    (None, "not_sent", "platform"),  # rejected by the platform before reaching the engine
    ("received", "approved", "engine"),
    ("received", "declined", "engine"),
    ("received", "waiting", "engine"),
    ("waiting", "approved", "customer"),
    ("waiting", "declined", "customer"),
    ("waiting", "timed_out", "platform"),
])
def test_allowed_purchase_transitions(current, target, by):
    assert purchase_transition(current, target, by=by) == target


@pytest.mark.parametrize("by", ["engine"])
@pytest.mark.parametrize("target", ["approved", "declined", "timed_out"])
def test_only_customer_or_platform_can_end_a_wait(target, by):
    with pytest.raises(IllegalTransition, match="waiting"):
        purchase_transition("waiting", target, by=by)


def test_customer_cannot_time_out_and_platform_cannot_answer():
    with pytest.raises(IllegalTransition):
        purchase_transition("waiting", "timed_out", by="customer")
    with pytest.raises(IllegalTransition):
        purchase_transition("waiting", "approved", by="platform")


@pytest.mark.parametrize("final", ["approved", "declined", "timed_out", "not_sent"])
@pytest.mark.parametrize("target", ["received", "approved", "declined", "waiting", "timed_out"])
def test_final_states_are_final(final, target):
    with pytest.raises(IllegalTransition):
        purchase_transition(final, target, by="platform")


def test_engine_cannot_skip_receiving():
    with pytest.raises(IllegalTransition):
        purchase_transition(None, "approved", by="engine")


@pytest.mark.parametrize("current,target,by", [
    (None, "draft", "customer"),
    ("draft", "active", "customer"),
    ("active", "revoked", "customer"),
    ("active", "expired", "platform"),
])
def test_allowed_mandate_transitions(current, target, by):
    assert mandate_transition(current, target, by=by) == target


@pytest.mark.parametrize("current,target,by", [
    ("draft", "active", "engine"),       # only the customer confirms
    ("active", "revoked", "engine"),     # only the customer revokes
    ("expired", "active", "customer"),
    ("draft", "revoked", "customer"),
    ("active", "draft", "customer"),
])
def test_illegal_mandate_transitions(current, target, by):
    with pytest.raises(IllegalTransition):
        mandate_transition(current, target, by=by)


def test_unknown_states_and_actors_are_rejected():
    with pytest.raises(IllegalTransition):
        purchase_transition("received", "maybe", by="engine")  # type: ignore[arg-type]
    with pytest.raises(IllegalTransition):
        purchase_transition("received", "approved", by="agent")  # type: ignore[arg-type]
