"""L1 role input manifests, with no filesystem access.

A role file (``roles/<role>.md``) may start with a YAML header naming the files an
independent session of that role receives. Paths are root-relative patterns in which
``{project}`` is the only placeholder and ``*``/``?``/``[...]`` may appear in the last
component. Independent roles never receive discussion history: every pattern must fall
inside the allowlist below, so sessions, handoffs, Runs, Decisions, PROJECT.md,
other projects and calibration reports cannot be named.
"""

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

from toulmin.core.codec import decode
from toulmin.core.documents import Document
from toulmin.core.schema import mapping, strings, text

OPERATIONS = ("critique", "synthesize")
ROLE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PLACEHOLDER = "{project}"
GLOB = re.compile(r"[*?\[]")
# Patterns a manifest may name, after {project} is substituted. Anything else is refused.
ALLOWED = (
    "AGENTS.md",
    "roles/*.md",
    "framework/*.md",
    "global/papers/*",
    "global/assumptions/*",
    "projects/{project}/brief.md",
    "projects/{project}/claims/*.md",
)


@dataclass(frozen=True)
class RoleManifest:
    role: str
    operation: str
    inputs: tuple[str, ...]


def has_manifest(data: bytes) -> bool:
    return data.startswith(b"---\n")


def parse_manifest(data: bytes, location: str, role: str) -> RoleManifest:
    """Parse and validate the header of ``roles/<role>.md``."""
    document = decode(data, location)
    header = mapping(
        document, document.header, "", {"schema_version", "role", "operation", "inputs"}
    )
    if type(header["schema_version"]) is not int or header["schema_version"] != 1:
        document.fail("schema_version", "expected integer version 1")
    name = text(document, header["role"], "role")
    if name != role or not ROLE_NAME.fullmatch(name):
        document.fail("role", f"expected {role}, matching the filename")
    if header["operation"] not in OPERATIONS:
        document.fail("operation", f"expected one of {OPERATIONS}")
    inputs = strings(document, header["inputs"], "inputs", nonempty=True)
    for index, pattern in enumerate(inputs):
        _check_pattern(document, pattern, f"inputs[{index}]")
    if len(set(inputs)) != len(inputs):
        document.fail("inputs", "duplicate pattern")
    if f"roles/{role}.md" not in inputs:
        document.fail("inputs", f"must include the role file roles/{role}.md")
    return RoleManifest(name, header["operation"], tuple(inputs))


def _check_pattern(document: Document, pattern: str, field: str) -> None:
    probe = pattern.replace(PLACEHOLDER, "p")
    if "{" in probe or "}" in probe:
        document.fail(field, f"only the {PLACEHOLDER} placeholder is allowed")
    parts = PurePosixPath(probe).parts
    if (
        probe.startswith("/")
        or "\\" in probe
        or any(part in {".", ".."} for part in parts)
        or "//" in probe
    ):
        document.fail(field, "expected a portable root-relative path")
    if any(GLOB.search(part) for part in parts[:-1]):
        document.fail(field, "wildcards are allowed only in the last path component")
    if not allowed(pattern):
        document.fail(field, f"{pattern} is outside the inputs an independent role may receive")


def allowed(pattern: str) -> bool:
    """True when every path the pattern can match lies inside the allowlist.

    The project placeholder must stay a placeholder, so a manifest cannot name another
    project; a wildcard last component is allowed only where the allowlist itself has one.
    """
    head, _, last = pattern.rpartition("/")
    for permitted in ALLOWED:
        permitted_head, _, permitted_last = permitted.rpartition("/")
        if head != permitted_head:
            continue
        if GLOB.search(last):
            if last == permitted_last or (
                GLOB.search(permitted_last) and _narrower(last, permitted_last)
            ):
                return True
        elif fnmatchcase(last, permitted_last):
            return True
    return False


def _narrower(pattern: str, permitted: str) -> bool:
    # Conservative: a wildcard pattern is accepted only if it keeps the permitted suffix
    # (for example C-*.md under *.md); anything cleverer is refused rather than reasoned about.
    suffix = permitted.lstrip("*")
    return permitted.startswith("*") and not GLOB.search(suffix) and pattern.endswith(suffix)


def expand(pattern: str, project: str) -> str:
    return pattern.replace(PLACEHOLDER, project)


def natural_key(path: str) -> list[object]:
    """Sort C-2 before C-10 and C-999 before C-1000."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path)]


def is_glob(pattern: str) -> bool:
    return bool(GLOB.search(pattern))
