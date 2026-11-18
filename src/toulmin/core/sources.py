"""Additive source catalog and machine-local bindings, independent of Git/CLIs.

The tracked catalog contains logical identities only. Absolute paths and filesystem
identities belong exclusively to tools/sources.local.toml.
"""

import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from toulmin.core.atomic import digest
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import validate_project_name
from toulmin.core.repository import Repository
from toulmin.core.scope import Scope

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


def parse_catalog_v1(data: bytes) -> tuple[Source, ...]:
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
    parse_catalog_v1(data)
    return data


def read_catalog(root: Path) -> tuple[Source, ...]:
    catalog = read_source_catalog(root)
    return catalog.project_sources()


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


@dataclass(frozen=True)
class SourceDefinition:
    id: str
    definition_revision: int
    kind: str
    identity_method: str
    identity: str

    @property
    def sha256(self) -> str:
        data = json.dumps(asdict(self), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return digest((data + "\n").encode())


@dataclass(frozen=True)
class SourceAssociation:
    scope: Scope
    source: str
    role: str


@dataclass(frozen=True)
class SourceCatalog:
    schema_version: int
    definitions: tuple[SourceDefinition, ...]
    associations: tuple[SourceAssociation, ...]

    def definition(self, source: str) -> SourceDefinition:
        for definition in self.definitions:
            if definition.id == source:
                return definition
        raise FormatError(f"{CATALOG}: {source}: no such source definition")

    def associated(self, scope: Scope) -> tuple[SourceAssociation, ...]:
        return tuple(item for item in self.associations if item.scope == scope)

    def project_sources(self) -> tuple[Source, ...]:
        result = []
        for association in self.associations:
            if association.scope.project is not None:
                definition = self.definition(association.source)
                result.append(
                    Source(
                        definition.id,
                        association.scope.project,
                        definition.kind,
                        association.role,
                        definition.identity,
                    )
                )
        return tuple(result)


def parse_source_catalog(data: bytes) -> SourceCatalog:
    """Strict version dispatch. V1's in-memory view never invents workspace roles."""
    try:
        value = tomllib.loads(data.decode("utf-8"))
        version = value.get("schema_version")
        if type(version) is not int:
            raise ValueError("schema_version must be an integer")
        if version == 1:
            old = parse_catalog_v1(data)
            definitions = {
                s.source_id: SourceDefinition(
                    s.source_id,
                    1,
                    s.kind,
                    "git-roots-v1" if s.kind == "git" else "directory-anchors-v1",
                    s.identity,
                )
                for s in old
            }
            return SourceCatalog(
                1,
                tuple(definitions.values()),
                tuple(SourceAssociation(Scope(s.project), s.source_id, s.role) for s in old),
            )
        if version != 2 or set(value) != {"schema_version", "definitions", "associations"}:
            raise ValueError("expected catalog version 1 or 2 with exact fields")
        if not isinstance(value["definitions"], list) or not isinstance(
            value["associations"], list
        ):
            raise ValueError("definitions and associations must be arrays")
        parsed_definitions = []
        ids = set()
        for item in value["definitions"]:
            if not isinstance(item, dict) or set(item) != set(
                SourceDefinition.__dataclass_fields__
            ):
                raise ValueError("invalid definition fields")
            if (
                not isinstance(item["id"], str)
                or not SOURCE_ID.fullmatch(item["id"])
                or item["id"] in ids
            ):
                raise ValueError("invalid or duplicate source ID")
            kind = item["kind"]
            if (
                type(item["definition_revision"]) is not int
                or item["definition_revision"] != 1
                or kind not in {"git", "directory"}
                or item["identity_method"]
                != ("git-roots-v1" if kind == "git" else "directory-anchors-v1")
                or not isinstance(item["identity"], str)
                or not re.fullmatch(kind + r":[0-9a-f]{64}", item["identity"])
            ):
                raise ValueError("invalid definition revision, kind, identity method or identity")
            ids.add(item["id"])
            parsed_definitions.append(SourceDefinition(**item))
        parsed_associations = []
        pairs = set()
        working = set()
        owned = set()
        for item in value["associations"]:
            if not isinstance(item, dict) or set(item) != {"scope", "source", "role"}:
                raise ValueError("invalid association fields")
            scope = Scope.from_data(item["scope"])
            source = item["source"]
            if not isinstance(source, str) or source not in ids:
                raise ValueError("association names a missing definition")
            if item["role"] not in {"reference", "working"}:
                raise ValueError("invalid association role")
            pair = (scope, source)
            if pair in pairs:
                raise ValueError("duplicate scope/source association")
            pairs.add(pair)
            if item["role"] == "working":
                if scope in working:
                    raise ValueError("at most one working source per scope")
                working.add(scope)
            if scope.project is None:
                owned.add(source)
            parsed_associations.append(SourceAssociation(scope, source, item["role"]))
        if owned != ids:
            raise ValueError("every definition requires a workspace association")
        return SourceCatalog(2, tuple(parsed_definitions), tuple(parsed_associations))
    except (ValueError, TypeError, KeyError) as error:
        raise FormatError(
            f"{CATALOG}: {error}; inspect the catalog, no repair performed"
        ) from error


def parse_catalog(data: bytes) -> tuple[Source, ...]:
    """Compatibility project-association view, including new v2 project roles."""
    return parse_source_catalog(data).project_sources()


def render_source_catalog(catalog: SourceCatalog) -> bytes:
    if catalog.schema_version == 1:
        return render_catalog(catalog.project_sources())
    lines = ["schema_version = 2", ""]
    if not catalog.definitions:
        lines.append("definitions = []")
    if not catalog.associations:
        lines.append("associations = []")
    for definition in sorted(catalog.definitions, key=lambda item: item.id):
        lines.extend(("", "[[definitions]]"))
        lines.extend(f"{key} = {json.dumps(value)}" for key, value in asdict(definition).items())
    for association in sorted(
        catalog.associations, key=lambda a: (a.scope.kind, a.scope.project or "", a.source)
    ):
        scope = ", ".join(f"{k} = {json.dumps(v)}" for k, v in association.scope.to_data().items())
        lines.extend(
            (
                "",
                "[[associations]]",
                f"scope = {{ {scope} }}",
                f"source = {json.dumps(association.source)}",
                f"role = {json.dumps(association.role)}",
            )
        )
    data = ("\n".join(lines) + "\n").encode()
    parse_source_catalog(data)
    return data


def read_source_catalog(root: Path, staged: str | None = None) -> SourceCatalog:
    repository = Repository(root)
    path = repository.path(CATALOG)
    catalog = parse_source_catalog(path.read_bytes()) if path.exists() else SourceCatalog(2, (), ())
    if catalog.schema_version == 2:
        for association in catalog.associations:
            project = association.scope.project
            if project is not None and project != staged:
                try:
                    from toulmin.core.project import validate_project

                    repository.project(project)
                    validate_project(repository.read(f"projects/{project}/PROJECT.md"), project)
                except (OSError, ValueError) as error:
                    raise FormatError(
                        f"{CATALOG}: association names unhealthy child {project}: {error}"
                    ) from error
    return catalog
