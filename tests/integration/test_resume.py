"""A synthetic restart test, not the roadmap's real next-day human acceptance."""

import re
import subprocess
import sys
from pathlib import Path

from toulmin.core.codec import decode, encode
from toulmin.core.documents import Document


def test_manual_command_chain_then_fresh_process_recovers_only_from_files(tmp_path):
    executable = Path(sys.executable).with_name("toulmin")
    root = tmp_path / "research"

    def command(*arguments):
        return subprocess.run(
            [str(executable), *arguments], cwd=tmp_path, capture_output=True, text=True, check=True
        )

    command("init", str(root), "--project", "demo")
    charter = root / "projects/demo/PROJECT.md"
    document = decode(charter.read_bytes())
    document.body = (
        "## Goal\nFixture research idea for recovery test.\n\n"
        "## Constraints\nSynthetic data; no actual model invoked.\n"
    )
    charter.write_bytes(encode(document))
    manual = root / "projects/demo/runs/manual"
    manual.mkdir()
    examples = (root / "framework/format-examples.md").read_text()
    objects = {
        doc.object_id.kind: doc
        for sample in re.findall(r"````markdown\n(.*?)\n````", examples, re.S)
        for doc in [decode(sample.encode())]
    }

    def new(kind):
        doc = objects[kind]
        header = dict(doc.header)
        for field in ("id", "created", "confirmed_by"):
            header.pop(field)
        if kind != "run":
            header.pop("status")
        source = manual / f"{kind}.md"
        source.write_bytes(encode(Document(header, doc.body)))
        command(
            "new",
            kind,
            "demo",
            "--root",
            str(root),
            "--input",
            str(source.relative_to(root)),
            "--confirmed-by",
            "Fixture Researcher",
            "--confirm",
        )

    new("claim")
    output = root / "projects/demo/runs/20261031T100000Z-review"
    output.mkdir()
    (output / "output.md").write_text("Synthetic review fixture: challenge C-001.\n")
    new("run")
    new("objection")
    status = command("status", "demo", "--root", str(root))
    assert "O-001 | major | target=C-001" in status.stdout
    handoff_input = manual / "handoff.md"
    handoff_input.write_bytes(
        encode(
            Document(
                {
                    "session_id": "fixture-first-session",
                    "recent_decisions": [],
                    "next_step": "Answer O-001 before further validation.",
                },
                "## Done\nCreated C-001; archived R-001; confirmed intake of O-001.\n\n"
                "## Decisions\nNo new gate ruling; O-001 remains pending.\n\n"
                "## Open questions\nResolve O-001 using its archived source.\n",
            )
        )
    )
    draft = root / Path(
        command(
            "handoff", "demo", "--root", str(root), "--input", str(handoff_input.relative_to(root))
        ).stdout.strip()
    )
    command(
        "handoff",
        "demo",
        "--root",
        str(root),
        "--apply",
        str(draft.relative_to(root)),
        "--confirmed-by",
        "Fixture Researcher",
        "--confirm",
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture Researcher",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "test: hand off C-001 O-001 R-001",
        ],
        check=True,
    )
    script = """
from pathlib import Path
import sys
from toulmin.core.repository import Repository
from toulmin.core.documents import sections
from toulmin.protocols.session import entry_files
from toulmin.protocols.status import project_status
root = Path(sys.argv[1])
repo = Repository(root)
project = repo.read('projects/demo/PROJECT.md')
resident = entry_files('demo', project.header['last_handoff'])
assert [str(path) for path in resident[:2]] == ['AGENTS.md', 'projects/demo/PROJECT.md']
assert all((root / path).is_file() for path in resident)
session = repo.read(str(resident[2]))
assert session.header['session_id'] == 'fixture-first-session'
assert 'Fixture research idea' in sections(project)['Goal']
assert project.header['next_step'] == 'Answer O-001 before further validation.'
report = project_status(root, 'demo')
assert not report.errors and report.stage == 'explore'
assert str(report.open_objections[0].object_id) == 'O-001'
objection, _ = repo.resolve('demo', 'O-001')
run, _ = repo.resolve('demo', objection.header['source']['ref'])
assert run.header['role'] == 'reviewer'
original = repo.path(objection.header['source']['path'], 'file')
assert 'Synthetic review fixture' in original.read_text()
print('resumed from resident files; goal, open objection, next step and provenance recovered')
"""
    process = subprocess.run(
        [sys.executable, "-I", "-c", script, str(root)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "resumed from resident files" in process.stdout
    clean = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert clean.stdout == ""
