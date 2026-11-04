"""L2 previewed additive adoption of a legacy workbench (contract section 12).

Preview computes one deterministic plan from the current files and writes nothing.
Confirmation recomputes it and applies it only when the researcher's digest still
matches, through the root journal. Projects, objects, handoffs, bindings, context
archives and history are never touched; no model or session is started.
"""

import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from toulmin.core.adoption import (
    ADOPTION_DIR,
    CONTRACT,
    WATCHED,
    Change,
    Conflict,
    matches,
    render_plan,
    validate_plan,
)
from toulmin.core.atomic import digest, handoff_mutex
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.proposals import SEAL, Receipt, render_receipt
from toulmin.core.repository import Repository
from toulmin.core.schema import utc_text
from toulmin.core.workspace import CHARTER_FILE, render_initial, validate_name
from toulmin.core.workspace_journal import Image, Intent, finish, pending, prepare, read_intent
from toulmin.protocols.workspace_change import receipt_for
from toulmin.protocols.workspace_state import RootState, classify_root

SCOPE_HEADING = "## Workspace and project scopes"
JOURNAL_PATTERNS = (
    ".workspace-pending/",
    ".workspace-prepare-*/",
    ".workspace-completed-*/",
    "projects/.creating-*/",
)
RECORD_LOCATIONS = ("runs/drafts", "sessions", "shared/resources")
PLAN = "plan.md"


@dataclass(frozen=True)
class AdoptionTemplates:
    """Packaged inputs supplied by L3; L2 never reads package data itself."""

    agents: bytes  # current workspace research instructions
    contract: bytes  # packaged framework/workspace-formats.md
    released: dict[str, frozenset[str]]  # path -> digests of every released copy
    setup: dict[str, bytes]  # expected setup files, for root classification


@dataclass(frozen=True)
class Plan:
    name: str
    changes: tuple[Change, ...]
    conflicts: tuple[Conflict, ...]
    data: bytes

    @property
    def digest(self) -> str:
        return digest(self.data)


@dataclass(frozen=True)
class AdoptionOutcome:
    """status: preview, adopted, recovered, replayed, configured, incomplete."""

    status: str
    root: Path
    plan: Plan | None = None
    directory: str | None = None
    receipt: Receipt | None = None
    problems: tuple[str, ...] = ()


def scope_section(agents: bytes) -> str:
    """The template's scope section, appended to customized instructions."""
    content = agents.decode()
    match = re.search(rf"^{re.escape(SCOPE_HEADING)}\n.*?(?=^## |\Z)", content, re.M | re.S)
    if match is None:
        raise FormatError(f"workspace template: missing {SCOPE_HEADING!r} section")
    return match.group(0).rstrip("\n") + "\n"


def _regular(repository: Repository, relative: str) -> bytes | None | Conflict:
    """Bytes of a regular file, None when absent, or a conflict for anything else."""
    path = repository.root / relative
    if not os.path.lexists(path):
        return None
    if path.is_symlink() or not path.is_file():
        return Conflict(relative, "expected a regular file; links and directories are not adopted")
    return path.read_bytes()


def _empty(path: Path) -> bool:
    """A directory holding nothing but empty .gitkeep placeholders (and directories)."""
    for item in path.rglob("*"):
        if item.is_symlink():
            return False
        if item.is_file() and (item.name != ".gitkeep" or item.stat().st_size):
            return False
    return True


def _agents(
    repository: Repository, templates: AdoptionTemplates
) -> tuple[Change | None, Conflict | None]:
    current = _regular(repository, "AGENTS.md")
    if isinstance(current, Conflict):
        return None, current
    if current is None:
        return None, Conflict("AGENTS.md", "missing; restore the workbench instructions")
    if current == templates.agents:
        return None, None
    if digest(current) in templates.released.get("AGENTS.md", frozenset()):
        return Change("AGENTS.md", current, templates.agents), None
    text = current.decode("utf-8", "replace")
    if re.search(rf"^{re.escape(SCOPE_HEADING)}[ \t]*$", text, re.M):
        return None, Conflict(
            "AGENTS.md",
            f"customized instructions already have a {SCOPE_HEADING!r} section; merge it by "
            "hand, then preview again",
        )
    base = text if text.endswith("\n") else text + "\n"
    return Change(
        "AGENTS.md", current, (base + "\n" + scope_section(templates.agents)).encode()
    ), None


def compute(root: Path, name: str | None, templates: AdoptionTemplates) -> Plan:
    """The exact plan for a recognized legacy root; refuses every other root state."""
    report = classify_root(root, templates.setup)
    root = report.root
    if report.state == RootState.WORKSPACE:
        raise FormatError(f"{root}: workspace state already configured; nothing to adopt")
    if report.state != RootState.LEGACY:
        hint = {
            RootState.MISSING: "`toulmin init ROOT` creates a workspace",
            RootState.EMPTY: "`toulmin init ROOT` creates a workspace",
            RootState.INCOMPLETE: "rerun `toulmin init ROOT` to finish setup",
            RootState.UNRELATED: "not a Toulmin workbench; choose another directory",
        }[report.state]
        raise FormatError(f"{root}: {report.state.value} root, not a legacy workbench; {hint}")
    if report.unexpected:
        raise FormatError(
            f"{root}: workbench files but no projects (unexpected or modified: "
            f"{', '.join(report.unexpected)}); nothing to adopt. If this is an interrupted "
            "init, restore those files and rerun init"
        )
    try:
        chosen = validate_name(name if name is not None else root.name)
    except ValueError as error:
        raise FormatError(f"{error}; pass --name") from error
    repository = Repository(root)
    changes: list[Change] = []
    conflicts: list[Conflict] = []
    change, conflict = _agents(repository, templates)
    changes += [change] if change else []
    conflicts += [conflict] if conflict else []

    contract = _regular(repository, CONTRACT)
    if isinstance(contract, Conflict):
        conflicts.append(contract)
    elif contract is None:
        changes.append(Change(CONTRACT, None, templates.contract))
    elif contract != templates.contract:
        if digest(contract) in templates.released.get(CONTRACT, frozenset()):
            changes.append(Change(CONTRACT, contract, templates.contract))
        else:
            conflicts.append(
                Conflict(
                    CONTRACT,
                    "differs from every released copy; keep your edits elsewhere, restore or "
                    "remove it, then preview again",
                )
            )

    ignore = _regular(repository, ".gitignore")
    if isinstance(ignore, Conflict):
        conflicts.append(ignore)
    else:
        lines = (ignore or b"").decode("utf-8", "replace").splitlines()
        missing = [pattern for pattern in JOURNAL_PATTERNS if pattern not in lines]
        if missing:
            base = ignore or b""
            if base and not base.endswith(b"\n"):
                base += b"\n"
            changes.append(
                Change(".gitignore", ignore, base + "".join(f"{m}\n" for m in missing).encode())
            )

    for location in ("runs", "sessions", "shared", "shared/resources"):
        path = repository.root / location
        if not os.path.lexists(path):
            continue
        if path.is_symlink() or not path.is_dir():
            conflicts.append(Conflict(location, "expected a directory"))
        elif location != "shared" and not _empty(path):
            conflicts.append(
                Conflict(
                    location,
                    "holds existing root data, which adoption never reclassifies; move it "
                    "aside, then preview again",
                )
            )
    for location in RECORD_LOCATIONS:
        placeholder = f"{location}/.gitkeep"
        if not os.path.lexists(repository.root / placeholder):
            changes.append(Change(placeholder, None, b""))
    if os.path.lexists(repository.root / ".aoe/binding.json"):
        conflicts.append(
            Conflict(
                ".aoe/binding.json",
                "a root binding exists without workspace state; it is never reinterpreted",
            )
        )
    changes.append(Change(CHARTER_FILE, None, render_initial(chosen)))
    absent = tuple(item for item in WATCHED if not os.path.lexists(repository.root / item))
    folder = repository.root / "projects"
    projects = tuple(
        sorted(
            path.name
            for path in folder.iterdir()
            if not path.name.startswith(".") and path.is_dir() and not path.is_symlink()
        )
    )
    unique = tuple(dict.fromkeys(conflicts))
    data = render_plan(chosen, tuple(changes), absent, unique, projects)
    return Plan(chosen, tuple(changes), unique, data)


def preview(root: Path, name: str | None, templates: AdoptionTemplates) -> AdoptionOutcome:
    """Read-only: the plan, an incomplete adoption, or the configured workspace."""
    repository = Repository(classify_root(root, templates.setup).root)
    if pending(repository):
        intent = read_intent(repository)
        if intent.operation == "adoption":
            return AdoptionOutcome(
                "incomplete",
                repository.root,
                directory=intent.record.removesuffix("/plan.md"),
                problems=(
                    f"adoption interrupted; rerun with --plan-digest {intent.record_sha256} "
                    "--confirm to finish it",
                ),
            )
        raise FormatError(
            f"incomplete {intent.operation} for {intent.record}; rerun that operation's command "
            "first"
        )
    if os.path.lexists(repository.root / CHARTER_FILE):
        found = _adopted(repository, None)
        return AdoptionOutcome(
            "configured",
            repository.root,
            directory=found[0] if found else None,
            receipt=found[1] if found else None,
        )
    return AdoptionOutcome("preview", repository.root, compute(root, name, templates))


def _adopted(repository: Repository, value: str | None) -> tuple[str, Receipt] | None:
    """The applied adoption archive (matching ``value`` when given), from files only."""
    runs = repository.root / "runs"
    for path in sorted(runs.iterdir()) if runs.is_dir() and not runs.is_symlink() else ():
        relative = f"runs/{path.name}"
        if not ADOPTION_DIR.fullmatch(relative):
            continue
        try:
            plan = repository.path(f"{relative}/plan.md", "file").read_bytes()
            sealed = repository.path(f"{relative}/seal", "file").read_bytes()
            if not SEAL.fullmatch(sealed.decode("utf-8", "replace")):
                continue
            seal = sealed.decode().strip()
            if seal != digest(plan):
                continue
            validate_plan(decode(plan, f"{relative}/plan.md"))
            receipt = receipt_for(repository, relative, seal, PLAN)
        except (OSError, ValueError):
            continue
        if receipt is not None and receipt.disposition == "applied":
            if value is None or matches(value, seal):
                return relative, receipt
    return None


def adopt(
    root: Path,
    name: str | None,
    templates: AdoptionTemplates,
    plan_digest: str,
    actor: str,
    *,
    approval_text: str | None = None,
    now: datetime | None = None,
    token: str | None = None,
) -> AdoptionOutcome:
    """Apply the previewed plan when ``plan_digest`` still names it; idempotent."""
    if not actor.strip():
        raise FormatError("adopt: a confirming actor is required (--confirmed-by)")
    if not re.fullmatch(r"[0-9a-f]{16,64}", plan_digest):
        raise FormatError("--plan-digest: expected the plan digest (at least 16 hex digits)")
    repository = Repository(classify_root(root, templates.setup).root)
    with handoff_mutex(repository.root):
        if pending(repository):
            intent = read_intent(repository)
            if intent.operation != "adoption":
                raise FormatError(
                    f"incomplete {intent.operation} for {intent.record}; rerun that operation's "
                    "command first"
                )
            if not matches(plan_digest, intent.record_sha256):
                raise FormatError(
                    f"incomplete adoption of plan {intent.record_sha256} is pending; rerun with "
                    "that digest; journal kept"
                )
            notes = []
            if actor != intent.actor:
                notes.append(
                    f"--confirmed-by {actor} ignored; recovery keeps the first confirmation "
                    f"by {intent.actor} at {intent.at}"
                )
            finish(repository)
            directory = intent.record.removesuffix("/plan.md")
            return AdoptionOutcome(
                "recovered",
                repository.root,
                directory=directory,
                receipt=receipt_for(repository, directory, intent.record_sha256, PLAN),
                problems=tuple(notes),
            )
        if os.path.lexists(repository.root / CHARTER_FILE):
            found = _adopted(repository, plan_digest)
            if found is None:
                raise FormatError(
                    f"{repository.root}: workspace state already configured; nothing to adopt"
                )
            return AdoptionOutcome(
                "replayed", repository.root, directory=found[0], receipt=found[1]
            )
        plan = compute(repository.root, name, templates)
        if not matches(plan_digest, plan.digest):
            raise FormatError(
                f"plan changed since preview (current digest {plan.digest}); review the new plan; "
                "nothing written"
            )
        if plan.conflicts:
            listed = "; ".join(f"{item.path}: {item.reason}" for item in plan.conflicts)
            raise FormatError(f"plan has conflicts ({listed}); nothing written")
        moment = (now or datetime.now(UTC)).astimezone(UTC)
        directory = f"runs/{moment.strftime('%Y%m%dT%H%M%SZ')}-adoption-{token or uuid.uuid4().hex}"
        if os.path.lexists(repository.root / directory):
            raise FormatError(f"{directory}: already exists; retry in a second")
        at = utc_text(moment)
        record = f"{directory}/plan.md"
        results = [
            {
                "path": change.path,
                "before_sha256": None if change.before is None else digest(change.before),
                "after_sha256": digest(change.after),
            }
            for change in plan.changes
        ]
        receipt = render_receipt(
            record, plan.digest, "applied", actor, at, approval_text, None, results
        )
        # WORKSPACE.md (the last change) is published after the archive, just before
        # the receipt, so the root becomes a workspace only once everything else exists.
        images = [Image(c.path, c.before, c.after) for c in plan.changes[:-1]]
        images += [
            Image(record, None, plan.data),
            Image(f"{directory}/seal", None, (plan.digest + "\n").encode()),
            Image(plan.changes[-1].path, None, plan.changes[-1].after),
            Image(f"{directory}/receipt.md", None, receipt),
        ]
        prepare(
            repository,
            Intent("adoption", record, plan.digest, actor, at, approval_text, tuple(images)),
        )
        finish(repository)
    return AdoptionOutcome(
        "adopted",
        repository.root,
        plan,
        directory,
        receipt_for(repository, directory, plan.digest, PLAN),
    )
