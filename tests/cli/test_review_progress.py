"""C5-F1: file-derived round suggestions and advisory previews; no real tools."""

import pytest
from typer.testing import CliRunner

from toulmin.adapters import review as review_adapter
from toulmin.cli import decide
from toulmin.cli.app import app
from toulmin.core.codec import decode, encode
from toulmin.core.documents import sections
from toulmin.core.inspection import inspect_project
from toulmin.core.repository import Repository
from toulmin.protocols import project_proposals
from toulmin.protocols.research_map import move_facts, next_moves
from toulmin.protocols.review import plan_review
from toulmin.protocols.review_intake import intake_review
from toulmin.protocols.review_progress import review_advisory, review_progress
from toulmin.protocols.status import project_status

AT = "2026-11-11T23:33:00Z"
LATER = "2026-11-12T10:00:00Z"
OUTPUT = "projects/demo/runs/20261031T100000Z-review/output.md"
BLOCK = """```yaml
- label: d1
  target: C-001
  severity: major
  content: Existing concern.
  grounds: Existing reasoning.
- label: d2
  target: C-001
  severity: minor
  content: Another concern.
  grounds: Another reason.
```
"""


def edit(root, path, **header):
    document = decode((root / path).read_bytes(), path)
    document.header.update(header)
    (root / path).write_bytes(encode(document))
    return document


@pytest.fixture
def reviewed(populated):
    edit(populated, "projects/demo/PROJECT.md", stage="critique")
    edit(populated, "projects/demo/runs/R-001.md", created=AT)
    return populated


def facts(root):
    snapshot = inspect_project(Repository(root), "demo")
    assert not snapshot.errors, snapshot.errors
    return move_facts(
        root,
        "demo",
        snapshot,
        project_status(root, "demo").gates,
        project_proposals.inventory(root, "demo").items,
    )


def suggests_review(root):
    return any(move.how == "runs/proposals/review-…" for move in next_moves(facts(root), 50))


def add_material(root, kind, timestamp=LATER, invalidated=False, superseded=False):
    directory, prefix = ("claims", "C") if kind == "claim" else ("evidence", "E")
    document = decode((root / f"projects/demo/{directory}/{prefix}-001.md").read_bytes())
    document.header.update(id=f"{prefix}-002", created=timestamp)
    if invalidated:
        document.header["status"] = "invalidated"
        if "Invalidation" not in sections(document):
            document.body += "\n## Invalidation\nFixture invalidation.\n"
    if superseded:
        document.header.update(status="superseded", superseded_by="C-001", decisions=["D-001"])
    (root / f"projects/demo/{directory}/{prefix}-002.md").write_bytes(encode(document))


def test_no_new_material_suppresses_another_review_and_exposes_facts(reviewed):
    assert not suggests_review(reviewed)
    progress = facts(reviewed).review_progress
    assert progress.latest == "R-001" and progress.claims == () and progress.evidence == ()
    assert "no new Claim or Evidence" in review_advisory(reviewed, "demo")


@pytest.mark.parametrize("kind", ["claim", "evidence"])
def test_new_claim_or_evidence_suggests_review_and_removes_advisory(reviewed, kind):
    add_material(reviewed, kind)
    assert suggests_review(reviewed)
    progress = facts(reviewed).review_progress
    assert (len(progress.claims), len(progress.evidence)) == ((1, 0) if kind == "claim" else (0, 1))
    assert review_advisory(reviewed, "demo") is None


@pytest.mark.parametrize(
    "kind,options",
    [
        ("evidence", {"invalidated": True}),
        ("claim", {"superseded": True}),
        ("evidence", {"timestamp": AT}),
        ("claim", {"timestamp": "2026-11-12T00:33:00+01:00"}),
    ],
)
def test_invalidated_superseded_or_not_later_material_does_not_trigger(reviewed, kind, options):
    add_material(reviewed, kind, **options)
    assert not suggests_review(reviewed)
    assert review_advisory(reviewed, "demo") is not None


def test_no_completed_review_keeps_first_round_suggestion(reviewed):
    path = reviewed / "projects/demo/runs/R-001.md"
    run = decode(path.read_bytes())
    run.header["status"] = "failed"
    run.body += "\n## Failure\nFixture failure.\n"
    path.write_bytes(encode(run))
    assert suggests_review(reviewed)
    assert review_advisory(reviewed, "demo") is None


def test_newer_failed_run_does_not_replace_latest_completed_review(reviewed):
    path = reviewed / "projects/demo/runs/R-001.md"
    run = decode(path.read_bytes())
    run.header.update(
        id="R-002",
        created=LATER,
        status="failed",
        output="projects/demo/runs/20261112T100000Z-review-failed",
    )
    (reviewed / run.header["output"]).mkdir()
    run.body += "\n## Failure\nFixture failure.\n"
    (reviewed / "projects/demo/runs/R-002.md").write_bytes(encode(run))
    assert not suggests_review(reviewed)
    assert facts(reviewed).review_progress.latest == "R-001"


def test_advisory_counts_duplicates_and_old_records_omit_the_clause(reviewed):
    (reviewed / OUTPUT).write_text(BLOCK)
    intake_review(reviewed, "demo", OUTPUT, "Fixture", True, reject={"d2": "Out of scope."})
    old = review_advisory(reviewed, "demo")
    assert "Since the last round (R-001, 2026-11-11 23:33 UTC)" in old
    assert "Last round:" not in old
    intake_review(reviewed, "demo", OUTPUT, "Fixture", True, duplicate={"d1": "O-001"})
    notice = review_advisory(reviewed, "demo")
    assert "Last round: 1 of 2 drafts were duplicates of existing Objections." in notice
    assert "applying still starts it" in notice
    assert project_status(reviewed, "demo").errors == ()


def test_round_counts_include_all_completed_sessions_with_the_common_archive_stamp(reviewed):
    original = decode((reviewed / "projects/demo/runs/R-001.md").read_bytes())
    for number, suffix in ((1, "reviewer-one-model"), (2, "reviewer-two-model")):
        run = decode(encode(original))
        run.header.update(
            id=f"R-{number:03d}", output=f"projects/demo/runs/20261111T230000Z-review-{suffix}"
        )
        (reviewed / run.header["output"]).mkdir()
        (reviewed / run.header["output"] / "output.md").write_text(BLOCK)
        (reviewed / f"projects/demo/runs/R-{number:03d}.md").write_bytes(encode(run))
        # O-001 retains its original source; duplicate does not rewrite it.
        if number == 1:
            edit(
                reviewed,
                "projects/demo/objections/O-001.md",
                source={"kind": "human", "actor": "Fixture"},
            )
            edit(
                reviewed,
                "projects/demo/evidence/E-001.md",
                source={"kind": "human", "actor": "Fixture"},
            )
        intake_review(
            reviewed,
            "demo",
            run.header["output"] + "/output.md",
            "Fixture",
            True,
            duplicate={"d1": "O-001", "d2": "O-001"},
        )
    assert "4 of 4 drafts" in review_advisory(reviewed, "demo")
    assert facts(reviewed).review_progress.runs == ("R-001", "R-002")


@pytest.mark.parametrize("new_material", [False, True])
def test_direct_review_preview_advisory_is_present_only_without_new_material(
    reviewed, monkeypatch, new_material
):
    monkeypatch.setattr(review_adapter, "_preflight", lambda *args: None)

    def forbidden(*args, **kwargs):
        raise AssertionError("preview invoked a model")

    monkeypatch.setattr(review_adapter, "_execute", forbidden)
    if new_material:
        add_material(reviewed, "evidence")
    result = CliRunner().invoke(app, ["review", "demo", "--root", str(reviewed), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert ("no new Claim or Evidence" in result.stdout) == (not new_material)


def test_decide_advisory_precedes_apply_and_does_not_refuse(reviewed, monkeypatch):
    monkeypatch.setattr(decide, "_interactive", lambda: True)
    monkeypatch.setattr(review_adapter, "_preflight", lambda *args: None)
    calls = []

    def execute(plan, actor, echo):
        calls.append(plan)
        return review_adapter.RoundResult((), None, "fake round completed")

    monkeypatch.setattr(review_adapter, "execute_round", execute)
    folder = reviewed / "projects/demo/runs/proposals"
    folder.mkdir()
    (folder / "review-20261112T100000Z.md").write_text(
        "---\nschema_version: 1\nkind: review-request\n---\n## Why now\n"
        "Researcher requests another look.\n"
    )
    result = CliRunner().invoke(
        app, ["decide", "--root", str(reviewed), "--confirmed-by", "Researcher"], input="a\n"
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert result.stdout.index("no new Claim or Evidence") < result.stdout.index("[a]pply")


def test_review_inputs_and_prompts_do_not_gain_objections(reviewed):
    tasks = plan_review(reviewed, "demo", ["reviewer-skeptic"], ["fixture-model"], 1)
    assert not any("/objections/" in name for name in tasks[0].files)
    assert "<<<FILE projects/demo/objections/" not in tasks[0].prompt
    data = review_progress(inspect_project(Repository(reviewed), "demo").objects)
    assert data.reviewed
