"""Canonical identifiers shared by files, protocols and adapters."""

import re
from dataclasses import dataclass
from enum import StrEnum

SCHEMA_VERSION = 1


class ObjectKind(StrEnum):
    CLAIM = "claim"
    EVIDENCE = "evidence"
    OBJECTION = "objection"
    DECISION = "decision"
    EXPLORATION = "exploration"
    SPEC = "spec"
    RUN = "run"


PREFIXES = {
    ObjectKind.CLAIM: "C",
    ObjectKind.EVIDENCE: "E",
    ObjectKind.OBJECTION: "O",
    ObjectKind.DECISION: "D",
    ObjectKind.EXPLORATION: "X",
    ObjectKind.SPEC: "S",
    ObjectKind.RUN: "R",
}


def validate_project_name(name: str) -> str:
    """Accept a single portable, lowercase project directory name."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError(f"Invalid project name: {name!r}")
    return name


@dataclass(frozen=True)
class ObjectId:
    kind: ObjectKind
    number: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObjectKind):
            raise ValueError("Object kind must be an ObjectKind")
        if type(self.number) is not int or self.number < 1:
            raise ValueError("Object number must be a positive integer")

    def __str__(self) -> str:
        return f"{PREFIXES[self.kind]}-{self.number:03d}"

    @classmethod
    def parse(cls, value: str) -> "ObjectId":
        """Reject aliases such as C-1, C-0001 and IDs with path components."""
        match = re.fullmatch(r"([CEODXSR])-([0-9]{3,})", value)
        if match is None:
            raise ValueError(f"Invalid object ID: {value!r}")
        kind = next(kind for kind, prefix in PREFIXES.items() if prefix == match[1])
        result = cls(kind, int(match[2]))
        if str(result) != value:
            raise ValueError(f"Noncanonical object ID: {value!r}")
        return result


@dataclass(frozen=True)
class ObjectRef:
    object_id: ObjectId
    project: str | None = None

    def __post_init__(self) -> None:
        if self.project is not None:
            validate_project_name(self.project)

    def __str__(self) -> str:
        prefix = f"{self.project}/" if self.project is not None else ""
        return f"{prefix}{self.object_id}"

    @classmethod
    def parse(cls, value: str) -> "ObjectRef":
        if "/" not in value:
            return cls(ObjectId.parse(value))
        project, object_id = value.split("/", 1)
        return cls(ObjectId.parse(object_id), project)
