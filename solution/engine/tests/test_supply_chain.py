"""LEASH-141: the release controls are configuration, and configuration rots silently.

A pipeline's gates are only gates while they are still wired to the thing they gate. These checks read
the committed configuration and fail when a control is quietly lost: a base image that drifts back to a
tag, a scan that stops blocking the release, a lockfile that stops deciding, an ignore rule that would
let a secret or a build artifact into the repository.

They do not run the scanners — that needs the CI runner — but they do prove the wiring the scanners hang
from, which is the part a refactor breaks.
"""

import pathlib
import re
from pathlib import Path

import pytest
import yaml

from leash.adapters.postgres.migrate import head_revision

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = ROOT / "solution" / "engine" / "Dockerfile"
COMPOSE = ROOT / "solution" / "docker-compose.yml"
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")
#: Images this repository builds. Their identity is the commit they were built from, not a digest we
#: could pin here — pinning one would mean pinning yesterday's build of our own code.
OURS = ("leash-engine",)


@pytest.fixture(scope="module")
def ci() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


# --- every gate still gates ---------------------------------------------------------------------

#: The four kinds of evidence the ticket requires before a release, and the job that produces each.
REQUIRED_GATES = {"backend", "frontend", "secrets", "dependencies", "image"}


def test_the_release_waits_for_every_gate(ci):
    needs = set(ci["jobs"]["release"]["needs"])
    assert REQUIRED_GATES <= needs, f"these no longer block a release: {sorted(REQUIRED_GATES - needs)}"


def test_the_scans_fail_the_build_rather_than_warn(ci):
    trivy = _step(ci, "image", "aquasecurity/trivy-action")
    assert trivy["with"]["exit-code"] == "1", "a vulnerable image must stop the release, not annotate it"
    assert "CRITICAL" in trivy["with"]["severity"]
    audit = " ".join(s.get("run", "") for s in ci["jobs"]["dependencies"]["steps"])
    assert "pip-audit --strict" in audit and "npm audit --audit-level=high" in audit


def test_no_gate_can_fail_without_failing_the_workflow(ci):
    """`continue-on-error` on a job reports success to everything downstream, so `release` would run on
    an unscanned image. A gate that cannot fail the build is not a gate."""
    soft = []
    for name in REQUIRED_GATES:
        job = ci["jobs"][name]
        if job.get("continue-on-error"):
            soft.append(f"job {name}")
        for step in job["steps"]:
            if step.get("continue-on-error"):
                soft.append(f"{name}/{step.get('name') or step.get('uses')}")
    assert not soft, f"these cannot fail the build: {soft}"


def test_no_gate_swallows_its_own_exit_code(ci):
    """`|| true`, `; true` and `set +e` turn a failing command into a passing step; a substring check on
    the command would still see the command."""
    swallowed = []
    for name in REQUIRED_GATES:
        for step in ci["jobs"][name]["steps"]:
            run = step.get("run", "")
            if re.search(r"\|\|\s*(true|:)|;\s*true\b|set \+e|exit 0", run):
                swallowed.append(f"{name}/{step.get('name') or 'run'}")
    assert not swallowed, f"these hide a failure: {swallowed}"


def test_every_action_is_pinned_to_a_commit(ci):
    """A tag can move, and a tag that does not exist fails only at runtime — `trivy-action@0.28.0` was
    exactly that mistake (the real tag is `v0.28.0`). A commit SHA cannot be either."""
    loose = [step["uses"] for job in ci["jobs"].values() for step in job["steps"]
             if "uses" in step and not re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"].split(" #")[0].strip())]
    assert not loose, f"pin these to a commit SHA (keep the version in a trailing comment): {loose}"


def test_the_release_image_name_is_a_name_the_registry_accepts(ci):
    """`github.repository` keeps the owner's capitalisation; a registry rejects an uppercase name."""
    push = _step(ci, "release", "docker/build-push-action")
    assert "github.repository }}" not in push["with"]["tags"], \
        "lowercase the repository before using it as an image name"


def test_every_copy_of_an_image_digest_agrees(ci):
    """The same image pinned twice, updated once, is worse than not pinned: it looks deliberate."""
    digests: dict[str, set[str]] = {}
    for path in (DOCKERFILE, COMPOSE, WORKFLOW):
        for line in path.read_text(encoding="utf-8").splitlines():
            found = re.search(r"([\w./-]+):([\w.-]+)@(sha256:[0-9a-f]{64})", line)
            if found and not line.strip().startswith("#"):
                digests.setdefault(f"{found.group(1)}:{found.group(2)}", set()).add(found.group(3))
    disagreeing = {image: shas for image, shas in digests.items() if len(shas) > 1}
    assert not disagreeing, f"the same image is pinned to different digests: {disagreeing}"


def test_the_secret_scan_reads_the_whole_history(ci):
    checkout = next(s for s in ci["jobs"]["secrets"]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0, "a secret committed and removed is still a leaked secret"


def test_the_lockfiles_decide_what_is_installed(ci):
    runs = " ".join(s.get("run", "") for job in ci["jobs"].values() for s in job["steps"])
    assert "uv sync --frozen" in runs and "npm ci" in runs
    assert "pip install" not in runs and "npm install" not in runs


def test_the_image_is_built_once_and_promoted_by_digest(ci):
    sign = " ".join(s.get("run", "") for s in ci["jobs"]["release"]["steps"])
    assert "cosign sign" in sign and "steps.push.outputs.digest" in sign, "sign the digest, not a tag"


def test_provenance_is_a_cosign_attestation_on_the_pushed_digest(ci):
    """LEASH-196: GitHub's attestation store refuses user-owned private repositories, so provenance
    travels with the image in the registry instead, where `cosign verify-attestation` finds it."""
    uses = [str(s.get("uses", "")) for s in ci["jobs"]["release"]["steps"]]
    assert not any(u.startswith("actions/attest") for u in uses), \
        "GitHub attestations fail on a private user-owned repository"
    step = next(s for s in ci["jobs"]["release"]["steps"] if "cosign attest" in s.get("run", ""))
    assert "--type slsaprovenance1" in step["run"]
    assert "steps.push.outputs.digest" in str(step), "attest the digest, not a tag"
    assert "attestations" not in ci["jobs"]["release"]["permissions"], "no longer needed; least privilege"


def test_the_release_notes_name_the_commit_the_schema_and_the_evidence(ci):
    notes = next(s["run"] for s in ci["jobs"]["release"]["steps"] if s.get("name") == "release notes")
    for needed in ("github.sha", "Schema revision", "Evidence", "github.run_id", "DIGEST"):
        assert needed in notes, f"release notes must name {needed}"


def test_the_release_notes_derive_the_right_schema_revision():
    """Run the extraction, rather than grep the YAML for it: a wrong command would still contain the
    words. It is a shell one-liner and needs no runner, so there is no excuse for leaving it unproven."""
    import subprocess

    ci = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    line = next(l for l in next(s["run"] for s in ci["jobs"]["release"]["steps"]
                                if s.get("name") == "release notes").splitlines()
                if l.strip().startswith("SCHEMA="))
    script = f'{line.strip()}\necho "${{SCHEMA%%_*}}"'
    got = subprocess.run(["bash", "-c", script], cwd=ROOT, capture_output=True, text=True, check=True)
    assert got.stdout.strip() == head_revision(), \
        f"the notes would claim schema {got.stdout.strip()!r}, the database is at {head_revision()!r}"


def test_migration_names_are_padded_so_the_sort_cannot_be_ambiguous():
    """What actually makes the release note's `sort … | tail -1` correct.

    A reviewer flagged the lexicographic sort as picking `0009` over `0010`. It does not — with a fixed
    width, lexicographic and numeric order are the same — so the real invariant to pin is the padding,
    not the sort. One unpadded name (`10_later.py`) and the extraction silently reports the wrong schema
    revision in a release note.
    """
    names = [p.name for p in (ROOT / "solution" / "engine" / "migrations" / "versions").glob("*.py")]
    widths = {len(name.split("_")[0]) for name in names}
    assert len(widths) == 1, f"migration numbers must all be the same width, found {widths}: {sorted(names)}"
    assert all(name.split("_")[0].isdigit() for name in names), sorted(names)


def test_a_release_only_happens_from_the_reviewed_branch(ci):
    assert ci["jobs"]["release"]["if"].strip().endswith("github.ref == 'refs/heads/leash-mvp'")


# --- nothing drifts -----------------------------------------------------------------------------

@pytest.mark.parametrize("path", [DOCKERFILE, COMPOSE, WORKFLOW], ids=lambda p: p.name)
def test_every_external_image_is_pinned_by_digest(path):
    """A tag is a moving target: the same source would build a different image next week."""
    loose = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if text.startswith("#"):
            continue
        for marker in ("FROM ", "COPY --from=", "image: "):
            if marker not in text or "scratch" in text or DIGEST.search(text):
                continue
            if any(ours in text for ours in OURS):
                continue
            # a build stage referring to an earlier stage by name is not an external image
            if marker == "COPY --from=" and "/" not in text.split("COPY --from=")[1].split()[0]:
                continue
            loose.append(f"{path.name}:{number}: {text}")
    assert not loose, "pin these by digest:\n  " + "\n  ".join(loose)


def test_the_repository_ignores_environments_caches_artifacts_and_secrets():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for rule in ("node_modules/", ".venv/", "__pycache__/", ".pytest_cache/", ".mypy_cache/",
                 "solution/app/dist/", ".env"):
        assert rule in ignored, f".gitignore must cover {rule}"


#: BuildKit uses `<dockerfile>.dockerignore` when one sits next to the Dockerfile, and ignores the
#: repository root's `.dockerignore` entirely. Every build here is `-f solution/engine/Dockerfile`, so
#: this is the file that decides — asserting on the root one would be asserting on a file nothing reads.
EFFECTIVE_DOCKERIGNORE = DOCKERFILE.parent / "Dockerfile.dockerignore"


def test_the_ignore_file_that_actually_applies_is_the_one_next_to_the_dockerfile():
    assert EFFECTIVE_DOCKERIGNORE.exists(), (
        "this file takes precedence over the root .dockerignore for `-f solution/engine/Dockerfile`; "
        "if it is removed, the root one applies instead and this test must be rewritten")


def test_the_build_context_carries_nothing_from_a_developers_machine():
    ignored = EFFECTIVE_DOCKERIGNORE.read_text(encoding="utf-8")
    for rule in ("**/node_modules", "**/.venv", "**/__pycache__", "**/*.pyc", "**/*.egg-info",
                 "solution/app/dist", ".git"):
        assert rule in ignored, f"the effective .dockerignore must cover {rule}"


def test_no_env_file_can_reach_the_build_context():
    """Anything copied into a context is readable in the image's layers."""
    ignored = EFFECTIVE_DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored and "**/.env" in ignored, \
        "a developer's .env must not be buildable into the image"


def test_nothing_ignored_is_actually_tracked():
    """An ignore rule added after the fact does not untrack what is already in the index."""
    import subprocess

    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout; there is no index to check")
    tracked = subprocess.run(["git", "ls-files", "--", ":!:*.gitignore"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.split()
    bad = [f for f in tracked
           if "/node_modules/" in f or "/.venv/" in f or "__pycache__" in f or f.startswith("solution/app/dist/")
           or f.endswith(".pyc")
           or (pathlib.PurePosixPath(f).name.startswith(".env")
               and pathlib.PurePosixPath(f).name != ".env.example")]
    assert not bad, f"tracked but should be ignored: {bad[:10]}"


def test_updates_to_pinned_things_go_through_review():
    dependabot = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    ecosystems = {u["package-ecosystem"] for u in dependabot["updates"]}
    assert {"docker", "uv", "npm", "github-actions"} <= ecosystems, \
        "a digest pin only stays current if something proposes the update as a reviewable change"


def _step(ci: dict, job: str, uses: str) -> dict:
    return next(s for s in ci["jobs"][job]["steps"] if str(s.get("uses", "")).startswith(uses))
