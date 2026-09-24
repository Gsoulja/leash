"""Canonical registry of the hard_rule fields the engine understands (DEC-004).

Every confirmed restriction travels to the engine as a `hard_rule` inside the live event, so both
sides must read each field the same way every time. Viseca's own paths keep their names; our fields
carry a `leash.` prefix and a version suffix. A field's meaning never changes: a new meaning is a new
versioned name (tests pin a fingerprint of each entry).

The operators and value kinds come from the engine's FIELD_SPEC, so the registry and the engine
cannot drift apart.
"""

import ast
import hashlib
import importlib
import inspect
import re
from decimal import Decimal
from pathlib import Path
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from leash.domain import mandate as m
from leash.domain.mandate import CompiledMandate, Rule

_MEANINGS: dict[str, str] = {
    m.F_BILLING_CHF: "Purchase total in CHF, delivery included (the event's billing_amount_chf). "
                     "scope=purchase limits one order; scope=period with period_days limits the sum of final "
                     "approvals in this run over the trailing window of simulated time.",
    m.F_FULFILLMENT: "How the order is fulfilled (the event's fulfillment_method, e.g. delivery, pickup, digital).",
    m.F_MERCHANT_CATEGORY: "The merchant's category (e.g. sporting_goods). Describes the shop, not the basket.",
    m.F_ITEM_CATEGORY: "Every basket line's item_category must satisfy the rule.",
    m.F_ITEM_ID: "Every basket line's catalogue item_id must satisfy the rule.",
    m.F_PRIOR_PURCHASES: "Approved purchases at this merchant_id on this card before this one: history (purchases "
                         "only, never refunds, withdrawals or declines) plus final approvals earlier in this run.",
    m.F_SIZE: "The size stated for the requested item in the merchant's product text; not stated means missing.",
    m.F_RETURN_DAYS: "The return window in days stated by the merchant; final sale counts as 0; not stated means missing.",
    m.F_UNREQUESTED_ITEMS: "Basket lines that are not a requested item (add-ons, plans, vouchers). Only 0 is enforced.",
    m.F_MAX_PURCHASES: "Approved purchases allowed in total in this run, whatever the item (1 = buy it once).",
    m.F_MAX_QUANTITY: "Total quantity of requested items in one order.",
    m.F_SESSION_RISK: "Session risk points: new device 2, 2+ attempts in 10 min 2 (1 attempt 1), "
                      "night-time in Zurich 1, first-time country 2 (DEC-024).",
    m.F_SPLIT_CHECK: "'on': a second order at the same merchant within an hour that together exceeds the "
                     "per-order limit is treated as possibly split.",
}


def describe_field(field_name: str) -> str:
    """The field's meaning in words, for showing a rule to the customer (its first sentence)."""
    meaning = _MEANINGS.get(field_name)
    return meaning.split(". ")[0].rstrip(".") if meaning else field_name


class RegistryError(ValueError):
    """A rule uses a field, operator or value the engine does not understand."""


@dataclass(frozen=True)
class FieldSpec:
    name: str
    version: int
    operators: frozenset[str]
    value_kind: Literal["number", "text"]
    meaning: str
    source: Literal["viseca", "leash"]


# Viseca's own paths keep their names, so our interpretation of them is versioned here instead.
# Bump a number (and add a new lock entry) when the engine's reading of that path changes.
_VISECA_INTERPRETATION_VERSION: dict[str, int] = {
    m.F_BILLING_CHF: 1, m.F_FULFILLMENT: 1, m.F_MERCHANT_CATEGORY: 1, m.F_ITEM_CATEGORY: 1, m.F_ITEM_ID: 1,
}


def _spec(name: str) -> FieldSpec:
    ops, kind = m.FIELD_SPEC[name]
    suffix = re.search(r"\.v(\d+)$", name)
    version = int(suffix.group(1)) if suffix else _VISECA_INTERPRETATION_VERSION[name]
    return FieldSpec(name=name, version=version, operators=frozenset(ops),
                     value_kind="number" if kind == "number" else "text", meaning=_MEANINGS[name],
                     source="leash" if name.startswith("leash.") else "viseca")


REGISTRY: Mapping[str, FieldSpec] = MappingProxyType({name: _spec(name) for name in m.FIELD_SPEC})


_PROBE_OPERATORS = ("<", "<=", "=", "!=", ">", ">=", "in", "not_in")
_PROBE_NUMBERS = tuple(Decimal(v) for v in (
    "-10000000000", "-1", "0", "0.5", "1", "2", "2.7", "5", "14", "300", "9999", "10000", "1000000", "100000000", "1000000000",
    "1000000001", "NaN", "Infinity"))
_PROBE_TEXTS: tuple[str | tuple[str, ...], ...] = (
    "on", " on", "on ", "off", "ON", "yes", "true", "enabled", "", "43", "x", " x", "chf", (), ("on",), ("a",), ("a", "b"),
    ("b", "c"), ("a", "b", "c"), ("a", "b", "c", "d"))
_PROBE_CURRENCIES = (None, "CHF", "chf", "EUR", "USD", "GBP")
_PROBE_PERIODS: tuple[tuple[str | None, int | None], ...] = (
    (None, None), ("purchase", None), ("purchase", 7), (None, 7), ("period", 1), ("period", 7), ("period", 14),
    ("period", 30), ("period", 365), ("period", 366), ("period", 400), ("period", 401), ("period", 100000))


def _probe_rules(name: str) -> list[Rule]:
    out = []
    shapes = [(c, s, d) for c in _PROBE_CURRENCIES for s, d in _PROBE_PERIODS] if name == m.F_BILLING_CHF else \
        [(None, None, None), ("CHF", None, None), (None, "purchase", None), (None, "period", 7)]
    for op in _PROBE_OPERATORS:
        for value in (*_PROBE_NUMBERS, *_PROBE_TEXTS):
            for currency, scope, days in shapes:
                try:
                    out.append(Rule(name, op, value, currency=currency, scope=scope, period_days=days))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
    return out


def _canonical(value: object) -> str:
    """Order-independent text form (sets are sorted), so the hash is the same on every run."""
    if isinstance(value, (frozenset, set)):
        return "{" + ",".join(sorted(_canonical(v) for v in value)) + "}"
    if isinstance(value, (tuple, list)):
        return "(" + ",".join(_canonical(v) for v in value) + ")"
    return repr(value)


def _effect(*rules: Rule) -> str:
    return _canonical(CompiledMandate(instruction="probe", rules=rules, uncertainty="ask")._snapshot())


def behaviour(name: str) -> str:
    """What the engine actually does with this field, as a hash.

    Probes every operator × a fixed set of numbers, texts, currencies and period shapes: for each single
    rule whether it is supported and the effective constraints it produces (unsupported rules too, so a
    rule the engine can't enforce is pinned as having no effect), for pairs of supported rules how they
    combine (strictest wins), and for triples how three or more rules fold together. Part of the
    fingerprint, so changing enforcement, not just the description, is caught.
    """
    lines = []
    supported_rules = []
    for rule in _probe_rules(name):
        ok = m.supported(rule)
        if ok:
            supported_rules.append(rule)
        lines.append(f"1|{rule!r}|{'+' if ok else '-'}|{_effect(rule)}")
    sample = supported_rules[:: max(1, len(supported_rules) // 24)][:24]
    for a in sample:
        for b in sample:
            lines.append(f"2|{a!r}|{b!r}|{_effect(a, b)}")
    trio = supported_rules[:: max(1, len(supported_rules) // 8)][:8]
    for a in trio:
        for b in trio:
            for c in trio:
                lines.append(f"3|{a!r}|{b!r}|{c!r}|{_effect(a, b, c)}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def fingerprint(spec: FieldSpec) -> str:
    """Short hash of what a field means and how it is enforced (compiled and evaluated); pinned by the tests."""
    text = "|".join([spec.name, str(spec.version), ",".join(sorted(spec.operators)), spec.value_kind, spec.meaning,
                     behaviour(spec.name), enforcement_code_hash(spec.name)])
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def code_hash(source: str) -> str:
    """Hash of Python code's structure: comments, docstrings and formatting don't change it."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and \
                isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]  # type: ignore[attr-defined]
    return hashlib.sha256(ast.dump(tree, annotate_fields=False).encode()).hexdigest()[:12]


# Core code that shapes every field's meaning: rule compilation, what text is read at all, time windows,
# purchase identity, how checks combine into a verdict, and how model facts merge with deterministic ones.
SHARED_ENFORCEMENT: tuple[str, ...] = (
    "leash.domain.mandate", "leash.domain.facts", "leash.domain.clock", "leash.domain.purchase",
    "leash.domain.checks", "leash.domain.decide", "leash.adapters.fallback_reader",
    "leash.domain.money", "leash.domain.snapshot",  # used by several rules: shared, so no field can miss them
    "leash.domain.rules.shop_text",  # a safeguard on every purchase; decide() runs it for every verdict
    "leash.domain.rules.unsupported",  # an unenforceable rule never approves (DEC-005)
    "leash.domain.states", "leash.ports.repository",  # which transitions count (e.g. what becomes spend)
    "leash.domain.explain",  # the body actually sent: its decision must stay the verdict
    "leash.policy.hard_rules",  # how API rules are read into Rule objects (value types, unknown fields)
    "leash.adapters.viseca_api.translate",  # what every live event field means to the engine
    "leash.adapters.pack.loader",  # the seed reads the pack through it (merchants, history)
    "leash.adapters.postgres.repository",  # builds the live snapshot: which history and run rows count
    "leash.adapters.postgres.mandates",  # which compiled mandate a customer approval is re-checked against
    "leash.adapters.postgres.unit_of_work",  # which run's rows a decision and a customer answer see
    "leash.adapters.pack.seed",  # writes the live history that familiarity, devices and countries come from
    "leash.application.decide_purchase",  # which mandate and facts a live decision uses; the safe fallback
    "leash.application.resolve",  # which rules can block a customer's approval (DEC-012)
)
# Schema files are part of the live meaning too (e.g. the familiarity view defines "prior purchase").
SHARED_FILES: tuple[str, ...] = ("migrations/versions/*",)  # every file, not only Python (e.g. a .sql input)

# Every other module, with the reason it can't change a field's meaning. A new module must be classified
# here or above before the tests pass, so nothing on the live path is added silently.
NOT_A_FIELD_MEANING: Mapping[str, str] = MappingProxyType({
    **{pkg: "package marker" for pkg in (
        "leash", "leash.adapters", "leash.adapters.http", "leash.adapters.pack", "leash.adapters.postgres",
        "leash.adapters.viseca_api",
        "leash.application", "leash.domain", "leash.domain.rules", "leash.policy", "leash.ports", "leash.reading")},
    "leash.adapters.http.events": "change notifications for the app, derived from decision_events",
    "leash.adapters.http.query_api": "read-only views for the app; its can_approve re-check mirrors application.resolve",
    "leash.application.clarify": "turns the customer's answers into a recompiled draft; readings come from the compiler",
    "leash.service": "process wiring: routers, background loops, health and readiness",
    "leash.adapters.postgres.migrate": "runs the migrations and the pack seed; the seed itself is hashed",
    "leash.adapters.http.policy_api": "draft, submit and confirm endpoints; rules pass through hard_rules and the compiler, "
                                      "never evaluated here",
    "leash.adapters.viseca_api.client": "HTTP transport",
    "leash.adapters.viseca_api.worker": "polling loop and process wiring; every verdict comes from DecidePurchase",
    "leash.adapters.viseca_api.event_schema": "structural validation only: rejects, never changes a value",
    "leash.adapters.viseca_api.outbox_sender": "resends stored bodies unchanged",
    "leash.application.replay": "offline replay only",
    "leash.application.permission_context": "background for the permission conversation: bounded profile and "
                                            "history context that suggests questions, never rules; not read at "
                                            "decision time",
    "leash.adapters.pack.catalogue": "reference lookup for the permission conversation: names candidate items "
                                     "and their price context, never read at decision time",
    "leash.policy.compiler": "drafts rules for the customer to confirm; only confirmed hard_rules are enforced",
    "leash.config": "runtime settings and timeouts, no rule semantics",
    "leash.policy.registry": "the registry itself; meanings and versions are in each fingerprint",
    "leash.ports.fact_reader": "interface only",
    "leash.reading.question_bank": "the model's questions, pinned by bank_hash; a model can only tighten (DEC-009)",
})

# The code that gives each field its own meaning at decision time: rule evaluators and the fact sources they
# read. With SHARED_ENFORCEMENT, part of the field's fingerprint, so changing how a rule is evaluated is a
# versioned decision too.
EVALUATORS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    m.F_BILLING_CHF: ("leash.domain.rules.price", "leash.domain.rules.period"),
    m.F_FULFILLMENT: ("leash.domain.rules.fulfilment",),
    m.F_MERCHANT_CATEGORY: ("leash.domain.rules.shop_type",),
    m.F_ITEM_CATEGORY: ("leash.domain.rules.basket",),
    m.F_ITEM_ID: ("leash.domain.rules.basket",),
    m.F_PRIOR_PURCHASES: ("leash.domain.rules.familiar",),
    m.F_SIZE: ("leash.domain.rules.size", "leash.adapters.regex_reader"),
    m.F_RETURN_DAYS: ("leash.domain.rules.returns", "leash.adapters.regex_reader"),
    m.F_UNREQUESTED_ITEMS: ("leash.domain.rules.basket", "leash.adapters.regex_reader"),
    m.F_MAX_PURCHASES: ("leash.domain.rules.single",),
    m.F_MAX_QUANTITY: ("leash.domain.rules.basket",),
    m.F_SESSION_RISK: ("leash.domain.rules.session",),
    m.F_SPLIT_CHECK: ("leash.domain.rules.duplicates",),
})
# Fields the engine accepts but no evaluator enforces yet, with the ticket that adds one.
PENDING_EVALUATOR: Mapping[str, str] = MappingProxyType({})


def _source(module: str) -> str:
    return inspect.getsource(importlib.import_module(module))


_ENGINE_ROOT = Path(__file__).resolve().parents[3]


def _shared_files() -> list[Path]:
    return sorted(p for pattern in SHARED_FILES for p in _ENGINE_ROOT.glob(pattern) if p.is_file())


def _file_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return code_hash(text)  # structure only: comments and formatting don't count
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def enforcement_code_hash(name: str) -> str:
    """Structure of the shared core plus the field's evaluators: catches changes the behaviour probes can't sample."""
    modules = (*SHARED_ENFORCEMENT, *EVALUATORS.get(name, ()))
    parts = [f"{mod}:{code_hash(_source(mod))}" for mod in modules]
    parts += [f"{p.relative_to(_ENGINE_ROOT)}:{_file_hash(p)}" for p in _shared_files()]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def unknown_fields(rules: Iterable[Rule]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(r.field for r in rules if r.field not in REGISTRY))


def problems(rules: Iterable[Rule]) -> list[str]:
    """Why each rule can't be enforced exactly as written (empty when all are fine)."""
    out = []
    for r in rules:
        spec = REGISTRY.get(r.field)
        if spec is None:
            out.append(f"unknown field {r.field!r}")
        elif r.operator not in spec.operators:
            out.append(f"{r.field}: operator {r.operator!r} not supported (allowed: {', '.join(sorted(spec.operators))})")
        elif not m.supported(r):
            out.append(f"{r.field}: value {r.value!r} (currency={r.currency}, scope={r.scope}, "
                       f"period_days={r.period_days}) can't be enforced as written")
    return out


def check_rules(rules: Iterable[Rule]) -> None:
    """Compile-time check: raise if any rule can't be enforced exactly as written."""
    found = problems(rules)
    if found:
        raise RegistryError("; ".join(found))
