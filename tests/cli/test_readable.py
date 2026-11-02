import re

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode

SECOND = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"
LONG_PLAN = "Replay the drifting trace with a fixed seed " * 5


@pytest.fixture(autouse=True)
def no_operator_default(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)


def write(root, relative, text):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return relative


CLAIM_DRAFT = f"""---
importance: core
type: problem
source: {{kind: human, actor: "Tianchi YU"}}
validation_plan: "{LONG_PLAN.strip()}"
tags: [workload]
---
## Statement
{"Queueing delay dominates tail latency under drifting load " * 3}

Second paragraph.
"""


def new_claim(root, *extra):
    relative = write(root, "projects/demo/runs/drafts/c.md", CLAIM_DRAFT)
    command = ["new", "claim", "demo", "--input", relative, "--confirmed-by", "Tianchi YU"]
    return CliRunner().invoke(app, [*command, "--confirm", *extra])


def test_generated_object_header_is_ordered_unfolded_and_second_precise(populated):
    result = new_claim(populated, "--root", str(populated))
    assert result.exit_code == 0, result.output
    assert result.stdout == "projects/demo/claims/C-002.md\n"
    text = (populated / "projects/demo/claims/C-002.md").read_text()
    header = text.split("\n---\n", 1)[0].splitlines()[1:]
    keys = [line.split(":", 1)[0] for line in header if not line.startswith((" ", "-"))]
    assert keys == [
        "schema_version",
        "id",
        "status",
        "created",
        "source",
        "confirmed_by",
        "type",
        "importance",
        "tags",
        "validation_plan",
    ]
    plan = next(line for line in header if line.startswith("validation_plan:"))
    assert LONG_PLAN.strip() in plan  # one line, not folded at 80 columns
    document = decode(text.encode())
    assert re.fullmatch(SECOND, document.header["created"])
    assert document.header["confirmed_by"]["at"] == document.header["created"]


def test_new_prints_root_relative_path_from_default_root(populated, monkeypatch):
    monkeypatch.chdir(populated)
    result = new_claim(populated)
    assert result.exit_code == 0, result.output
    assert result.stdout == "projects/demo/claims/C-002.md\n"


def test_existing_files_with_old_style_headers_remain_valid(populated):
    # Files written before U3 have sorted keys, folded strings and microseconds.
    legacy = """---
confirmed_by:
  actor: Tianchi YU
  at: '2026-11-02T13:47:08.613558Z'
created: '2026-11-02T13:47:08.613558Z'
id: C-002
importance: core
schema_version: 1
source:
  actor: Tianchi YU
  kind: human
status: proposed
type: magnitude
validation_plan: db_bench fillrandom with bursts; attribute latency via RocksDB
  stall statistics.
---
## Statement
Write stalls account for more than half of p99 write latency.
"""
    write(populated, "projects/demo/claims/C-002.md", legacy)
    result = CliRunner().invoke(app, ["status", "demo", "--root", str(populated)])
    assert result.exit_code == 0, result.output
    assert "C-002 | stored=proposed" in result.stdout


def test_status_verbose_shows_statements_objections_and_last_handoff(populated):
    write(
        populated,
        "projects/demo/claims/C-002.md",
        (populated / "projects/demo/claims/C-001.md")
        .read_text()
        .replace("id: C-001", "id: C-002")
        .split("## Statement\n")[0]
        + "## Statement\n\n"
        + "x" * 150
        + "\nsecond line\n",
    )
    plain = CliRunner().invoke(app, ["status", "demo", "--root", str(populated)])
    verbose = CliRunner().invoke(app, ["status", "demo", "--root", str(populated), "-v"])
    assert plain.exit_code == verbose.exit_code == 0, verbose.output
    assert "Last handoff" not in plain.stdout
    assert "Queueing delay is the main source" not in plain.stdout
    lines = verbose.stdout.splitlines()
    assert "Last handoff: none" in lines
    claim = lines.index(next(line for line in lines if line.startswith("  C-001 |")))
    assert lines[claim + 1] == (
        "      Queueing delay is the main source of tail latency under the specified load."
    )
    long_claim = lines.index(next(line for line in lines if line.startswith("  C-002 |")))
    assert lines[long_claim + 1] == "      " + "x" * 97 + "..."
    write(
        populated,
        "projects/demo/claims/C-003.md",
        (populated / "projects/demo/claims/C-001.md")
        .read_text()
        .replace("id: C-001", "id: C-003")
        .split("## Statement\n")[0]
        + "## Statement\nWrapped by\nhand.\n\nNot part of the summary.\n",
    )
    lines = CliRunner().invoke(app, ["status", "demo", "--root", str(populated), "-v"]).stdout
    lines = lines.splitlines()
    wrapped = lines.index(next(line for line in lines if line.startswith("  C-003 |")))
    assert lines[wrapped + 1] == "      Wrapped by hand."
    objection = lines.index("  O-001 | major | target=C-001")
    assert lines[objection + 1].startswith("      A fixed request distribution")

    draft = CliRunner().invoke(app, ["handoff", "demo", "--root", str(populated)])
    applied = CliRunner().invoke(
        app,
        [
            "handoff",
            "demo",
            "--root",
            str(populated),
            "--apply",
            draft.stdout.strip(),
            "--confirmed-by",
            "Tianchi YU",
            "--confirm",
        ],
    )
    assert applied.exit_code == 0, applied.output
    verbose = CliRunner().invoke(app, ["status", "demo", "--root", str(populated), "-v"])
    assert f"Last handoff: {applied.stdout.strip()}" in verbose.stdout.splitlines()


def test_handoff_files_use_contract_field_order(populated):
    draft = CliRunner().invoke(app, ["handoff", "demo", "--root", str(populated)])
    text = (populated / draft.stdout.strip()).read_text()
    keys = [
        line.split(":", 1)[0]
        for line in text.split("\n---\n", 1)[0].splitlines()[1:]
        if not line.startswith((" ", "-"))
    ]
    assert keys == [
        "schema_version",
        "project",
        "session_id",
        "created",
        "base_project_sha256",
        "recent_decisions",
        "next_step",
    ]
