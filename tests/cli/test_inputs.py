from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.roles import natural_key, parse_manifest
from toulmin.protocols.inputs import resolve_inputs

TEMPLATES = Path(__file__).resolve().parents[2] / "src/toulmin/cli/templates/roles"
INDEPENDENT = sorted(path.stem for path in TEMPLATES.glob("*.md") if path.stem != "scribe")
CLAIMS = "projects/demo/claims"
ARCHIVE = "projects/demo/runs/20261031T100000Z-review"
# Discussion history and other outputs no independent role may ever receive.
FORBIDDEN = ("/sessions/", "/runs/", "/decisions/", "/objections/", "PROJECT.md", "calibration")


@pytest.fixture(autouse=True)
def no_operator_default(monkeypatch):
    monkeypatch.delenv("TOULMIN_ACTOR", raising=False)


def copy_claim(root, number, **changes):
    document = decode((root / f"{CLAIMS}/C-001.md").read_bytes())
    document.header.update(id=f"C-{number:03}", **changes)
    (root / f"{CLAIMS}/C-{number:03}.md").write_bytes(encode(document))


@pytest.fixture
def bench(populated):
    copy_claim(populated, 2)
    copy_claim(populated, 10)
    (populated / "global/papers/io-uring-notes.md").write_text("Paper notes.\n")
    (populated / "projects/demo/sessions/note.md").write_text("Discussion.\n")
    return populated


def inputs(root, *arguments):
    return CliRunner().invoke(app, ["inputs", "demo", *arguments, "--root", str(root)])


def test_reviewer_receives_exactly_the_brief_and_current_claims_in_order(bench):
    result = inputs(bench, "reviewer")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        "AGENTS.md",
        "roles/reviewer.md",
        "projects/demo/brief.md",
        f"{CLAIMS}/C-001.md",
        f"{CLAIMS}/C-002.md",
        f"{CLAIMS}/C-010.md",
    ]
    papers = inputs(bench, "reviewer-why-not-x").stdout.splitlines()
    assert papers[-1] == "global/papers/io-uring-notes.md"
    assert ".gitkeep" not in "".join(papers)


@pytest.mark.parametrize("role", INDEPENDENT)
def test_every_shipped_independent_role_resolves_without_discussion_history(bench, role):
    result = resolve_inputs(bench, "demo", role)
    assert f"roles/{role}.md" in result.files and "projects/demo/brief.md" in result.files
    assert not any(marker in path for path in result.files for marker in FORBIDDEN)
    if role.startswith("reviewer-"):
        assert "roles/reviewer.md" in result.files  # personas extend the base contract
    assert result.operation == ("synthesize" if role == "synthesizer" else "critique")


def test_superseded_claims_are_left_out_and_selection_narrows(bench):
    copy_claim(bench, 1, status="superseded", superseded_by="C-002", decisions=["D-001"])
    result = inputs(bench, "reviewer")
    assert f"{CLAIMS}/C-001.md" not in result.stdout
    assert "Left out superseded Claims: C-001" in result.stderr
    selected = inputs(bench, "reviewer", "--claim", "C-010", "--claim", "demo/C-002")
    assert selected.exit_code == 0, selected.output
    assert [line for line in selected.stdout.splitlines() if line.startswith(CLAIMS)] == [
        f"{CLAIMS}/C-002.md",
        f"{CLAIMS}/C-010.md",
    ]
    stale = inputs(bench, "reviewer", "--claim", "C-001")
    assert stale.exit_code == 1 and "superseded by C-002; select the current Claim" in stale.output


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["reviewer", "--claim", "C-009"], "C-009: claim: not among the inputs"),
        (["reviewer", "--claim", "O-001"], "expected a Claim ID"),
        (["reviewer", "--claim", "other/C-001"], "expected a Claim in project demo"),
        (["reviewer", "--claim", "C-1"], "C-1: claim:"),
        (["scribe"], "no input manifest"),
        (["nobody"], "roles/nobody.md"),
        (["../AGENTS"], "expected lowercase letters"),
    ],
)
def test_bad_roles_and_selections_fail(bench, arguments, message):
    result = inputs(bench, *arguments)
    assert result.exit_code == 1
    assert message in result.output


def test_symlinked_inputs_are_refused(bench, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("Not part of the workbench.\n")
    (bench / "global/papers/link.md").symlink_to(outside)
    result = inputs(bench, "reviewer-why-not-x")
    assert result.exit_code == 1 and "symlinks forbidden" in result.output


def manifest(inputs_block, role="tester", operation="critique", extra=""):
    lines = "".join(f"  - {item}\n" for item in inputs_block)
    return (
        f"---\nschema_version: 1\nrole: {role}\noperation: {operation}\n{extra}"
        f"inputs:\n{lines}---\n# Tester\n"
    ).encode()


OWN = "roles/tester.md"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (manifest([OWN, "projects/{project}/sessions/*"]), "outside the inputs"),
        (manifest([OWN, "projects/{project}/runs/x/output.md"]), "outside the inputs"),
        (manifest([OWN, "projects/{project}/PROJECT.md"]), "outside the inputs"),
        (manifest([OWN, "projects/{project}/decisions/*.md"]), "outside the inputs"),
        (manifest([OWN, "projects/{project}/objections/*.md"]), "outside the inputs"),
        (manifest([OWN, "projects/demo/claims/*.md"]), "outside the inputs"),
        (manifest([OWN, "projects/*/brief.md"]), "wildcards are allowed only in the last"),
        (manifest([OWN, "global/calibration/*"]), "outside the inputs"),
        (manifest([OWN, "projects/{project}/claims/*"]), "outside the inputs"),
        (manifest([OWN, "projects/{project}/claims/../runs/a.md"]), "portable root-relative"),
        (manifest([OWN, "/etc/passwd"]), "portable root-relative"),
        (manifest([OWN, "projects/{role}/brief.md"]), "only the {project} placeholder"),
        (manifest(["AGENTS.md"]), "must include the role file roles/tester.md"),
        (manifest([OWN, OWN]), "duplicate pattern"),
        (manifest([OWN], role="other"), "expected tester, matching the filename"),
        (manifest([OWN], operation="expand"), "operation: expected one of"),
        (manifest([OWN], extra="model: x\n"), "model: unknown field"),
        (manifest([]).replace(b"inputs:\n", b"inputs: []\n"), "at least one item"),
    ],
)
def test_manifest_contract(data, message):
    with pytest.raises(FormatError) as error:
        parse_manifest(data, "roles/tester.md", "tester")
    assert message in str(error.value)


def test_narrower_patterns_inside_the_allowlist_are_accepted():
    parsed = parse_manifest(
        manifest([OWN, "projects/{project}/claims/C-00?.md", "global/papers/*.md"]),
        "roles/tester.md",
        "tester",
    )
    assert parsed.inputs[1:] == ("projects/{project}/claims/C-00?.md", "global/papers/*.md")


def test_natural_order_puts_c999_before_c1000():
    names = ["C-1000.md", "C-999.md", "C-010.md", "C-002.md"]
    assert sorted(names, key=natural_key) == ["C-002.md", "C-010.md", "C-999.md", "C-1000.md"]


def test_run_draft_takes_role_and_inputs_and_becomes_a_run(bench):
    command = ["draft", "run", "demo", "--root", str(bench), "--role", "reviewer-skeptic"]
    result = CliRunner().invoke(app, [*command, "--claim", "C-002"])
    assert result.exit_code == 0, result.output
    relative = result.stdout.strip()
    text = (bench / relative).read_text()
    assert 'role: "reviewer-skeptic"' in text
    assert f'  - "{CLAIMS}/C-002.md"' in text and "C-001.md" not in text
    for placeholder, value in (
        ('"<fill: completed | failed>"', "completed"),
        ('"<fill: model name as reported by the tool>"', "example-model"),
        ('"<fill: projects/demo/runs/YYYYMMDDTHHMMSSZ-name>"', ARCHIVE),
        ('"<fill: researcher>"', '"Tianchi YU"'),
        ("<fill: what was run and what it produced>", "Skeptic review."),
    ):  # fmt: skip
        text = text.replace(placeholder, value)
    (bench / relative).write_text(text)
    created = CliRunner().invoke(
        app,
        ["new", "run", "demo", "--input", relative, "--root", str(bench)]
        + ["--confirmed-by", "Tianchi YU", "--confirm"],
    )
    assert created.exit_code == 0, created.output
    run = decode((bench / "projects/demo/runs/R-002.md").read_bytes())
    assert run.header["role"] == "reviewer-skeptic"
    assert run.header["input_files"] == [
        "AGENTS.md",
        "roles/reviewer.md",
        "roles/reviewer-skeptic.md",
        "projects/demo/brief.md",
        f"{CLAIMS}/C-002.md",
    ]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["claim", "demo", "--role", "reviewer"], "only a Run draft takes a role's inputs"),
        (["run", "demo", "--claim", "C-001"], "selecting Claims needs a role"),
        (["run", "demo", "--role", "scribe"], "no input manifest"),
    ],
)
def test_role_drafts_fail_before_writing(bench, arguments, message):
    before = sorted(str(path) for path in bench.rglob("*"))
    result = CliRunner().invoke(app, ["draft", *arguments, "--root", str(bench)])
    assert result.exit_code == 1
    assert message in result.output
    assert sorted(str(path) for path in bench.rglob("*")) == before
