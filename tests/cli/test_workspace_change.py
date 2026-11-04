"""WI3: reviewed workspace changes and shared resource descriptions.

Every test uses a temporary workspace; no model, network or real research project.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toulmin.cli.app import app
from toulmin.cli.initialize import initialize, initialize_workspace
from toulmin.core import workspace_journal
from toulmin.core.atomic import digest
from toulmin.core.documents import FormatError
from toulmin.protocols import workspace_change
from toulmin.protocols.workspace_change import apply, load, propose, reject

runner = CliRunner()
DOCS = Path(__file__).resolve().parents[2] / "docs"
ACTIVITY = "runs/20261104T093000Z-activity-6b1f0c2e9a4d4e7f8c3b2a1d0e9f8a7b/activity.md"
FIRST = "runs/20261104T100000Z-proposal-0d9e8c7b6a5f4e3d2c1b0a9f8e7d6c5b"
PACKET = "runs/20261104T101500Z-proposal-a41c9e07d3b24f5e9b6c8d7e1f203a4b"
INPUT = "runs/drafts/workspace-direction.md"
TRACE = "shared/data/synthetic-queue-trace"
RESOURCE = "shared/resources/synthetic-queue-trace.md"
APPROVAL = "Approve this packet: direction, constraints and the trace registration."


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def examples():
    """The contract's markdown examples (docs/workspace-formats.md), as exact bytes."""
    text = (DOCS / "workspace-formats.md").read_text()
    blocks = [part.split("\n````", 1)[0] + "\n" for part in text.split("````markdown\n")[1:]]

    def one(*needles):
        found = [block for block in blocks if all(needle in block for needle in needles)]
        assert len(found) == 1, needles
        return found[0].encode()

    return {
        "activity": one("kind: workspace-activity"),
        "input": one("kind: workspace-change-input"),
        "packet": one("kind: workspace-change\n"),
        "receipt": one("kind: workspace-receipt", "disposition: applied"),
        "charter": one('name: "Serving Research"\ncharter_revision: 1', "next_step: null\n"),
        "resource": one("---\nschema_version: 1\nresource: synthetic-queue-trace"),
    }


@pytest.fixture
def root(tmp_path):
    """The contract's fixture: a fresh workspace, the synthetic trace and one activity."""
    root = tmp_path / "serving"
    initialize_workspace(root, "Serving Research")
    (root / TRACE).mkdir(parents=True)
    (root / TRACE / "trace.csv").write_text("arrival_us,service_us\n0,180\n240,95\n410,620\n")
    (root / TRACE / "README.md").write_text(
        "Synthetic single-queue trace for the WS3 fixture. Not a measurement.\n"
    )
    (root / ACTIVITY).parent.mkdir(parents=True)
    (root / ACTIVITY).write_bytes(examples()["activity"])
    return root


def contents(root):
    """Bytes of every file outside runs/ (confirmed state, projects and material)."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).parts[0] != "runs"
    }


def contract_packet(root):
    """Propose the contract's example: a first packet, then its revision superseding it."""
    data = examples()["input"]
    (root / INPUT).write_bytes(data.replace(f"supersedes: {FIRST}".encode(), b"supersedes: null"))
    propose(root, INPUT, at("2026-11-04T10:00:00"), FIRST.rsplit("-", 1)[1])
    (root / INPUT).write_bytes(data)
    return propose(root, INPUT, at("2026-11-04T10:15:00"), PACKET.rsplit("-", 1)[1])


def write_input(root, changes, *, sources="[]", pins="[]", name="change.md", supersedes="null"):
    text = (
        "---\nschema_version: 1\nkind: workspace-change-input\nscope: {kind: workspace}\n"
        f"supersedes: {supersedes}\nsources: {sources}\npins: {pins}\nchanges:\n{changes}"
        "---\n## Question\nChange it?\n\n## Unresolved assumptions\nNone.\n"
    )
    (root / "runs/drafts" / name).write_text(text)
    return f"runs/drafts/{name}"


FOCUS = '  - target: charter\n    sections: {Focus: "Compare FIFO and SRPT first."}\n'


def confirm(root, packet, actor="Tianchi YU", **extra):
    return apply(root, packet, actor, confirmed=True, **extra)


def invoke(*args, env=None):
    return runner.invoke(app, [str(arg) for arg in args], env=env or {"TOULMIN_ACTOR": ""})


# Propose: frozen, sourced, readable; confirmed state untouched.


def test_contract_example_is_reproduced_byte_for_byte(root):
    expected = examples()
    before = contents(root)
    outcome = contract_packet(root)
    packet = root / PACKET
    assert (packet / "packet.md").read_bytes() == expected["packet"]
    assert (packet / "seal").read_text() == digest(expected["packet"]) + "\n"
    assert (packet / "input.md").read_bytes() == expected["input"]
    assert (packet / "sources/1.md").read_bytes() == expected["activity"]
    assert (packet / "targets/1.md").read_bytes() == expected["charter"]
    assert (packet / "targets/2.md").read_bytes() == expected["resource"]
    assert contents(root) == before  # propose changes no confirmed file
    assert outcome.status == "proposed"

    result = confirm(root, PACKET, approval_text=APPROVAL, now=at("2026-11-04T10:20:00"))
    assert result.status == "applied"
    assert (root / "WORKSPACE.md").read_bytes() == expected["charter"]
    assert (root / RESOURCE).read_bytes() == expected["resource"]
    assert (packet / "receipt.md").read_bytes() == expected["receipt"]
    assert not (root / workspace_journal.JOURNAL).exists()
    # Registration is a description only: no Evidence, Claim or project appears.
    assert not list(root.glob("projects/*/"))
    assert not list(root.rglob("E-*.md")) and not list(root.rglob("C-*.md"))


def test_propose_cli_shows_scope_diff_sources_seal_and_commands(root):
    (root / INPUT).write_bytes(
        examples()["input"].replace(f"supersedes: {FIRST}".encode(), b"supersedes: null")
    )
    result = invoke("workspace", "propose", "--root", root, "--input", INPUT)
    assert result.exit_code == 0, result.output
    directory = next(path for path in (root / "runs").iterdir() if "-proposal-" in path.name)
    seal = (directory / "seal").read_text().strip()
    for line in (
        f"Root: {root}",
        "Scope: workspace",
        f"Packet: runs/{directory.name}",
        f"Seal: {seal[:16]}",
        "Target: WORKSPACE.md (replace)",
        f"Target: {RESOURCE} (create)",
        "+## Direction",
        f"- {ACTIVITY} (selected messages; complete capture of that selection)",
        "--confirmed-by ACTOR --confirm",
    ):
        assert line in result.stdout, line
    assert "charter_revision: 0" in (root / "WORKSPACE.md").read_text()  # still unchanged


def test_coverage_is_labeled_honestly_and_must_match_the_activity(root):
    activity = (root / ACTIVITY).read_text()
    (root / ACTIVITY).write_text(
        activity.replace(
            "capture: {coverage: selected, complete: true,",
            "capture: {coverage: summary, complete: false,",
        )
    )
    (root / "runs/notes.txt").write_text("free-form scratch\n")
    sources = (
        f"[{{path: {ACTIVITY}, coverage: summary}}, {{path: runs/notes.txt, coverage: unknown}}, "
        '{url: "https://example.org/paper", coverage: summary}]'
    )
    outcome = propose(root, write_input(root, FOCUS, sources=sources))
    body = outcome.loaded.body
    assert "summary only; INCOMPLETE capture: Selected researcher messages" in body
    assert "- runs/notes.txt (coverage: unknown)" in body
    assert "- https://example.org/paper (coverage: summary)" in body
    assert (root / outcome.loaded.directory / "sources/2.txt").read_text() == "free-form scratch\n"

    wrong = f"[{{path: {ACTIVITY}, coverage: full}}]"
    with pytest.raises(FormatError, match="the activity record says summary"):
        propose(root, write_input(root, FOCUS, sources=wrong, name="wrong.md"))


def test_oversized_source_is_recorded_by_digest_without_snapshot(root, monkeypatch):
    (root / "runs/odd.my-ext").write_text("odd suffix\n")
    odd = propose(
        root, write_input(root, FOCUS, sources="[{path: runs/odd.my-ext, coverage: full}]")
    )
    assert odd.loaded.packet.sources[0].snapshot == "sources/1"
    monkeypatch.setattr(workspace_change, "MAX_BYTES", 2000)
    (root / "runs/big.txt").write_text("x" * 2001)
    outcome = propose(
        root, write_input(root, FOCUS, sources="[{path: runs/big.txt, coverage: full}]")
    )
    source = outcome.loaded.packet.sources[0]
    assert source.snapshot is None and source.sha256 == digest(b"x" * 2001)
    assert not (root / outcome.loaded.directory / "sources").exists()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            "  - target: project\n    path: projects/scheduling/brief.md\n",
            "only charter and resource",
        ),
        ('  - target: charter\n    sections: {Goal: "x"}\n', "Direction, Constraints or Focus"),
        ("  - target: charter\n    sections: {Focus: null}\n", "name and sections unchanged"),
        (
            "  - target: resource\n    resource: synthetic-queue-trace\n    action: revise\n"
            '    title: "x"\n',
            "not registered",
        ),
        (
            '  - target: resource\n    resource: claims\n    action: register\n    title: "C"\n'
            "    status: active\n    kind: data\n"
            "    location: {path: projects/scheduling/claims, url: null}\n"
            "    version: {method: tree-v1, sha256: " + "ab" * 32 + ", revision: null}\n"
            '    origin: "o"\n    purpose: "p"\n    limitations: "l"\n',
            "formal object directories",
        ),
        (
            '  - target: resource\n    resource: trace\n    action: register\n    title: "T"\n'
            f"    status: active\n    kind: data\n    location: {{path: {TRACE}, url: null}}\n"
            "    version: {method: file, sha256: " + "ab" * 32 + ", revision: null}\n"
            '    origin: "o"\n    purpose: "p"\n    limitations: "l"\n',
            "path is a directory; use tree-v1",
        ),
    ],
)
def test_invalid_changes_are_refused_before_any_packet(root, changes, message):
    with pytest.raises(FormatError, match=message):
        propose(root, write_input(root, changes))
    assert not [path for path in (root / "runs").iterdir() if "proposal" in path.name]


def test_input_must_be_a_root_draft_of_the_right_kind(root):
    (root / "notes.md").write_text("x\n")
    with pytest.raises(FormatError, match="runs/drafts/"):
        propose(root, "notes.md")
    path = write_input(root, FOCUS)
    text = (root / path).read_text().replace("workspace-change-input", "workspace-change")
    (root / path).write_text(text)
    with pytest.raises(FormatError, match="kind: expected workspace-change-input"):
        propose(root, path)


def test_supersedes_must_name_a_pending_packet(root):
    contract_packet(root)
    with pytest.raises(FormatError, match="already superseded"):
        propose(root, write_input(root, FOCUS, supersedes=FIRST))
    confirm(root, PACKET)
    with pytest.raises(FormatError, match="already has a receipt"):
        propose(root, write_input(root, FOCUS, supersedes=PACKET, name="b.md"))


# Apply: exact-content authorization, relevant checks only.


def test_preview_and_missing_confirmation_write_nothing(root):
    contract_packet(root)
    before = contents(root)
    preview = invoke("workspace", "apply", "--root", root, "--draft", PACKET)
    assert preview.exit_code == 0, preview.output
    assert "Preview only; nothing written." in preview.stdout
    assert "+## Direction" in preview.stdout
    refused = invoke("workspace", "apply", "--root", root, "--draft", PACKET, "--confirmed-by", "R")
    assert refused.exit_code == 1
    assert "not applied; confirmation missing" in refused.stderr
    no_actor = invoke("workspace", "apply", "--root", root, "--draft", PACKET, "--confirm")
    assert no_actor.exit_code == 2
    assert contents(root) == before
    assert not (root / PACKET / "receipt.md").exists()


def test_apply_cli_uses_actor_and_replays_the_original_receipt(root):
    contract_packet(root)
    env = {"TOULMIN_ACTOR": "Tianchi YU"}
    args = ("workspace", "apply", "--root", root, "--draft", f"{PACKET}/packet.md", "--confirm")
    result = invoke(*args, env=env)
    assert result.exit_code == 0, result.output
    assert "Disposition: applied by Tianchi YU" in result.stdout
    assert f"Published: WORKSPACE.md ({digest(examples()['charter'])[:16]})" in result.stdout
    receipt = (root / PACKET / "receipt.md").read_bytes()
    state = contents(root)
    again = invoke(*args, "--confirmed-by", "Someone Else")
    assert again.exit_code == 0, again.output
    assert "Already recorded; nothing written." in again.stdout
    assert "applied by Tianchi YU" in again.stdout
    assert (root / PACKET / "receipt.md").read_bytes() == receipt
    assert contents(root) == state


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (INPUT, "an input, not a reviewed packet"),
        ("runs/20261104T140000Z-project-" + "c" * 32, "child creation packet"),
        ("runs/20261104T113000Z-handoff-" + "5" * 32 + "/draft.md", "handoff draft"),
        ("WORKSPACE.md", "expected a workspace change packet"),
    ],
)
def test_wrong_artifacts_are_refused(root, value, message):
    contract_packet(root)
    before = contents(root)
    with pytest.raises(FormatError, match=message):
        confirm(root, value)
    assert contents(root) == before


@pytest.mark.parametrize("name", ["packet.md", "targets/1.md", "sources/1.md", "input.md"])
def test_any_edit_after_preview_invalidates_the_packet(root, name):
    contract_packet(root)
    path = root / PACKET / name
    path.write_bytes(path.read_bytes() + b"\nedited\n")
    before = contents(root)
    with pytest.raises(FormatError, match="changed after preview"):
        confirm(root, PACKET)
    assert contents(root) == before


def test_wrong_scope_in_a_resealed_packet_is_refused(root):
    contract_packet(root)
    path = root / PACKET / "packet.md"
    text = path.read_bytes().replace(
        b"scope: {kind: workspace}", b"scope: {kind: project, project: scheduling}"
    )
    path.write_bytes(text)
    (root / PACKET / "seal").write_text(digest(text) + "\n")
    with pytest.raises(FormatError, match="scope"):
        confirm(root, PACKET)


def test_changed_selected_source_or_target_is_stale(root):
    contract_packet(root)
    before = (root / "WORKSPACE.md").read_bytes()
    (root / ACTIVITY).write_text((root / ACTIVITY).read_text() + "\nLater note.\n")
    with pytest.raises(FormatError, match="selected source changed since propose"):
        confirm(root, PACKET)
    assert (root / "WORKSPACE.md").read_bytes() == before
    preview = apply(root, PACKET, None, confirmed=False)
    assert any("selected source changed" in problem for problem in preview.problems)


def test_unrelated_sibling_edits_do_not_conflict(root, tmp_path):
    contract_packet(root)
    template = tmp_path / "template"
    initialize(template, "scheduling")
    os.rename(template / "projects/scheduling", root / "projects/scheduling")
    (root / "runs/drafts/other.md").write_text("unrelated draft\n")
    (root / "shared/other.txt").write_text("unrelated material\n")
    (root / "AGENTS.md").write_text((root / "AGENTS.md").read_text() + "\nLocal rule.\n")
    assert confirm(root, PACKET).status == "applied"


def test_occupied_target_is_refused(root):
    contract_packet(root)
    (root / RESOURCE).write_text("someone else's description\n")
    with pytest.raises(FormatError, match="occupied since propose"):
        confirm(root, PACKET)
    assert (root / RESOURCE).read_text() == "someone else's description\n"
    assert (root / "WORKSPACE.md").read_bytes() != examples()["charter"]


def test_changed_registered_material_is_refused(root):
    contract_packet(root)
    (root / TRACE / "trace.csv").write_text("arrival_us,service_us\n0,1\n")
    with pytest.raises(FormatError, match="material digest .* differs"):
        confirm(root, PACKET)
    assert not (root / RESOURCE).exists()


def registered(root):
    contract_packet(root)
    confirm(root, PACKET)
    return digest((root / RESOURCE).read_bytes())


TREE = "8a1e96927975330167f8c5bdd4c4fa142ed55b3f0f69249c143908b299fd7336"
PIN = f"[{{resource: synthetic-queue-trace, revision: 1, sha256: {TREE}}}]"


def test_pins_are_frozen_in_full_and_broken_pins_refused(root):
    registered(root)
    outcome = propose(root, write_input(root, FOCUS, pins=PIN))
    pin = outcome.loaded.packet.pins[0]
    assert pin["path"] == TRACE and pin["method"] == "tree-v1" and pin["sha256"] == TREE
    assert "pinned resource synthetic-queue-trace revision 1 (tree-v1 8a1e969279753301" in (
        outcome.loaded.body
    )
    (root / TRACE / "README.md").unlink()
    with pytest.raises(FormatError, match="broken pin synthetic-queue-trace revision 1"):
        confirm(root, outcome.loaded.directory)
    with pytest.raises(FormatError, match="material digest"):
        propose(root, write_input(root, FOCUS, pins=PIN, name="again.md"))


def test_revision_and_withdrawal_keep_history_and_stale_pins(root):
    first = registered(root)
    pinned = propose(root, write_input(root, FOCUS, pins=PIN, name="pinned.md"))
    revise = (
        "  - target: resource\n    resource: synthetic-queue-trace\n    action: revise\n"
        '    status: withdrawn\n    notes: "Superseded by a recorded trace."\n'
    )
    outcome = propose(root, write_input(root, revise))
    confirm(root, outcome.loaded.directory)
    text = (root / RESOURCE).read_text()
    assert "status: withdrawn" in text and "revision: 2" in text
    assert f"previous_sha256: {first}" in text and "## Notes\nSuperseded" in text
    before = (root / outcome.loaded.directory / "targets/1.md").read_bytes()
    assert before == (root / RESOURCE).read_bytes()
    # The earlier pin is now stale: the latest description is never substituted.
    with pytest.raises(FormatError, match="description revised since pinned"):
        confirm(root, pinned.loaded.directory)
    status = invoke("status", "--workspace", "--root", root)
    assert "synthetic-queue-trace | withdrawn | revision 2" in status.stdout


# Recovery: explicit incomplete state, forward-only, never over someone else's edit.


def crash_before(monkeypatch, target):
    """Fail the journal's publication write of ``target`` (a root-relative path)."""
    real = workspace_journal.write_atomic

    def write(path, data, *, replace=False):
        if Path(path).as_posix().endswith("/" + target):
            raise OSError("simulated crash")
        return real(path, data, replace=replace)

    monkeypatch.setattr(workspace_journal, "write_atomic", write)


@pytest.mark.parametrize("target", ["WORKSPACE.md", RESOURCE, f"{PACKET}/receipt.md"])
def test_interrupted_apply_is_incomplete_then_recovers_once(root, monkeypatch, target):
    contract_packet(root)
    other = propose(root, write_input(root, FOCUS))
    crash_before(monkeypatch, target)
    with pytest.raises(OSError, match="simulated crash"):
        confirm(root, PACKET, approval_text=APPROVAL, now=at("2026-11-04T10:20:00"))
    monkeypatch.undo()
    assert (root / workspace_journal.JOURNAL).is_dir()
    assert not (root / PACKET / "receipt.md").exists()
    status = invoke("status", "--workspace", "--root", root)
    assert status.exit_code == 1
    assert f"{PACKET} | change | incomplete" in status.stdout
    preview = invoke("workspace", "apply", "--root", root, "--draft", PACKET)
    assert "State: publication incomplete" in preview.stdout
    with pytest.raises(FormatError, match="incomplete workspace publication"):
        propose(root, write_input(root, FOCUS, name="other.md"))
    with pytest.raises(FormatError, match="incomplete workspace-change"):
        confirm(root, other.loaded.directory)

    result = confirm(root, PACKET, actor="Someone Else")
    assert result.status == "recovered"
    assert "ignored; recovery keeps the first confirmation by Tianchi YU" in result.problems[0]
    expected = examples()
    assert (root / "WORKSPACE.md").read_bytes() == expected["charter"]
    assert (root / RESOURCE).read_bytes() == expected["resource"]
    assert (root / PACKET / "receipt.md").read_bytes() == expected["receipt"]
    assert not (root / workspace_journal.JOURNAL).exists()
    assert confirm(root, PACKET).status == "replayed"


def test_crash_after_receipt_retires_the_journal_on_rerun(root, monkeypatch):
    contract_packet(root)

    def interrupted(repository):
        raise OSError("simulated crash before retire")

    monkeypatch.setattr(workspace_journal, "retire", interrupted)
    with pytest.raises(OSError):
        confirm(root, PACKET)
    monkeypatch.undo()
    assert (root / PACKET / "receipt.md").exists()
    assert (root / workspace_journal.JOURNAL).is_dir()
    assert confirm(root, PACKET).status == "recovered"
    assert not (root / workspace_journal.JOURNAL).exists()


def test_crash_after_journal_before_any_target(root, monkeypatch):
    contract_packet(root)
    monkeypatch.setattr(workspace_change, "finish", lambda repository: (_ for _ in ()).throw(
        OSError("simulated crash after the journal commit")
    ))  # fmt: skip
    with pytest.raises(OSError):
        confirm(root, PACKET)
    monkeypatch.undo()
    assert (root / "WORKSPACE.md").read_bytes() != examples()["charter"]
    assert confirm(root, PACKET).status == "recovered"
    assert (root / "WORKSPACE.md").read_bytes() == examples()["charter"]


def test_external_edit_during_recovery_is_preserved_not_rolled_back(root, monkeypatch):
    contract_packet(root)
    crash_before(monkeypatch, RESOURCE)
    with pytest.raises(OSError):
        confirm(root, PACKET)
    monkeypatch.undo()
    (root / "WORKSPACE.md").write_text("researcher's own edit\n")
    with pytest.raises(FormatError, match="changed outside this publication.*journal kept"):
        confirm(root, PACKET)
    assert (root / "WORKSPACE.md").read_text() == "researcher's own edit\n"
    assert (root / workspace_journal.JOURNAL).is_dir()
    assert not (root / RESOURCE).exists()


# Reject and derived dispositions.


def test_reject_records_a_final_disposition_only(root):
    contract_packet(root)
    before = contents(root)
    args = ("workspace", "reject", "--root", root, "--draft", PACKET, "--reason", "Not yet.")
    assert invoke(*args, "--confirmed-by", "R").exit_code == 1  # no --confirm
    result = invoke(*args, "--confirmed-by", "R", "--confirm")
    assert result.exit_code == 0, result.output
    assert "Disposition: rejected by R" in result.stdout
    assert contents(root) == before
    assert invoke(*args, "--confirmed-by", "R", "--confirm").exit_code == 0  # replay
    with pytest.raises(FormatError, match="rejected by R .Not yet..; propose anew"):
        confirm(root, PACKET)
    with pytest.raises(FormatError, match="superseded by"):
        reject(root, FIRST, "Old.", "R")
    status = invoke("status", "--workspace", "--root", root, "--verbose")
    assert f"{PACKET} | change | rejected" in status.stdout
    assert f"{FIRST} | change | superseded" in status.stdout


def test_applied_packet_cannot_be_rejected(root):
    contract_packet(root)
    confirm(root, PACKET)
    with pytest.raises(FormatError, match="already applied"):
        reject(root, PACKET, "Changed my mind.", "R")


def test_superseded_packet_preview_names_its_successor(root):
    contract_packet(root)
    preview = apply(root, FIRST, None, confirmed=False)
    assert preview.problems[0].startswith(f"superseded by {PACKET}")
    with pytest.raises(FormatError, match=f"superseded by {PACKET}"):
        confirm(root, FIRST)


def test_status_notices_edits_outside_a_receipt_but_not_handoff_fields(root):
    registered(root)
    charter = root / "WORKSPACE.md"
    original = charter.read_text()
    charter.write_text(original.replace("next_step: null", 'next_step: "Plan a measurement."'))
    status = invoke("status", "--workspace", "--root", root)
    assert status.exit_code == 0, status.output
    assert "edited outside a receipt" not in status.stdout
    charter.write_text(original.replace("single serving node", "single node"))
    (root / RESOURCE).write_text((root / RESOURCE).read_text().replace("tiny", "small"))
    status = invoke("status", "--workspace", "--root", root)
    assert status.exit_code == 0, status.output
    assert "Notice: WORKSPACE.md: differs from its last receipt" in status.stdout
    assert f"Notice: {RESOURCE}: differs from its last receipt" in status.stdout
    assert (
        "Direction: Understand how request scheduling policy affects tail latency on a single node"
        in (status.stdout)
    )


def test_load_rejects_a_receipt_for_another_seal(root):
    contract_packet(root)
    confirm(root, PACKET)
    receipt = root / PACKET / "receipt.md"
    receipt.write_text(receipt.read_text().replace("24c921f8", "00000000"))
    with pytest.raises(FormatError, match="does not belong to this sealed packet"):
        confirm(root, PACKET)
    assert load(root, PACKET).directory == PACKET
