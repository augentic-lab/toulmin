"""Project creation, explicit setup recovery and read-only workspace inspection."""

import errno
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from toulmin.cli.initialize import _templates, initialize
from toulmin.core.atomic import digest, handoff_mutex, sync_directory, write_atomic
from toulmin.core.codec import encode
from toulmin.core.documents import Document, FormatError, sections
from toulmin.core.identifiers import ObjectKind, validate_project_name
from toulmin.core.inspection import inspect_project
from toulmin.core.repository import Repository
from toulmin.core.setup import IMAGES, SetupRecord, initial_documents, validate_setup
from toulmin.core.workspace import CHARTER_FILE


@dataclass(frozen=True)
class ProjectView:
    root: Path
    project: str
    goal: str
    motivation: str
    brief: str
    stage: str
    diagnostics: tuple[str, ...]
    last_handoff: str | None
    setup_pending: bool
    next_step: str = ""
    open_objections: tuple[str, ...] = ()


def _root(root: Path) -> Path:
    if ".." in root.parts:
        raise FormatError("Workbench root must not contain '..'")
    root = root.absolute()
    for path in (*reversed(root.parents), root):
        if path.is_symlink():
            raise FormatError(f"{path}: directory symlinks forbidden")
        if path.exists() and not path.is_dir():
            raise FormatError(f"{path}: expected directory")
    return root


def _setup(repository: Repository, project: str) -> tuple[SetupRecord, bytes]:
    prefix = f"projects/{project}/runs/setup"
    intent_path = repository.path(f"{prefix}/intent.md", "file")
    intent = repository.read(f"{prefix}/intent.md")
    images = {name: repository.path(f"{prefix}/{name}.md", "file").read_bytes() for name in IMAGES}
    record = validate_setup(intent, project, images)
    if record.source_file is not None:
        source = repository.path(f"{prefix}/{record.source_file}", "file").read_bytes()
        if digest(source) != intent.header["source_sha256"]:
            intent.fail("source_sha256", "imported source checksum mismatch; originals retained")
        try:
            source.decode("utf-8")
        except UnicodeDecodeError as error:
            intent.fail("source_file", f"expected UTF-8 source ({error})")
    return record, intent_path.read_bytes()


class WorkspaceService:
    """Keep mutation behind explicit operations; opening never initializes templates."""

    def list_projects(self, root: Path) -> list[str]:
        root = _root(root)
        if not root.exists():
            return []
        repository = Repository(root)
        folder = repository.path("projects")
        if not folder.exists():
            return []
        folder = repository.path("projects", "directory")
        names = []
        for path in sorted(folder.iterdir()):
            if path.is_symlink() or not path.is_dir():
                continue
            try:
                validate_project_name(path.name)
            except ValueError:
                continue
            names.append(path.name)
        return names

    def open_project(self, root: Path, project: str) -> ProjectView:
        validate_project_name(project)
        repository = Repository(_root(root))
        repository.path(f"projects/{project}", "directory")
        snapshot = inspect_project(repository, project)
        errors = list(snapshot.errors)
        goal, motivation, brief, stage = "", "", "", "unknown"
        last_handoff = None
        next_step = ""
        charter = snapshot.charter
        if charter is not None:
            goal = sections(charter).get("Goal", "").strip()
            stage = charter.header["stage"]
            last_handoff = charter.header["last_handoff"]
            next_step = charter.header["next_step"]
        try:
            path = repository.path(f"projects/{project}/brief.md", "file")
            brief = path.read_bytes().decode("utf-8")
            motivation = sections(Document({}, brief)).get("Problem", "").strip()
            lines = motivation.split("\n")
            if lines and all(line == ">" or line.startswith("> ") for line in lines):
                motivation = "\n".join(line[2:] if line.startswith("> ") else "" for line in lines)
        except (OSError, ValueError) as error:
            errors.append(str(error))
        pending = False
        try:
            runs = repository.path(f"projects/{project}/runs")
            if runs.is_dir() and any(runs.glob(".setup-*")):
                pending = True
                errors.append(
                    f"{runs}: setup input preparation interrupted; inspect .setup-* archives "
                    "and preserve originals before retrying with a new project slug"
                )
            setup = repository.path(f"projects/{project}/runs/setup")
            if setup.exists():
                pending = True
                record, intent = _setup(repository, project)
                complete = repository.path(f"projects/{project}/runs/setup/complete")
                if complete.exists():
                    if complete.read_bytes() != (digest(intent) + "\n").encode():
                        raise FormatError(f"{complete}: setup completion checksum mismatch")
                    pending = False
                else:
                    goal = record.goal
                    motivation = record.motivation
                    errors.append(f"{setup}: setup incomplete; use Resume Setup")
        except (OSError, ValueError) as error:
            errors.append(str(error))
        return ProjectView(
            repository.root,
            project,
            goal,
            motivation,
            brief,
            stage,
            tuple(sorted(set(errors))),
            last_handoff,
            pending,
            next_step,
            tuple(
                str(document.object_id)
                for document in snapshot.objects
                if document.object_id.kind == ObjectKind.OBJECTION
                and document.header["status"] in {"open", "answered"}
            ),
        )

    def create_project(
        self,
        root: Path,
        project: str,
        goal: str,
        motivation: str,
        source_path: Path | None = None,
        *,
        expected_source_sha256: str | None = None,
    ) -> ProjectView:
        validate_project_name(project)
        root = _root(root)
        templates = _templates(project)
        relative = Path("projects") / project
        images = initial_documents(
            project,
            goal,
            motivation,
            templates[relative / "PROJECT.md"],
            templates[relative / "brief.md"],
        )
        source = None
        source_file = None
        source_name = None
        if source_path is not None:
            suffix = source_path.suffix.lower()
            if suffix not in {".md", ".txt"}:
                raise FormatError("Import supports UTF-8 .md and .txt files only")
            if not source_path.is_file():
                raise FormatError(f"{source_path}: expected regular source file")
            source = source_path.read_bytes()
            if expected_source_sha256 is not None and digest(source) != expected_source_sha256:
                raise FormatError(f"{source_path}: source changed since preview; import it again")
            try:
                source.decode("utf-8")
            except UnicodeDecodeError as error:
                raise FormatError(f"{source_path}: expected UTF-8 source") from error
            source_file = "source" + suffix
            source_name = source_path.name
        record = SetupRecord(project, goal, motivation, source_name, source_file, images, source)
        validate_setup(record.document(), project, images)
        # The root lock also serializes shared-template initialization across projects.
        with handoff_mutex(root):
            if os.path.lexists(root / CHARTER_FILE):
                # Workspace children come from reviewed creation, never template setup.
                raise FormatError(
                    "This is a workspace root; template project setup is refused here. "
                    "Children are added by reviewed creation (toulmin project propose/create)"
                )
            root.mkdir(parents=True, exist_ok=True)
            repository = Repository(root)
            directory = repository.path(f"projects/{project}")
            projects = repository.path("projects")
            projects.mkdir(exist_ok=True)
            directory.mkdir()  # Exclusive ownership; never adopt an existing project.
            runs = repository.path(f"projects/{project}/runs")
            runs.mkdir()
            setup = repository.path(f"projects/{project}/runs/setup")
            published = False
            try:
                with tempfile.TemporaryDirectory(prefix=".setup-", dir=runs) as temporary:
                    staging = Path(temporary)
                    for name in IMAGES:
                        write_atomic(staging / f"{name}.md", images[name])
                    if source_file is not None and source is not None:
                        write_atomic(staging / source_file, source)
                    write_atomic(staging / "intent.md", encode(record.document()))
                    # No scaffold exists until this complete input bundle is published.
                    if setup.exists() or setup.is_symlink():
                        raise FormatError(f"{setup}: setup archive already exists")
                    os.rename(staging, setup)
                    published = True
                    sync_directory(runs)
            finally:
                if not published:
                    # Remove only our empty containers; preserve concurrent additions.
                    for empty in (runs, directory):
                        try:
                            empty.rmdir()
                        except OSError as error:
                            if error.errno not in {errno.ENOTEMPTY, errno.EEXIST, errno.ENOENT}:
                                raise
            self._finish_setup(repository, project)
        return self.open_project(root, project)

    def resume_setup(self, root: Path, project: str) -> ProjectView:
        validate_project_name(project)
        root = _root(root)
        with handoff_mutex(root):
            repository = Repository(root)
            self._finish_setup(repository, project)
        return self.open_project(root, project)

    def _finish_setup(self, repository: Repository, project: str) -> None:
        record, intent = _setup(repository, project)
        prefix = f"projects/{project}/runs/setup"
        complete = repository.path(f"{prefix}/complete")
        checksum = (digest(intent) + "\n").encode()
        if complete.exists():
            if complete.read_bytes() != checksum:
                raise FormatError(f"{complete}: setup completion checksum mismatch")
            return
        ready = repository.path(f"{prefix}/scaffold-ready")
        if not ready.exists():
            initialize(repository.root, project)
            write_atomic(ready, b"1\n")
        elif ready.read_bytes() != b"1\n":
            raise FormatError(f"{ready}: invalid setup scaffold marker")
        targets = (
            (f"projects/{project}/PROJECT.md", "project"),
            (f"projects/{project}/brief.md", "brief"),
        )
        # Check every target before the first mutation; recovery may find either image.
        for relative, name in targets:
            current = repository.path(relative, "file").read_bytes()
            if current not in {record.images[f"{name}-before"], record.images[f"{name}-after"]}:
                raise FormatError(f"{relative}: changed since setup; refusing overwrite")
        for relative, name in targets:
            target = repository.path(relative, "file")
            current = target.read_bytes()
            if current == record.images[f"{name}-before"]:
                write_atomic(target, record.images[f"{name}-after"], replace=True)
            elif current != record.images[f"{name}-after"]:
                raise FormatError(f"{relative}: changed during setup; refusing overwrite")
        write_atomic(complete, checksum)
