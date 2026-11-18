"""Machine-local native Codex launch choices, outside research formats (L3).

Only a new session consumes a choice. AoE owns the resulting --extra-args and
keeps them for native resume/restart; a binding is never a permission editor.
"""

import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from toulmin.application.sources import ResolvedSource, filesystem_identity
from toulmin.core.atomic import write_atomic
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import validate_project_name
from toulmin.core.repository import Repository

LOCAL = "tools/native.local.toml"
MODES = ("workspace-write", "inherit")


@dataclass(frozen=True)
class LaunchPolicy:
    sandbox: str
    records_root: str
    records_identity: str
    source_id: str
    source_identity: str
    cwd: str
    cwd_identity: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str)
            or not value.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            for value in asdict(self).values()
        ):
            raise ValueError("policy fields must be nonempty strings without control characters")
        validate_mode(self.sandbox)
        for value in (self.cwd, self.records_root):
            if not Path(value).is_absolute() or ".." in Path(value).parts:
                raise ValueError("policy paths must be absolute without '..'")

    @classmethod
    def choice(cls, sandbox: str, root: Path, source: ResolvedSource) -> "LaunchPolicy":
        validate_mode(sandbox)
        return cls(
            sandbox,
            str(root),
            filesystem_identity(root),
            source.source_id,
            source.identity,
            str(source.path.resolve()),
            filesystem_identity(source.path),
        )

    def matches(self, root: Path, source: ResolvedSource) -> bool:
        return self == self.choice(self.sandbox, root, source)


def validate_mode(value: str) -> None:
    if value not in MODES:
        raise FormatError("--codex-sandbox: expected workspace-write or inherit")


def load(repository: Repository) -> dict[str, LaunchPolicy]:
    path = repository.path(LOCAL)
    if not path.exists():
        return {}
    repository.path(LOCAL, "file")
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError("configuration exceeds 1 MB")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if (
            set(data) != {"schema_version", "projects"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
            or not isinstance(data["projects"], dict)
        ):
            raise ValueError("expected schema_version = 1 and a projects table")
        result = {}
        fields = set(LaunchPolicy.__dataclass_fields__)
        for project, item in data["projects"].items():
            validate_project_name(project)
            if not isinstance(item, dict) or set(item) != fields:
                raise ValueError(f"invalid fields for project {project}")
            policy = LaunchPolicy(**item)
            result[project] = policy
        return result
    except (ValueError, UnicodeError) as error:
        raise FormatError(
            f"{path}: invalid native launch policy ({error}); inspect and correct the file. "
            "It has not been repaired or overwritten"
        ) from error


def save(repository: Repository, project: str, policy: LaunchPolicy) -> None:
    """Call under the workspace binding lock; preserve other projects' choices."""
    validate_project_name(project)
    policies = load(repository)
    policies[project] = policy
    lines = ["schema_version = 1", "", "[projects]"]
    for name, item in sorted(policies.items()):
        lines.extend(("", f"[projects.{json.dumps(name)}]"))
        lines.extend(
            f"{key} = {json.dumps(value, ensure_ascii=False)}"
            for key, value in asdict(item).items()
        )
    repository.path("tools", "directory")
    path = repository.path(LOCAL)
    write_atomic(path, ("\n".join(lines) + "\n").encode("utf-8"), replace=path.exists())
