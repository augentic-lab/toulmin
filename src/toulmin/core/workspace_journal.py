"""Recoverable forward publication of workspace records (contract section 10).

One journal per workspace root. Every image is written and synced in a prepare
directory, which is then renamed into place: that rename is the commit point.
Recovery accepts each target only at its exact before or after image; anything else
is an external edit, preserved and refused, never rolled back.
"""

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from toulmin.core.atomic import digest, sync_directory, write_atomic
from toulmin.core.codec import decode
from toulmin.core.creation import STAGING
from toulmin.core.documents import FormatError
from toulmin.core.render import header
from toulmin.core.repository import Repository
from toulmin.core.schema import mapping, text, timestamp

JOURNAL = ".workspace-pending"
PREPARE = ".workspace-prepare-"
COMPLETED = ".workspace-completed-"
OPERATIONS = ("workspace-change", "workspace-handoff", "project-create", "adoption")
INTENT_FIELDS = (
    "schema_version",
    "operation",
    "record",
    "record_sha256",
    "actor",
    "at",
    "approval_text",
    "targets",
)


@dataclass(frozen=True)
class Image:
    """One target: absent before when ``before`` is None; ``after`` is always written."""

    path: str
    before: bytes | None
    after: bytes


@dataclass(frozen=True)
class Intent:
    operation: str
    record: str
    record_sha256: str
    actor: str
    at: str
    approval_text: str | None
    images: tuple[Image, ...]
    # project-create only: the private directory that becomes projects/NAME in one rename.
    staging: str | None = None


def pending(repository: Repository) -> bool:
    return os.path.lexists(repository.root / JOURNAL)


def prepare(repository: Repository, intent: Intent) -> None:
    """Durably record the complete intent; nothing public changes yet."""
    if intent.operation not in OPERATIONS:
        raise FormatError(f"{intent.operation}: unknown journal operation")
    if pending(repository):
        raise FormatError(f"{repository.root / JOURNAL}: unresolved publication journal")
    targets = [
        {
            "path": image.path,
            "before_sha256": None if image.before is None else digest(image.before),
            "after_sha256": digest(image.after),
        }
        for image in intent.images
    ]
    fields: list[tuple[str, Any]] = [
        ("schema_version", 1),
        ("operation", intent.operation),
        ("record", intent.record),
        ("record_sha256", intent.record_sha256),
        ("actor", intent.actor),
        ("at", intent.at),
        ("approval_text", intent.approval_text),
        ("targets", targets),
    ]
    if (intent.operation == "project-create") != (intent.staging is not None):
        raise FormatError("staging: required for project-create and only for it")
    if intent.staging is not None:
        fields.append(("staging", intent.staging))
    with tempfile.TemporaryDirectory(prefix=PREPARE, dir=repository.root) as temporary:
        staging = Path(temporary)
        (staging / "before").mkdir()
        (staging / "after").mkdir()
        for index, image in enumerate(intent.images, 1):
            if image.before is not None:
                write_atomic(staging / "before" / str(index), image.before)
            write_atomic(staging / "after" / str(index), image.after)
        write_atomic(
            staging / "intent.md", (header(fields) + "Workspace publication intent.\n").encode()
        )
        sync_directory(staging)
        os.rename(staging, repository.root / JOURNAL)
    sync_directory(repository.root)


def incomplete_child(repository: Repository) -> str | None:
    """The child a pending project-create journal is publishing, if any (read-only)."""
    if not pending(repository):
        return None
    try:
        intent = read_intent(repository)
    except (OSError, ValueError):
        return None
    if intent.operation != "project-create":
        return None
    return next(
        (image.path.split("/")[1] for image in intent.images if image.path.startswith("projects/")),
        None,
    )


def read_intent(repository: Repository) -> Intent:
    """Load and verify the journal; corrupt journals are errors, never repaired."""
    base = f"{JOURNAL}/intent.md"
    document = decode(repository.path(base, "file").read_bytes(), str(repository.root / base))
    h = mapping(document, document.header, "", set(INTENT_FIELDS), {"staging"})
    if h["schema_version"] != 1 or h["operation"] not in OPERATIONS:
        document.fail("operation", "unsupported journal")
    staging = h.get("staging")
    if (h["operation"] == "project-create") != (staging is not None):
        document.fail("staging", "required for project-create and only for it")
    if staging is not None and not STAGING.fullmatch(text(document, staging, "staging")):
        document.fail("staging", "expected projects/.creating-<hex>")
    text(document, h["record"], "record")
    text(document, h["record_sha256"], "record_sha256")
    text(document, h["actor"], "actor")
    timestamp(document, h["at"], "at")
    if h["approval_text"] is not None:
        text(document, h["approval_text"], "approval_text")
    if not isinstance(h["targets"], list) or not h["targets"]:
        document.fail("targets", "expected a nonempty list")
    images = []
    for index, item in enumerate(h["targets"], 1):
        field = f"targets[{index - 1}]"
        target = mapping(document, item, field, {"path", "before_sha256", "after_sha256"})
        after = repository.path(f"{JOURNAL}/after/{index}", "file").read_bytes()
        if digest(after) != target["after_sha256"]:
            document.fail(f"{field}.after_sha256", "journal after image changed")
        before = None
        if target["before_sha256"] is not None:
            before = repository.path(f"{JOURNAL}/before/{index}", "file").read_bytes()
            if digest(before) != target["before_sha256"]:
                document.fail(f"{field}.before_sha256", "journal before image changed")
        images.append(Image(text(document, target["path"], f"{field}.path"), before, after))
    return Intent(
        h["operation"],
        h["record"],
        h["record_sha256"],
        h["actor"],
        h["at"],
        h["approval_text"],
        tuple(images),
        staging,
    )


def finish(repository: Repository) -> Intent:
    """Publish every remaining image in order, then retire the journal.

    All targets are checked first; a single external edit stops recovery before
    any write, with every image kept for inspection.
    """
    intent = read_intent(repository)
    if intent.staging is not None:
        return _finish_creation(repository, intent)
    states = []
    for image in intent.images:
        path = repository.path(image.path)
        current = path.read_bytes() if path.exists() else None
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise FormatError(f"{image.path}: expected a regular file; journal kept")
        if current == image.after:
            states.append(True)
        elif current == image.before:
            states.append(False)
        else:
            raise FormatError(
                f"{image.path}: changed outside this publication (expected before "
                f"{digest(image.before) if image.before is not None else 'absent'} or after "
                f"{digest(image.after)}, found "
                f"{digest(current) if current is not None else 'absent'}); journal kept. "
                "Restore one image by hand, then rerun the same command"
            )
    for image, done in zip(intent.images, states, strict=True):
        if done:
            continue
        path = repository.path(image.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        repository.path(image.path)  # recheck links after creating parents
        write_atomic(path, image.after, replace=image.before is not None)
    retire(repository)
    return intent


def _external(path: str, image: Image | None, current: bytes | None) -> FormatError:
    expected = (
        "no such file"
        if image is None
        else f"before {digest(image.before) if image.before is not None else 'absent'} or "
        f"after {digest(image.after)}"
    )
    found = digest(current) if current is not None else "absent"
    return FormatError(
        f"{path}: changed outside this publication (expected {expected}, found {found}); "
        "journal kept. Restore one image by hand, then rerun the same command"
    )


def _tree(repository: Repository, directory: str) -> dict[str, Path]:
    """Every entry under a directory, by root-relative path; links are refused."""
    base = repository.path(directory, "directory")
    found: dict[str, Path] = {}
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(repository.root).as_posix()
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise FormatError(f"{relative}: expected a regular file or directory; journal kept")
        found[relative] = path
    return found


def _finish_creation(repository: Repository, intent: Intent) -> Intent:
    """Publish a child: build it in staging, rename it into place, then the receipt.

    The child appears under its name in one rename. Before any write, the staging
    directory or the published child must hold only expected files at their after
    images (unfinished atomic-write temporaries in staging are discarded); anything
    else is an external edit, preserved and refused.
    """
    assert intent.staging is not None
    child = [image for image in intent.images if image.path.startswith("projects/")]
    rest = [image for image in intent.images if not image.path.startswith("projects/")]
    final = child[0].path.split("/")[1]
    target = f"projects/{final}"
    if any(image.before is not None or not image.path.startswith(f"{target}/") for image in child):
        raise FormatError(f"{JOURNAL}: project-create images must be new files in {target}")
    exists = os.path.lexists(repository.root / target)
    staged = os.path.lexists(repository.root / intent.staging)
    if exists and staged:
        raise FormatError(
            f"{target} and {intent.staging} both exist; journal kept. Inspect both, keep the "
            "published child, then rerun the same command"
        )
    directory = target if exists else intent.staging
    expected = {
        (image.path if exists else intent.staging + image.path.removeprefix(target)): image
        for image in child
    }
    parents = {str(Path(path).parent) for path in expected} | {directory}
    parents |= {str(parent) for path in parents for parent in Path(path).parents}
    present: dict[str, Path] = _tree(repository, directory) if exists or staged else {}
    discard = []
    for relative, path in present.items():
        if path.is_dir():
            if relative not in parents:
                raise FormatError(
                    f"{relative}: unexpected directory in this publication; journal kept. "
                    "Remove it by hand, then rerun the same command"
                )
            continue
        image = expected.get(relative)
        if image is None:
            if not exists and path.name.startswith(".handoff-") and path.name.endswith(".tmp"):
                discard.append(path)  # an unfinished temporary of this writer
                continue
            raise _external(relative, None, path.read_bytes())
        if path.read_bytes() != image.after:
            raise _external(relative, image, path.read_bytes())
    if exists and set(expected) - set(present):
        missing = sorted(set(expected) - set(present))[0]
        raise _external(missing, expected[missing], None)
    later = []
    for image in rest:
        path = repository.path(image.path)
        current = path.read_bytes() if path.is_file() and not path.is_symlink() else None
        if os.path.lexists(path) and current is None:
            raise FormatError(f"{image.path}: expected a regular file; journal kept")
        if current not in (image.before, image.after):
            raise _external(image.path, image, current)
        later.append((image, current == image.after))
    if not exists:
        for path in discard:
            path.unlink()
        if not staged:
            repository.path("projects", "directory")
            os.mkdir(repository.root / intent.staging)
        for relative, image in expected.items():
            if relative in present:
                continue
            path = repository.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            repository.path(relative)  # recheck links after creating parents
            write_atomic(path, image.after)
        for relative in sorted(parents, key=len, reverse=True):
            if relative.startswith(intent.staging):
                sync_directory(repository.root / relative)
        os.rename(repository.root / intent.staging, repository.root / target)
        sync_directory(repository.path("projects", "directory"))
    for image, done in later:
        if not done:
            path = repository.path(image.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(path, image.after, replace=image.before is not None)
    retire(repository)
    return intent


def retire(repository: Repository) -> None:
    completed = repository.root / f"{COMPLETED}{uuid.uuid4().hex}"
    os.rename(repository.root / JOURNAL, completed)
    sync_directory(repository.root)
    shutil.rmtree(completed, ignore_errors=True)


def remove_completed(repository: Repository) -> None:
    """Retired journals carry no state; a later writer removes leftover remnants."""
    for path in repository.root.glob(f"{COMPLETED}*"):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
