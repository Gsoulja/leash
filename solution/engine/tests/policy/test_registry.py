from decimal import Decimal

import pytest

from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.policy import registry
from leash.policy.registry import (EVALUATORS, NOT_A_FIELD_MEANING, PENDING_EVALUATOR, REGISTRY, SHARED_ENFORCEMENT,
                                   RegistryError, check_rules, code_hash, fingerprint, unknown_fields)

# Pinned meaning of every field. If a test here fails because a fingerprint changed, do NOT edit the
# entry: a changed meaning needs a new field name/version (e.g. leash.items.size.v2) and a new entry.
# Re-pinned 2026-09-24: max_count.v1 retired for v2 (DEC-032); the other fields moved only because the
# shared domain/mandate.py changed (the field constant), not their meaning.
# Re-pinned again 2026-09-24, both changes only tighten: the platform spend counter now applies to every
# period rule (LEASH-034 round 4, billing_amount_chf); decide.combine() never approves an injection and always
# asks on repeat/split/off-purpose/already-bought orders (DEC-029, DEC-030; shared, so every field moved).
# Re-pinned again 2026-09-24: DEC-030 option A, those orders are never approved automatically and a decline
# policy still declines them (only tightens compared with the previous pin).
# Re-pinned again 2026-09-24 (LEASH-131): durable claims touch shared code (migration 0006, the repository's
# receive, the unit of work, decide_purchase); no field's meaning changed.
# Re-pinned again 2026-09-24 (LEASH-154): adapters.pack.loader gained customer, account, card and
# transaction readers for the permission conversation's context bundle. The diff is additive only
# (120 insertions, 0 deletions): no existing read path, seed row or decision input changed, so every
# field moved for the same reason and no field's meaning did.
# Re-pinned again 2026-09-24 (LEASH-101, after review): migration 0007 adds draft_revisions and
# policy_drafts.revision, and stamps existing drafts as revision 1 so a stored view still matches its
# own schema. migrations/versions/* is in SHARED_FILES and is hashed as a whole file, so any edit to
# it moves every field. It adds only local draft bookkeeping (revisions, transcript, retained
# context); it touches no table the decision path reads and changes no field's meaning.
# Re-pinned again 2026-09-24 (LEASH-136): `application/decide_purchase.py` is in SHARED_ENFORCEMENT, and
# its decision-send timeout changed from `max(send_seconds, left)` to `max(0.0, min(send_seconds, left))`
# so a POST can no longer be held past `deadline_at`. That only shortens how long the engine waits to
# hand over an already-decided answer; it reads no rule, no fact and no amount, so every field moved for
# the same reason and no field's meaning did.
# Re-pinned again 2026-09-24 (LEASH-135): `0002` now adds `purchase` nullable and the new `0008` backfills,
# validates and requires it, `migrations/env.py` bounds every migration's lock and statement timeouts, and
# `env.py` was added to SHARED_FILES so that file is hashed too. Those files are hashed with `code_hash`
# (an AST dump, docstrings stripped), so a behaviour change there moves every field while a comment-only
# edit deliberately does not. The stored shape is unchanged — `0008` writes exactly what
# `purchase_to_json(translate(event).purchase)` produces, which is what the engine already wrote for every
# row created after `0002` — so no field's meaning changed; what changed is that a populated database can
# now reach head at all.
# Re-pinned again 2026-09-24 (LEASH-135, after review): `env.py` now refuses a zero timeout (Postgres reads
# `0` as *no* timeout, which would have silently removed the bound the file exists to guarantee), and `0008`
# gained a `remaining_without_purchase` helper so its validation step can be tested directly. Docstring-only
# edits to 0001 and 0004-0007 move nothing (code_hash strips docstrings). Neither change reads a rule, a fact
# or an amount, and the stored `purchase` shape is untouched: no field's meaning changed.
# Re-pinned again 2026-09-24 (LEASH-130): the engine's verdict and the platform's acceptance are now separate
# facts. Migration 0009 adds authorizations.delivery / platform_outcome / delivered_at and the `delivered`
# event kind; `domain/states.py` gains the delivery machine and the `→ not_sent` transitions a terminal refusal
# implies; `repository.py` gains `record_delivery`; `unit_of_work.mark_sent` records acceptance in the same
# transaction as closing the outbox row. Every field moved because all of these are shared code.
#
# This change is strictly *tightening*: a decision the platform refused now leaves `approved` for `not_sent`,
# so it stops counting toward spend, familiarity, duplicates and the purchase count — it used to count. No rule
# reads the new columns, no verdict depends on them, and nothing that counted before counts less safely now.
# Re-pinned again 2026-09-24 (LEASH-130, after review): migration 0009's backfill now also releases the
# spend a refused delivery was holding (it recorded the refusal but left `state = 'approved'`, which was the
# very bug the revision exists to fix, reintroduced for every pre-0009 row), and `unit_of_work.mark_sent`
# clears a stale `last_error` so an accepted decision reads as sent. Both are in shared code, so every field
# moved.
#
# Correcting the previous note, which claimed this work "only ever tightens": that is true of **spend**, and
# false of **verdicts**. Dropping a refused purchase from `snapshot.prior` also removes it as a *prior* for
# the next purchase, so a duplicate, split or count check it used to trigger no longer fires — reproduced by
# the reviewer: an identical second order went from `possible_duplicate` (step_up under DEC-029/030) to no
# check at all. That is what AC4 asks for — a decision the platform never accepted is not a purchase that
# happened — but it is a loosening for later purchases and must not be recorded as anything else.
# Re-pinned again 2026-09-24 (LEASH-136, reconciled with feature/LEASH-136). `application/decide_purchase.py`
# is in SHARED_ENFORCEMENT and its send path changed in four ways: it refuses to start once nothing remains
# before `deadline_at`; it is bounded by `min(plan.send_seconds, left)` rather than the old
# `max(send_seconds, left)`; it hands that same number to the sender, so connect, read, write and the pool
# wait are bounded inside httpx too; and the `Sender` port gained an optional `budget_seconds`, which is a
# signature change in a hashed module and so moves every fingerprint on its own.
#
# None of these reads a rule, a compiled mandate, a fact, a check or an amount. Each only shortens how long
# the engine waits to hand over an answer it has already decided, so every field moved for one reason and no
# field's meaning changed. `leash.config`, `leash.service` and the viseca_api adapter are all in
# NOT_A_FIELD_MEANING, so moving the pool settings into Settings contributes nothing to these hashes.
#
# Re-pinned 2026-09-25 (DEC-046 and the live 422). Three hashed modules changed:
#   * `domain/snapshot.py` gained `has_purchase_history()` — a new accessor; nothing existing behaves
#     differently, so every field moved on a signature change alone.
#   * `domain/explain.py` now sends `evidence` as one object per check instead of one string. The hosted
#     platform validates that field as a list of objects and refused **every** decision we sent with 422
#     (measured 2026-09-25, 285 refusals in one run); `decision`, `reason_codes` and `customer_message` are
#     untouched, so what the verdict says is unchanged — only how the supporting facts are encoded.
#   * `domain/rules/familiar.py` — this one **is** a behaviour change, and deliberately so:
#     `leash.merchant.prior_purchases.v1` still means "approved purchases at this merchant on this card",
#     and a card with history that has never used this shop still fails. What changed is the missing-fact
#     case: a card with no approved purchase anywhere now warns (uncertainty policy) instead of failing
#     (decline). It is recorded as a re-pin of v1 rather than a new `.v2` on purpose — a `.v2` would make
#     the `.v1` rules inside mandates already submitted to the platform *unsupported*, which never
#     approves, so introducing it would decline more, not less. Deliberate, and the loosening is bounded
#     to "we know nothing at all about this card": it can still never approve on its own.
#
# Re-pinned 2026-09-25 (LEASH-102, the changed-cart criterion). Two hashed modules changed, and no field's
# meaning did:
#   * `domain/purchase.py` gained the `Terms` value object (shop, billing amount, item fingerprint) with
#     `Terms.of` and `changed_from`. It is derived from `item_fingerprint`, which is why it lives here, and
#     nothing inside `decide()` reads it: it is used by the stores to tell a retried delivery from a
#     different attempt. A new class in a hashed module moves every fingerprint on its own.
#   * `application/decide_purchase.py` (SHARED_ENFORCEMENT) gained one branch on the **repeat** path, which
#     never calls `decide()`: a redelivery whose shop, amount or basket differs from the terms the stored
#     verdict was given on is answered with a `step_up` naming the mismatch instead of the saved verdict,
#     and an `integrity_alert` is written. The stored decision is not rewritten (DEC-003).
#
# This does change what is *sent* for such a redelivery — a saved `approve` is no longer posted for terms it
# was never checked against — and that is the point of the criterion. It only ever moves a verdict towards
# caution (approve → step_up), reads no rule, fact, check or amount, and cannot affect a first delivery.
LOCK = {
    "authorization.billing_amount_chf@v1": "93437733ba9e",
    "authorization.fulfillment_method@v1": "3eaaa5f96d74",
    "merchant.merchant_category@v1": "7d9694745f6f",
    "items.item_category@v1": "3f0599f57585",
    "items.item_id@v1": "a9ee61cb31ef",
    "leash.items.size.v1@v1": "2312127c48bb",
    "leash.merchant.prior_purchases.v1@v1": "a4f0f111c147",
    "leash.order.return_days.v1@v1": "6538d40e3894",
    "leash.items.unrequested_count.v1@v1": "1a917ef30abe",
    "leash.purchase.max_count.v2@v2": "b891e23cd5d8",
    "leash.items.max_quantity.v1@v1": "3cd7d78d798c",
    "leash.session.risk_score.v1@v1": "52061d132442",
    "leash.orders.split_check.v1@v1": "8403b04f8e77",
}


def test_unknown_field_is_reported():
    rules = (Rule(m.F_BILLING_CHF, "<=", Decimal("400")), Rule("leash.merchant.vibes.v1", "=", "good"))
    assert unknown_fields(rules) == ("leash.merchant.vibes.v1",)
    with pytest.raises(RegistryError, match="vibes"):
        check_rules(rules)


def test_every_registered_field_has_operators():
    for name, spec in REGISTRY.items():
        assert spec.name == name
        assert spec.operators, name
        assert spec.operators <= {"<", "<=", "=", "!=", ">", ">=", "in", "not_in"}
        assert spec.value_kind in ("number", "text")
        assert spec.meaning and spec.version >= 1
        assert spec.source in ("viseca", "leash")


def test_registry_and_engine_agree_on_every_field():
    assert set(REGISTRY) == set(m.FIELD_SPEC)
    for name, (ops, kind) in m.FIELD_SPEC.items():
        assert (REGISTRY[name].operators, REGISTRY[name].value_kind) == (ops, kind)


def test_our_fields_are_prefixed_and_versioned():
    for name, spec in REGISTRY.items():
        if spec.source == "leash":
            assert name.startswith("leash.") and name.endswith(f".v{spec.version}")
        else:
            assert not name.startswith("leash.")


def test_operators_a_field_does_not_support_are_rejected_at_compile_time():
    with pytest.raises(RegistryError, match="operator"):
        check_rules([Rule(m.F_PRIOR_PURCHASES, "=", Decimal("1"))])
    with pytest.raises(RegistryError, match="value"):
        check_rules([Rule(m.F_SIZE, "=", Decimal("43"))])
    check_rules([Rule(m.F_SIZE, "=", "43"), Rule(m.F_ITEM_ID, "in", ("IT0017",))])  # fine


def test_changing_a_meaning_requires_a_new_version():
    keys = {f"{name}@v{spec.version}" for name, spec in REGISTRY.items()}
    assert set(LOCK) == keys, "every field version needs a pinned fingerprint"
    for name, spec in REGISTRY.items():
        assert fingerprint(spec) == LOCK[f"{name}@v{spec.version}"], (
            f"{name}: meaning or enforcement changed (the registry entry, the engine's handling of the rule, or "
            f"the code that evaluates it). If the meaning changed, add a new version (leash fields: new .vN name; "
            f"Viseca paths: bump its interpretation version) and a new lock entry. If it is a pure refactor, "
            f"re-pin this entry and say why in the ticket.")


def test_every_field_names_the_code_that_enforces_it():
    for name in REGISTRY:
        assert EVALUATORS.get(name) or name in PENDING_EVALUATOR, f"{name}: no evaluator and not marked pending"
    assert not set(PENDING_EVALUATOR) & {n for n, mods in EVALUATORS.items() if mods}


def test_every_module_is_classified():
    # From the file system, not pkgutil: a directory without __init__.py is still importable (a namespace
    # package) and would otherwise escape classification and hashing (review round 8).
    from pathlib import Path

    import leash

    root = Path(leash.__file__).resolve().parent
    missing_init = [d for d in root.rglob("*") if d.is_dir() and d.name != "__pycache__"
                    and any(d.glob("*.py")) and not (d / "__init__.py").exists()]
    assert not missing_init, f"every package needs an __init__.py: {missing_init}"
    modules = set()
    for path in root.rglob("*.py"):
        parts = ("leash", *path.relative_to(root).with_suffix("").parts)
        modules.add(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    covered = set(SHARED_ENFORCEMENT) | {mod for mods in EVALUATORS.values() for mod in mods}
    unclassified = modules - covered - set(NOT_A_FIELD_MEANING)
    assert not unclassified, f"classify these in policy/registry.py (shared, evaluator, or not a meaning): {unclassified}"
    assert not covered & set(NOT_A_FIELD_MEANING)
    assert set(NOT_A_FIELD_MEANING) <= modules, "remove entries for modules that no longer exist"


def test_nothing_that_decides_behaviour_can_hide_outside_classified_python_modules():
    # Review round 9: code in a package marker, data files read by rules, compiled-only modules, symlinked
    # directories and sibling packages under src/ all escaped the fingerprint.
    import ast
    from pathlib import Path

    import leash

    root = Path(leash.__file__).resolve().parent
    src = root.parent
    assert sorted(p.name for p in src.iterdir() if not p.name.endswith(".egg-info")) == ["leash"], \
        "src/ may only hold the leash package"
    for path in root.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        assert not path.is_symlink(), f"no symlinks in the package: {path}"
        if path.is_file():
            assert path.suffix == ".py" or path.name == "py.typed", \
                f"only Python modules in the package (data that decides behaviour must be code): {path}"
    for marker in root.rglob("__init__.py"):
        body = [n for n in ast.parse(marker.read_text()).body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        assert not body, f"package markers must be empty (not hashed): {marker}"


def test_everything_an_evaluator_imports_is_hashed_for_that_field():
    # Review round 10 (N15, N16): a helper shared by two fields but listed under one, or an imported module
    # wrongly classified as "no meaning", would change a field's meaning without changing its fingerprint.
    import ast
    import importlib
    import inspect

    def leash_imports(module):
        tree = ast.parse(inspect.getsource(importlib.import_module(module)))
        package = module.rsplit(".", 1)[0]
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = package.split(".")
                    base = ".".join(parts[:len(parts) - node.level + 1] + ([base] if base else []))
                for alias in node.names:
                    candidate = f"{base}.{alias.name}"
                    try:
                        importlib.import_module(candidate)
                        found.add(candidate)
                    except ImportError:
                        found.add(base)
            elif isinstance(node, ast.Import):
                found |= {a.name for a in node.names}
        return {m for m in found if m.startswith("leash.") and m in sys.modules and sys.modules[m].__file__
                and not sys.modules[m].__file__.endswith("__init__.py")}

    import sys

    def pure_interface(module):
        """Only imports, a docstring and Protocol classes: nothing that can carry a meaning."""
        tree = ast.parse(inspect.getsource(importlib.import_module(module)))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            if isinstance(node, ast.ClassDef) and any(getattr(b, "id", None) == "Protocol" for b in node.bases):
                continue
            return False
        return True

    interfaces = {m for m in NOT_A_FIELD_MEANING if NOT_A_FIELD_MEANING[m] == "interface only" and pure_interface(m)}
    for name, modules in EVALUATORS.items():
        hashed = set(SHARED_ENFORCEMENT) | set(modules) | interfaces
        for module in modules:
            missing = leash_imports(module) - hashed
            assert not missing, f"{name}: {module} imports {missing}, which its fingerprint doesn't hash"
    # The shared core is hashed into every field, so what it imports must be hashed too (review round 11, N17).
    every_evaluator = {m for mods in EVALUATORS.values() for m in mods}
    for module in SHARED_ENFORCEMENT:
        missing = leash_imports(module) - set(SHARED_ENFORCEMENT) - every_evaluator - interfaces
        assert not missing, f"shared core {module} imports {missing}, which no fingerprint hashes"


# Modules that read the challenge pack's read-only CSV files (Viseca's data, not rule parameters).
READS_PACK_FILES = {"leash.adapters.pack.loader", "leash.adapters.pack.seed"}


def test_rule_parameters_are_code_not_environment_files_or_dynamic_imports():
    # Review round 12 (R1, R2, R4): a rule parameter read from an environment variable or a data file, or code
    # reached through a string import, changes a field's meaning without changing any hashed code.
    import ast
    import importlib
    import inspect

    hashed = set(SHARED_ENFORCEMENT) | {m for mods in EVALUATORS.values() for m in mods}
    for module in sorted(hashed):
        tree = ast.parse(inspect.getsource(importlib.import_module(module)))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv", "putenv"}:
                found.add(f"os.{node.attr}")
            if isinstance(node, ast.Name) and node.id in {"__import__", "getenv"}:
                found.add(node.id)
            if isinstance(node, ast.Attribute) and node.attr in {"import_module", "reload"}:
                found.add(f"importlib.{node.attr}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) else [])
                if any(n and (n == "importlib" or n.startswith("importlib.")) for n in names):
                    found.add("importlib")
            if module not in READS_PACK_FILES:
                if isinstance(node, ast.Name) and node.id == "open":
                    found.add("open()")
                if isinstance(node, ast.Attribute) and node.attr in {"read_text", "read_bytes", "open", "loads"} \
                        and not (isinstance(node.value, ast.Name) and node.value.id == "json" and node.attr == "loads"):
                    found.add(f".{node.attr}()")
        assert not found, f"{module} reads rule parameters from outside its code: {sorted(found)}"


def test_fingerprint_covers_the_schema(monkeypatch):
    # Review round 7, mutant A5: the familiarity view counting refunds kept the lock green.
    from pathlib import Path

    before = {name: fingerprint(spec) for name, spec in REGISTRY.items()}
    real = Path.read_text

    def mutated(self, *args, **kwargs):
        text = real(self, *args, **kwargs)
        return text.replace("WHERE transaction_type = 'purchase' AND", "WHERE") if self.name == "0001_initial.py" else text

    monkeypatch.setattr(Path, "read_text", mutated)
    assert all(fingerprint(spec) != before[name] for name, spec in REGISTRY.items())


def test_fingerprint_covers_the_shared_core(monkeypatch):
    # Review round 6, mutant U10: reading less of the shop's text changed verdicts with every test green.
    before = {name: fingerprint(spec) for name, spec in REGISTRY.items()}
    real = registry._source

    def mutated(module):
        text = real(module)
        return text + "\nMIN_LINE_SHARE = 4000\n" if module == "leash.domain.facts" else text  # survives refactors

    monkeypatch.setattr(registry, "_source", mutated)
    assert all(fingerprint(spec) != before[name] for name, spec in REGISTRY.items())


def test_fingerprint_covers_the_evaluator_code(monkeypatch):
    # Round-5 review mutant: "prior purchases >= 1" silently read as "> 1" in the rule evaluator.
    spec = REGISTRY["leash.merchant.prior_purchases.v1"]
    before = fingerprint(spec)
    real = registry._source

    def mutated(module):
        text = real(module)
        return text.replace("count >= need", "count > need") if module.endswith("rules.familiar") else text

    monkeypatch.setattr(registry, "_source", mutated)
    assert fingerprint(spec) != before
    assert fingerprint(REGISTRY["leash.items.size.v1"]) == LOCK["leash.items.size.v1@v1"]  # other fields unaffected


def test_enforcement_code_hash_ignores_comments_docstrings_and_formatting():
    base = "def f(x):\n    return x + 1\n"
    assert code_hash(base) == code_hash('def f(x):\n    """Adds one."""\n    # comment\n    return (x +\n 1)\n')
    assert code_hash(base) != code_hash("def f(x):\n    return x + 2\n")


def test_fingerprint_covers_what_the_engine_enforces(monkeypatch):
    spec = REGISTRY["leash.items.unrequested_count.v1"]
    before = fingerprint(spec)
    real = m.supported
    # Pretend someone let "unrequested <= 5" through: the fingerprint must change.
    allowed = {Decimal("1"), Decimal("2"), Decimal("5")}
    monkeypatch.setattr(m, "supported", lambda r: True if (
        r.field == spec.name and r.operator == "<=" and r.value in allowed and r.scope is None) else real(r))
    assert fingerprint(spec) != before


def test_viseca_paths_carry_an_interpretation_version():
    for name, spec in REGISTRY.items():
        if spec.source == "viseca":
            assert spec.version >= 1
