"""Record a selected migration batch without copying or validating external code.

A receipt confirms the researcher's assessment of the recorded batch, not a research
conclusion. The immutable input and checks remain available for subsequent inspection.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from toulmin.core.atomic import digest, handoff_mutex, write_atomic
from toulmin.core.codec import decode, encode
from toulmin.core.documents import Document, FormatError
from toulmin.core.repository import Repository
from toulmin.core.sources import read_catalog

FIELDS = {
    "schema_version",
    "kind",
    "project",
    "source",
    "source_version",
    "target",
    "target_version",
    "items",
    "checks",
    "outcome",
}


def draft(root: Path, project: str) -> Path:
    repository = Repository(root)
    repository.project(project)
    path = repository.path(f"projects/{project}/runs/drafts/migration-{uuid4().hex}.md")
    data = {
        "schema_version": 1,
        "kind": "migration-batch",
        "project": project,
        "source": "<fill: registered source ID>",
        "source_version": "<fill: commit or digest>",
        "target": "<fill: registered target ID>",
        "target_version": "<fill: commit or digest>",
        "items": ["<fill: selected relative file or module>"],
        "checks": ["<fill: command, result and archived output path>"],
        "outcome": "<fill: passed, failed or partial>",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(
        path,
        encode(
            Document(
                data,
                "## Rationale\n<fill: why these parts>\n\n"
                "## Differences\n<fill: changes from the source>\n",
            )
        ),
    )
    return path


def preview(root: Path, project: str, relative: str) -> tuple[bytes, str]:
    repository = Repository(root)
    repository.project(project)
    relative = repository.relative(relative)
    if not relative.startswith(f"projects/{project}/runs/drafts/"):
        raise FormatError("migration input must be a draft in this project's runs/drafts")
    raw = repository.path(relative, "file").read_bytes()
    if len(raw) > 131072:
        raise FormatError("migration draft exceeds 128 KiB")
    document = decode(raw, relative)
    h = document.header
    if set(h) != FIELDS or type(h["schema_version"]) is not int or h["schema_version"] != 1:
        raise FormatError("expected migration-batch version 1 fields")
    if h["kind"] != "migration-batch" or h["project"] != project:
        raise FormatError("migration kind or project mismatch")
    for name in ("source", "source_version", "target", "target_version"):
        if not isinstance(h[name], str) or not h[name].strip():
            raise FormatError(f"migration {name}: nonempty text required")
    associated = {s.source_id for s in read_catalog(root) if s.project == project}
    if h["source"] not in associated or h["target"] not in associated:
        raise FormatError("migration source and target must be registered to this project")
    if h["source"] == h["target"]:
        raise FormatError("migration source and target must differ")
    for name in ("items", "checks"):
        if (
            not isinstance(h[name], list)
            or not h[name]
            or any(not isinstance(value, str) or not value.strip() for value in h[name])
        ):
            raise FormatError(f"migration {name}: nonempty text list required")
    if h["outcome"] not in {"passed", "failed", "partial"}:
        raise FormatError("migration outcome: expected passed, failed or partial")
    if "<fill:" in raw.decode() or not document.body.strip():
        raise FormatError("complete the migration draft before recording it")
    return raw, digest(raw)


def record(root: Path, project: str, relative: str, actor: str, expected: str) -> Path:
    if not actor.strip():
        raise FormatError("researcher attribution required")
    repository = Repository(root)
    with handoff_mutex(repository.project(project)):
        raw, sha = preview(root, project, relative)
        if sha != expected:
            raise FormatError("migration draft changed after preview")
        target = repository.path(f"projects/{project}/runs/migration-{sha}/receipt.md")
        if target.exists():
            existing = decode(target.read_bytes(), str(target))
            source = decode(raw, relative)
            expected_fields = dict(source.header)
            expected_fields.update(kind="migration-receipt", input_sha256=sha)
            if (
                set(existing.header) != set(expected_fields) | {"confirmed_by", "confirmed_at"}
                or any(existing.header.get(key) != value for key, value in expected_fields.items())
                or existing.body
                != "This records the researcher's assessment, not independent verification.\n\n"
                + source.body
            ):
                raise FormatError("migration receipt conflict")
            recorded_actor = existing.header.get("confirmed_by")
            recorded_at = existing.header.get("confirmed_at")
            if not isinstance(recorded_actor, str) or not recorded_actor.strip():
                raise FormatError("migration receipt actor missing")
            if (
                not isinstance(recorded_at, str)
                or datetime.fromisoformat(recorded_at).utcoffset() is None
            ):
                raise FormatError("migration receipt requires a timezone-aware confirmation time")
            return target
        source = decode(raw, relative)
        header = dict(source.header)
        header.update(
            {
                "kind": "migration-receipt",
                "input_sha256": sha,
                "confirmed_by": actor,
                "confirmed_at": datetime.now(UTC).isoformat(),
            }
        )
        body = (
            "This records the researcher's assessment, not independent verification.\n\n"
            + source.body
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, encode(Document(header, body)))
        return target
