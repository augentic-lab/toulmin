"""Independent contract fixtures, CLI driver and fake native/Chief boundaries.

These helpers deliberately serialize fixtures independently of production v2 writers.
They never invoke a subscribed CLI, Chief worker, source script or network service.
"""

import hashlib
import json
import subprocess
import tomllib
from dataclasses import replace

from typer.testing import CliRunner

from toulmin.adapters.aoe import AoEClient, AoEError, AoESession
from toulmin.application.sources import filesystem_identity, inspect_source
from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core.codec import decode, encode

WS = {"kind": "workspace"}
ACTOR = "Delegated fixture operator (not researcher acceptance)"
OVERVIEW = """## Structure
source-main:main.py contains a tiny fixture service at the observed revision.
## Entry points
source-main:main.py is the only observed entry point.
## Current behavior
The selected text prints a baseline; runtime behavior has not been established.
## Checks
No source scripts or tests executed during intake.
## Known gaps
Latency and deployment requirements are unknown.
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def definition_sha(value):
    return sha((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())


def tree(root):
    """Bytes and empty directory names; never follows directory symlinks."""
    return {
        p.relative_to(root).as_posix(): (
            ("link", str(p.readlink()))
            if p.is_symlink()
            else ("directory", None)
            if p.is_dir()
            else ("file", p.read_bytes())
        )
        for p in sorted(root.rglob("*"))
    }


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def repository(path):
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "main.py").write_text("print('fixture baseline')\n")
    (path / "AGENTS.md").write_text("Use the source repository's own instructions.\n")
    git(path, "add", ".")
    git(
        path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "Fixture baseline",
    )
    return path


def invoke(*args, code=0, input=None):
    result = CliRunner().invoke(app, [str(a) for a in args], input=input)
    assert result.exit_code == code, (args, result.output, repr(result.exception))
    return result


def outer_packets(root):
    found = []
    for path in (root / "runs").glob("*/packet.md"):
        try:
            value = json.loads(path.read_bytes())
        except ValueError:
            continue
        if value.get("schema_version") == 2 and value.get("kind") == "workspace-onboarding":
            found.append(path.parent)
    return set(found)


def propose(root, *args):
    before = outer_packets(root)
    invoke(*args, "--root", root)
    created = outer_packets(root) - before
    assert len(created) == 1, "One sealed v2 outer packet must be published"
    packet = created.pop()
    assert (packet / "seal").read_text() == sha((packet / "packet.md").read_bytes()) + "\n"
    return packet


def disposition(root, packet, *, reject=False, confirm=True, actor=ACTOR, seal=None, code=0):
    args = [
        "workspace",
        "reject" if reject else "apply",
        packet.relative_to(root).as_posix(),
        "--expect-seal",
        seal or (packet / "seal").read_text().strip(),
        "--root",
        root,
    ]
    if confirm:
        args += ["--confirm", "--confirmed-by", actor]
    if reject:
        args += ["--reason", "Goal needs another measurement"]
    return invoke(*args, code=code)


def onboard_a(root, source):
    packet = propose(root, "onboard", source, "--init", "--register-source", "source-main")
    disposition(root, packet)
    return packet


def child_input(root, name, *, context=False):
    path = root / f"runs/drafts/project-{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = f"""---
schema_version: 1
kind: project-creation-input
project: {name}
supersedes: null
question: "Which local request path dominates latency?"
motivation: "A bounded independent measurement is now useful."
included: ["One local request path"]
excluded: ["Deployment changes"]
assumptions: []
open_questions: ["Which trace is representative?"]
goal: "Measure one request path against a fixed trace."
constraints: "Local synthetic data only."
next_step: "Record the smallest useful measurement."
sources: []
pins: []
relationships: []
---
# Research brief
## Problem
Measure one local path.
## Minimal validation experiment
Replay a fixed local trace and record p50 and p99.
"""
    path.write_text(body)
    if context:
        doc = decode(path.read_bytes(), str(path))
        doc.header["sources"] = [{"path": "overview.md", "coverage": "full"}]
        path.write_bytes(encode(doc))
    return path


def child(root, name):
    """Populate healthy old child fixtures without depending on new intake."""
    import shutil

    staging = root.parent / ("template-" + name)
    initialize(staging, name)
    shutil.copytree(staging / "projects" / name, root / "projects" / name)


def catalog_bytes(definitions, associations):
    lines = ["schema_version = 2"]
    if not definitions:
        lines += ["definitions = []"]
    if not associations:
        lines += ["associations = []"]
    for item in definitions:
        lines += ["", "[[definitions]]"]
        lines += [f"{k} = {json.dumps(v)}" for k, v in item.items()]
    for item in associations:
        scope = ", ".join(f"{k} = {json.dumps(v)}" for k, v in item["scope"].items())
        lines += [
            "",
            "[[associations]]",
            f"scope = {{ {scope} }}",
            f"source = {json.dumps(item['source'])}",
            f"role = {json.dumps(item['role'])}",
        ]
    return ("\n".join(lines) + "\n").encode()


def catalog(root):
    return tomllib.loads((root / "sources.toml").read_text())


def role_map(root):
    return {
        (a["scope"]["kind"], a["scope"].get("project"), a["source"]): a["role"]
        for a in catalog(root)["associations"]
    }


def v2_workspace(root, source, *, children=()):
    initialize_workspace(root)
    for name in children:
        child(root, name)
    inspection = inspect_source(root, source)
    definition = {
        "id": "source-main",
        "definition_revision": 1,
        "kind": inspection.kind,
        "identity_method": f"{inspection.kind}-roots-v1"
        if inspection.kind == "git"
        else "directory-anchors-v1",
        "identity": inspection.identity,
    }
    associations = [{"scope": WS, "source": "source-main", "role": "working"}]
    associations += [
        {"scope": {"kind": "project", "project": name}, "source": "source-main", "role": "working"}
        for name in children
    ]
    (root / "sources.toml").write_bytes(catalog_bytes([definition], associations))
    (root / "tools/sources.local.toml").write_text(
        "schema_version = 1\n[bindings.source-main]\n"
        f'path = {json.dumps(str(source))}\nfilesystem = "{filesystem_identity(source)}"\n'
    )
    return definition


class FakeNative(AoEClient):
    """Fake across-profile inventory with persisted creation args, no process launch."""

    def __init__(self, profile="fixture"):
        self.profile = profile
        self.sessions = {}
        self.other = []
        self.created = []
        self.sent = []
        self.lookup_error = False
        self.create_uncertain = False

    def list_sessions(self):
        return tuple(self.sessions.values())

    def list_all_sessions(self):
        if self.lookup_error:
            raise AoEError("fixture cross-profile lookup unavailable")
        return tuple((self.profile, s) for s in self.sessions.values()) + tuple(self.other)

    def show(self, session_id):
        if session_id not in self.sessions:
            raise AoEError("fixture missing session")
        return self.sessions[session_id]

    def create(self, root, project, agent, *, title=None, add_directory=None, **options):
        sid = f"{len(self.created) + 1:016x}"
        self.created.append((root, project, agent, add_directory, options))
        row = AoESession(sid, root, agent, "live", "idle", "native-" + sid, title or "")
        self.sessions[sid] = row
        if self.create_uncertain:
            raise AoEError("fixture lost add response", creation_uncertain=True)
        return row

    def ready(self, session_id):
        return True, "idle"

    def send(self, session_id, message):
        self.sent.append((session_id, message))

    def archive(self):
        self.sessions = {
            key: replace(value, state="archived") for key, value in self.sessions.items()
        }
