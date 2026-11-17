"""Additive source catalog and machine-local bindings, independent of Git/CLIs.

The tracked catalog contains logical identities only. Absolute paths and filesystem
identities belong exclusively to tools/sources.local.toml.
"""

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from toulmin.core.documents import FormatError
from toulmin.core.identifiers import validate_project_name
from toulmin.core.repository import Repository

CATALOG = "sources.toml"
LOCAL = "tools/sources.local.toml"
SOURCE_ID = re.compile(r"[a-z][a-z0-9-]{0,79}")


@dataclass(frozen=True)
class Source:
    source_id: str
    project: str
    kind: str
    role: str
    identity: str


def parse_catalog(data: bytes) -> tuple[Source, ...]:
    try:
        value = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise FormatError(f"{CATALOG}: invalid TOML: {error}") from error
    if (
        set(value) != {"schema_version", "sources"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise FormatError(f"{CATALOG}: expected schema_version = 1 and sources")
    result = []
    if not isinstance(value["sources"], list):
        raise FormatError(f"{CATALOG}: sources must be an array of tables")
    for item in value["sources"]:
        if not isinstance(item, dict) or set(item) != {"id", "project", "kind", "role", "identity"}:
            raise FormatError(f"{CATALOG}: invalid source fields")
        if any(not isinstance(v, str) or not v.strip() for v in item.values()):
            raise FormatError(f"{CATALOG}: source fields must be nonempty strings")
        if not SOURCE_ID.fullmatch(item["id"]):
            raise FormatError(f"{CATALOG}: invalid source ID {item['id']!r}")
        validate_project_name(item["project"])
        if item["kind"] not in {"git", "directory"} or item["role"] not in {"working", "reference"}:
            raise FormatError(f"{CATALOG}: unsupported source kind or role")
        result.append(
            Source(item["id"], item["project"], item["kind"], item["role"], item["identity"])
        )
    if len({(s.source_id, s.project) for s in result}) != len(result):
        raise FormatError(f"{CATALOG}: duplicate source/project associations")
    identities: dict[str, tuple[str, str]] = {}
    for source in result:
        identity = (source.kind, source.identity)
        if source.source_id in identities and identities[source.source_id] != identity:
            raise FormatError(f"{CATALOG}: same source ID must keep its kind and identity")
        identities[source.source_id] = identity
    working = [s.project for s in result if s.role == "working"]
    if len(set(working)) != len(working):
        raise FormatError(f"{CATALOG}: at most one working source per project")
    return tuple(result)


def render_catalog(sources: tuple[Source, ...]) -> bytes:
    lines = ["schema_version = 1", ""]
    if not sources:
        lines.append("sources = []")
    for source in sources:
        lines.extend(
            [
                "[[sources]]",
                *(
                    f"{key} = {json.dumps(value)}"
                    for key, value in (
                        ("id", source.source_id),
                        ("project", source.project),
                        ("kind", source.kind),
                        ("role", source.role),
                        ("identity", source.identity),
                    )
                ),
                "",
            ]
        )
    data = ("\n".join(lines) + "\n").encode()
    parse_catalog(data)
    return data


def read_catalog(root: Path) -> tuple[Source, ...]:
    path = Repository(root).path(CATALOG)
    return parse_catalog(path.read_bytes()) if path.exists() else ()


def parse_bindings(data: bytes) -> dict[str, tuple[str, str]]:
    try:
        value = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise FormatError(f"{LOCAL}: invalid TOML: {error}") from error
    if (
        set(value) != {"schema_version", "bindings"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise FormatError(f"{LOCAL}: invalid local bindings")
    result = {}
    if not isinstance(value["bindings"], dict):
        raise FormatError(f"{LOCAL}: bindings must be tables")
    for source_id, item in value["bindings"].items():
        if (
            not SOURCE_ID.fullmatch(source_id)
            or not isinstance(item, dict)
            or set(item) != {"path", "filesystem"}
        ):
            raise FormatError(f"{LOCAL}: invalid binding")
        if (
            any(not isinstance(v, str) or not v for v in item.values())
            or not Path(item["path"]).is_absolute()
        ):
            raise FormatError(f"{LOCAL}: absolute path and filesystem identity required")
        result[source_id] = (item["path"], item["filesystem"])
    return result


def render_bindings(bindings: dict[str, tuple[str, str]]) -> bytes:
    lines = ["schema_version = 1", "", "[bindings]", ""]
    for source_id, (path, identity) in sorted(bindings.items()):
        lines.extend(
            [
                f"[bindings.{source_id}]",
                f"path = {json.dumps(path)}",
                f"filesystem = {json.dumps(identity)}",
                "",
            ]
        )
    data = ("\n".join(lines) + "\n").encode()
    parse_bindings(data)
    return data
