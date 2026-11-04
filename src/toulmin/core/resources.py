"""L1 schema for shared resource descriptions (docs/workspace-formats.md, section 6).

A description registers located, versioned material for reuse. It is a confirmed
description, never Evidence, and it supports or upgrades no Claim.
"""

import re
from dataclasses import dataclass
from typing import Any

from toulmin.core.documents import DIRECTORIES, Document, sections, validate_values
from toulmin.core.identifiers import validate_project_name
from toulmin.core.render import header
from toulmin.core.schema import mapping, text
from toulmin.core.workspace import RECEIPT

KINDS = ("data", "code", "document", "other")
STATUSES = ("active", "withdrawn")
METHODS = ("file", "tree-v1", "external")
HEX = re.compile(r"[0-9a-f]{64}")
RESOURCE_ORDER = (
    "schema_version",
    "resource",
    "title",
    "status",
    "kind",
    "location",
    "version",
    "origin",
    "revision",
    "previous_sha256",
    "receipt",
)
# Fields a change input may supply (section 7.1); the rest are generated.
CHANGE_FIELDS = ("title", "status", "kind", "location", "version", "origin")
BODY_FIELDS = ("purpose", "limitations", "notes")
BODY = {"Purpose": "purpose", "Limitations": "limitations", "Notes": "notes"}
FORMAL = set(DIRECTORIES.values())


@dataclass(frozen=True)
class Description:
    resource: str
    title: str
    status: str
    kind: str
    path: str | None
    url: str | None
    method: str
    sha256: str | None
    version_revision: str | None
    origin: str
    revision: int
    previous_sha256: str | None
    receipt: str
    purpose: str
    limitations: str
    notes: str | None

    def fields(self) -> dict[str, Any]:
        """The values a revision copies when a change omits them."""
        return {
            "title": self.title,
            "status": self.status,
            "kind": self.kind,
            "location": {"path": self.path, "url": self.url},
            "version": {
                "method": self.method,
                "sha256": self.sha256,
                "revision": self.version_revision,
            },
            "origin": self.origin,
            "purpose": self.purpose,
            "limitations": self.limitations,
            "notes": self.notes,
        }


def resource_path(name: str) -> str:
    validate_project_name(name)
    return f"shared/resources/{name}.md"


def check_location_path(value: str) -> None:
    """Refuse locations that are records, journals or formal research objects."""
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or value.startswith("/") or ":" in value:
        raise ValueError("expected a portable root-relative path")
    if parts[0] in {"sessions", ".git"} or parts[0].startswith(".workspace-"):
        raise ValueError(f"{parts[0]}/ cannot hold shared material")
    if parts[:2] == ["shared", "resources"] or ".aoe" in parts:
        raise ValueError("descriptions and bindings are not material")
    if parts[0] == "projects" and len(parts) > 2 and parts[2] in FORMAL:
        raise ValueError("formal object directories are referenced by Evidence, not resources")


def validate_location(document: Document, value: Any, field: str) -> tuple[str | None, str | None]:
    location = mapping(document, value, field, {"path", "url"})
    path, url = location["path"], location["url"]
    if (path is None) == (url is None):
        document.fail(field, "exactly one of path or url")
    if path is not None:
        text(document, path, f"{field}.path")
        try:
            check_location_path(path)
        except ValueError as error:
            document.fail(f"{field}.path", str(error))
    if url is not None and (not isinstance(url, str) or not re.fullmatch(r"https?://\S+", url)):
        document.fail(f"{field}.url", "expected http or https URL")
    return path, url


def validate_version(
    document: Document, value: Any, field: str, path: str | None
) -> tuple[str, str | None, str | None]:
    version = mapping(document, value, field, {"method", "sha256", "revision"})
    method, sha256, revision = version["method"], version["sha256"], version["revision"]
    if method not in METHODS:
        document.fail(f"{field}.method", f"expected one of {', '.join(METHODS)}")
    if sha256 is not None and not (isinstance(sha256, str) and HEX.fullmatch(sha256)):
        document.fail(f"{field}.sha256", "expected SHA-256 hex digest or null")
    if revision is not None:
        text(document, revision, f"{field}.revision")
    if path is not None:
        if method == "external":
            document.fail(f"{field}.method", "a path location uses file or tree-v1")
        if sha256 is None:
            document.fail(f"{field}.sha256", "required for a path location")
    else:
        if method != "external":
            document.fail(f"{field}.method", "a url location uses external")
        if sha256 is None and revision is None:
            document.fail(field, "external material needs sha256 or revision")
    return method, sha256, revision


def validate_description(document: Document, name: str) -> Description:
    validate_values(document)
    h = mapping(document, document.header, "", set(RESOURCE_ORDER))
    if type(h["schema_version"]) is not int or h["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    if h["resource"] != name:
        document.fail("resource", "must equal the filename stem")
    title = text(document, h["title"], "title")
    if h["status"] not in STATUSES:
        document.fail("status", "expected active or withdrawn")
    if h["kind"] not in KINDS:
        document.fail("kind", f"expected one of {', '.join(KINDS)}")
    path, url = validate_location(document, h["location"], "location")
    method, sha256, version_revision = validate_version(document, h["version"], "version", path)
    origin = text(document, h["origin"], "origin")
    revision = h["revision"]
    if type(revision) is not int or revision < 1:
        document.fail("revision", "expected integer >= 1")
    previous = h["previous_sha256"]
    if revision == 1 and previous is not None:
        document.fail("previous_sha256", "must be null at revision 1")
    if revision > 1 and not (isinstance(previous, str) and HEX.fullmatch(previous)):
        document.fail("previous_sha256", "expected the previous description's SHA-256")
    if not isinstance(h["receipt"], str) or not RECEIPT.fullmatch(h["receipt"]):
        document.fail("receipt", "expected runs/<stamp>-proposal-<hex>/receipt.md")
    body = sections(document)
    for heading, content in body.items():
        if heading not in BODY:
            document.fail(f"body.{heading}", "expected Purpose, Limitations or Notes")
        if not content.strip():
            document.fail(f"body.{heading}", "required content empty")
    for heading in ("Purpose", "Limitations"):
        if heading not in body:
            document.fail(f"body.{heading}", "required section missing")
    return Description(
        name,
        title,
        h["status"],
        h["kind"],
        path,
        url,
        method,
        sha256,
        version_revision,
        origin,
        revision,
        previous,
        h["receipt"],
        body["Purpose"].strip(),
        body["Limitations"].strip(),
        body["Notes"].strip() if "Notes" in body else None,
    )


def render_description(
    name: str, values: dict[str, Any], revision: int, previous: str | None, receipt: str
) -> bytes:
    fields: list[tuple[str, Any]] = [("schema_version", 1), ("resource", name)]
    fields += [(key, values[key]) for key in CHANGE_FIELDS]
    fields += [("revision", revision), ("previous_sha256", previous), ("receipt", receipt)]
    body = f"## Purpose\n{values['purpose'].strip()}\n\n## Limitations\n"
    body += f"{values['limitations'].strip()}\n"
    if values.get("notes") is not None:
        body += f"\n## Notes\n{values['notes'].strip()}\n"
    return (header(fields) + body).encode()
