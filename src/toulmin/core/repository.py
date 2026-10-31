"""L1 file storage, path confinement, link validation and exclusive publication."""

import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath

from toulmin.core.codec import decode, encode
from toulmin.core.documents import DIRECTORIES, Document, FormatError
from toulmin.core.identifiers import ObjectId, ObjectKind, ObjectRef, validate_project_name
from toulmin.core.schema import validate


class Repository:
    def __init__(self, root: Path):
        if ".." in root.parts:
            raise FormatError(f"{root}: root: '..' is forbidden")
        self.root = root.absolute()
        for part in (*reversed(self.root.parents), self.root):
            if part.is_symlink():
                raise FormatError(f"{part}: root: directory symlinks forbidden")
        if not self.root.is_dir():
            raise FormatError(f"{self.root}: root: workbench directory does not exist")

    def path(self, value: str, expected: str | None = None) -> Path:
        if (
            not value
            or "\\" in value
            or ":" in value
            or any(ord(character) < 32 for character in value)
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise FormatError(f"{value}: path: expected portable root-relative path")
        relative = PurePosixPath(value)
        if relative.is_absolute():
            raise FormatError(f"{value}: path: absolute paths forbidden")
        result = self.root
        for part in relative.parts:
            result /= part
            if result.is_symlink():
                raise FormatError(f"{result}: path: symlinks forbidden")
        if expected == "file" and not result.is_file():
            raise FormatError(f"{result}: path: expected existing regular file")
        if expected == "directory" and not result.is_dir():
            raise FormatError(f"{result}: path: expected existing directory")
        return result

    def project(self, name: str) -> Path:
        validate_project_name(name)
        path = self.path(f"projects/{name}", "directory")
        charter = self.read(f"projects/{name}/PROJECT.md")
        if charter.header.get("project") != name:
            charter.fail("project", "charter name does not match project")
        if (
            type(charter.header.get("schema_version")) is not int
            or charter.header["schema_version"] != 1
        ):
            charter.fail("schema_version", "expected integer version 1")
        return path

    def read(self, relative: str) -> Document:
        path = self.path(relative, "file")
        return decode(path.read_bytes(), str(path))

    def load(self, project: str, object_id: ObjectId) -> Document:
        self.project(project)
        relative = f"projects/{project}/{DIRECTORIES[object_id.kind]}/{object_id}.md"
        doc = self.read(relative)
        validate(doc)
        if doc.object_id != object_id:
            doc.fail("id", "ID does not match filename or directory")
        return doc

    def resolve(self, project: str, value: str) -> tuple[Document, str]:
        ref = ObjectRef.parse(value)
        owner = ref.project or project
        return self.load(owner, ref.object_id), owner

    def _file(self, doc: Document, value: str, field: str, expected: str = "file") -> Path:
        try:
            return self.path(value, expected)
        except (OSError, ValueError) as error:
            doc.fail(field, str(error))

    def _run_paths(self, doc: Document, project: str) -> Path:
        output = self._file(doc, doc.header["output"], "output", "directory")
        archive = self.path(f"projects/{project}/runs", "directory")
        if output == archive or not output.is_relative_to(archive):
            doc.fail("output", "Run output must be a subdirectory of its project's runs/")
        if output.parent != archive or not re.fullmatch(
            r"\d{8}T\d{6}Z-[A-Za-z0-9][A-Za-z0-9_-]*", output.name
        ):
            doc.fail("output", "expected runs/YYYYMMDDTHHMMSSZ-name archive directory")
        try:
            datetime.strptime(output.name[:16], "%Y%m%dT%H%M%SZ")
        except ValueError as error:
            doc.fail("output", str(error))
        for index, value in enumerate(doc.header["input_files"]):
            self._file(doc, value, f"input_files[{index}]")
        return output

    def validate_links(self, doc: Document, project: str) -> None:
        """Check direct links, without recursive traversal through decision cycles."""
        h = doc.header
        links: list[tuple[str, str]] = []
        for field in ("target", "superseded_by", "adopted_as"):
            if field in h:
                links.append((field, h[field]))
        for field in ("related", "decisions", "evidence"):
            links.extend(
                (f"{field}[{index}]", value) for index, value in enumerate(h.get(field, []))
            )
        for field, value in links:
            try:
                self.resolve(project, value)
            except (OSError, ValueError) as error:
                doc.fail(field, str(error))
        if h["source"]["kind"] == "run":
            source = h["source"]
            try:
                run, owner = self.resolve(project, source["ref"])
            except (OSError, ValueError) as error:
                doc.fail("source.ref", str(error))
            output = self._run_paths(run, owner)
            original = self._file(doc, source["path"], "source.path")
            if not original.is_relative_to(output):
                doc.fail(
                    "source.path", "source file is outside the referenced Run's output directory"
                )
        if doc.object_id.kind == ObjectKind.RUN:
            self._run_paths(doc, project)
        if doc.object_id.kind == ObjectKind.EVIDENCE:
            for index, item in enumerate(h["provenance"]):
                if "path" in item:
                    self._file(doc, item["path"], f"provenance[{index}].path")
            if "verification" in h:
                for index, value in enumerate(h["verification"]["artifacts"]):
                    self._file(doc, value, f"verification.artifacts[{index}]")

    @contextmanager
    def creation_lock(self, project: str) -> Iterator[None]:
        directory = self.project(project)
        lock = directory / ".toulmin-new.lock"
        try:
            lock.mkdir()
        except FileExistsError as error:
            raise FormatError(
                f"{lock}: creation: another writer or interrupted creation holds the lock"
            ) from error
        try:
            yield
        finally:
            lock.rmdir()

    def next_id(self, project: str, kind: ObjectKind) -> ObjectId:
        directory = self.path(f"projects/{project}/{DIRECTORIES[kind]}", "directory")
        largest = 0
        for path in sorted(directory.glob("*.md")):
            try:
                object_id = ObjectId.parse(path.stem)
            except ValueError as error:
                raise FormatError(f"{path}: id: invalid object filename") from error
            if object_id.kind != kind:
                raise FormatError(f"{path}: id: wrong object directory")
            self.load(project, object_id)
            largest = max(largest, object_id.number)
        return ObjectId(kind, largest + 1)

    def publish(self, project: str, doc: Document) -> Path:
        self.project(project)
        validate(doc)
        self.validate_links(doc, project)
        relative = f"projects/{project}/{DIRECTORIES[doc.object_id.kind]}/{doc.object_id}.md"
        destination = self.path(relative)
        data = encode(doc)
        # Complete the file before atomically exposing it under the final name.
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".new-", suffix=".tmp"
        ) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            self.path(relative)
            os.link(stream.name, destination)
        return destination
