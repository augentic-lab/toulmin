"""L2: resolve a role's input manifest to the exact files one session receives.

Independent sessions (critique, synthesis) must start from the same files and nothing
else. The manifest's allowlist (L1) keeps discussion history out; this module expands
the patterns for one project, drops superseded Claims, and applies an optional Claim
selection, so a Run's ``input_files`` is computed rather than retyped.
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from toulmin.core.documents import DIRECTORIES, FormatError
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef
from toulmin.core.repository import Repository
from toulmin.core.roles import (
    ROLE_NAME,
    expand,
    has_manifest,
    is_glob,
    natural_key,
    parse_manifest,
)


@dataclass(frozen=True)
class RoleInputs:
    role: str
    operation: str
    files: tuple[str, ...]
    superseded: tuple[str, ...]  # Claims left out because a successor replaces them


def resolve_inputs(
    root: Path, project: str, role: str, claims: list[str] | None = None
) -> RoleInputs:
    """Return the root-relative files a session of `role` receives for `project`.

    `claims` restricts the project's Claims to the selected IDs; each must be a current
    Claim that the manifest would otherwise include.
    """
    repository = Repository(root)
    repository.project(project)
    if not ROLE_NAME.fullmatch(role):
        raise FormatError(f"{role}: role: expected lowercase letters, digits and hyphens")
    role_path = repository.path(f"roles/{role}.md", "file")
    data = role_path.read_bytes()
    if not has_manifest(data):
        raise FormatError(f"{role_path}: role: no input manifest; this role is not independent")
    manifest = parse_manifest(data, str(role_path), role)
    selected = _selection(project, claims)

    claim_folder = f"projects/{project}/{DIRECTORIES[ObjectKind.CLAIM]}/"
    files: list[str] = []
    superseded: list[str] = []
    for pattern in manifest.inputs:
        for path in _matches(repository, expand(pattern, project)):
            if path in files:
                continue
            if path.startswith(claim_folder):
                claim = repository.load(project, ObjectId.parse(Path(path).stem))
                if selected is not None and str(claim.object_id) not in selected:
                    continue
                if claim.header["status"] == "superseded":
                    if selected is not None:
                        raise FormatError(
                            f"{claim.object_id}: claim: superseded by "
                            f"{claim.header['superseded_by']}; select the current Claim"
                        )
                    superseded.append(str(claim.object_id))
                    continue
            files.append(path)
    if selected is not None:
        found = {Path(path).stem for path in files if path.startswith(claim_folder)}
        for claim_id in sorted(selected - found):
            raise FormatError(
                f"{claim_id}: claim: not among the inputs of role {role} in project {project}"
            )
    return RoleInputs(manifest.role, manifest.operation, tuple(files), tuple(superseded))


def _selection(project: str, claims: list[str] | None) -> set[str] | None:
    if claims is None:
        return None
    selected: set[str] = set()
    for value in claims:
        try:
            reference = ObjectRef.parse(value)
        except ValueError as error:
            raise FormatError(f"{value}: claim: {error}") from error
        if reference.object_id.kind != ObjectKind.CLAIM:
            raise FormatError(f"{value}: claim: expected a Claim ID")
        if reference.project not in {None, project}:
            raise FormatError(f"{value}: claim: expected a Claim in project {project}")
        selected.add(str(reference.object_id))
    if not selected:
        raise FormatError("claim: an explicit selection needs at least one Claim")
    return selected


def _matches(repository: Repository, pattern: str) -> list[str]:
    if not is_glob(pattern):
        repository.path(pattern, "file")
        return [pattern]
    head, _, last = pattern.rpartition("/")
    folder = repository.path(head, "directory")
    found = []
    for entry in folder.iterdir():
        if entry.name.startswith(".") or not fnmatchcase(entry.name, last):
            continue
        relative = f"{head}/{entry.name}"
        repository.path(relative, "file")  # regular file, no symlink
        found.append(relative)
    return sorted(found, key=natural_key)
