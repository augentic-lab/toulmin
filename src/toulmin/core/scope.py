"""L1 research scope: the shared workspace or one named child project.

The serialized form mirrors ``source``: ``{kind: workspace}`` or
``{kind: project, project: NAME}`` (docs/workspace-formats.md, section 2).
"""

from dataclasses import dataclass
from typing import Any

from toulmin.core.identifiers import validate_project_name


@dataclass(frozen=True)
class Scope:
    project: str | None = None

    def __post_init__(self) -> None:
        if self.project is not None:
            validate_project_name(self.project)

    @property
    def kind(self) -> str:
        return "workspace" if self.project is None else "project"

    @property
    def display(self) -> str:
        return "Workspace" if self.project is None else f"Project: {self.project}"

    def records(self, name: str) -> str:
        """Root-relative location of this scope's ``runs`` or ``sessions`` directory."""
        if name not in {"runs", "sessions"}:
            raise ValueError(f"{name}: expected runs or sessions")
        return name if self.project is None else f"projects/{self.project}/{name}"

    def to_data(self) -> dict[str, str]:
        if self.project is None:
            return {"kind": "workspace"}
        return {"kind": "project", "project": self.project}

    @classmethod
    def from_data(cls, value: Any) -> "Scope":
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError("scope: expected mapping with kind")
        if value == {"kind": "workspace"}:
            return cls()
        if set(value) == {"kind", "project"} and value["kind"] == "project":
            if not isinstance(value["project"], str):
                raise ValueError("scope.project: expected project name")
            return cls(value["project"])
        raise ValueError("scope: expected {kind: workspace} or {kind: project, project: NAME}")


WORKSPACE = Scope()
