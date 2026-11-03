"""Native continuity remains conditional on durable, validated file provenance."""

import pytest

from toulmin.core.atomic import digest
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectId
from toulmin.core.repository import Repository
from toulmin.protocols import discussion
from toulmin.protocols.review import ReviewOutcome

CONFIG = "a" * 64


def begin(root, message="Current message", **kwargs):
    return discussion.begin_turn(
        root, "demo", message, "local", "researcher", configuration=CONFIG, **kwargs
    )


def finish(root, turn, *, session="native-1", failure=None, text="Original answer"):
    return discussion.finish_turn(
        root, "demo", turn.id, ReviewOutcome(text, "reported", session, 1, failure)
    )


def directory(root, turn):
    return root / "projects/demo/runs/conversations/main" / turn.id


def plan(root, turn):
    return discussion.get_continuation(root, "demo", turn.id)


def test_two_turn_delta_retains_anchor_and_exact_prompt(workbench):
    first = begin(workbench, "Inherited question")
    first_plan = plan(workbench, first)
    assert (first_plan.mode, first_plan.reason, first_plan.resume_id) == (
        "fresh",
        "first-turn",
        None,
    )
    workspace = discussion.prepare_research_workspace(workbench, "demo", first.id)
    workspace.joinpath("paper.txt").write_text("Original download")
    finish(workbench, first)
    (workbench / "projects/demo/brief.md").write_text("# Authoritative current brief\n")
    preview = discussion.preview_context(workbench, "demo", configuration=CONFIG)
    second = begin(workbench)
    current = plan(workbench, second)
    assert (current.mode, current.reason, current.resume_id) == ("resume", "resume", "native-1")
    assert current.anchor == first.id and current.previous == first.id
    assert current.workspace == workspace
    assert current.archive_directory == directory(workbench, second)
    assert discussion.prepare_research_workspace(workbench, "demo", second.id) == workspace
    assert not directory(workbench, second).joinpath("research").exists()
    assert workspace.joinpath("paper.txt").read_text() == "Original download"
    prompt = discussion.get_turn_prompt(workbench, "demo", second.id)
    assert prompt.startswith(preview)
    assert "Inherited question" not in prompt and "Original answer" not in prompt
    assert "Authoritative current brief" in prompt and "Current message" in prompt
    assert first.archive in prompt and "native-1" in prompt
    assert str(directory(workbench, second) / "research") not in prompt
    assert prompt.count(str(workspace)) == 2
    task = decode(directory(workbench, second).joinpath("task.md").read_bytes())
    assert task.header["prompt_sha256"] == digest(prompt.encode())
    completed = finish(workbench, second, session="native-fork")
    assert completed.session_id == "native-fork"
    run = Repository(workbench).load("demo", ObjectId.parse(completed.run))
    assert "Requested session: native-1" in run.body
    assert "Reported session: native-fork" in run.body
    assert first.archive in run.body
    assert (workbench / completed.archive / "continuation.md").read_bytes() == (
        directory(workbench, second) / "continuation.md"
    ).read_bytes()
    third = begin(workbench)
    assert plan(workbench, third).resume_id == "native-fork"
    assert plan(workbench, third).anchor == first.id


@pytest.mark.parametrize(
    ("variant", "reason"),
    [
        ("failed", "previous-failed"),
        ("no-session", "previous-no-session"),
        ("legacy", "legacy-session"),
        ("recovered", "previous-recovered"),
        ("changed", "configuration-changed"),
        ("fresh", "explicit-fresh"),
    ],
)
def test_ineligible_previous_turn_forces_full_fresh_context(workbench, variant, reason):
    first = (
        discussion.begin_turn(workbench, "demo", "Original question", "local", "researcher")
        if variant == "legacy"
        else begin(workbench, "Original question")
    )
    if variant == "recovered":
        discussion.recover_turn(workbench, "demo", first.id, "researcher")
    else:
        finish(
            workbench,
            first,
            failure="cancelled" if variant == "failed" else None,
            session=None if variant == "no-session" else "native-1",
        )
    if variant == "changed":
        second = discussion.begin_turn(
            workbench, "demo", "Next", "changed-model", "researcher", configuration="b" * 64
        )
    else:
        second = begin(workbench, fresh=variant == "fresh")
    current = plan(workbench, second)
    assert (current.mode, current.reason, current.resume_id) == ("fresh", reason, None)
    assert current.anchor == second.id and current.previous == first.id
    assert "Original question" in discussion.get_turn_prompt(workbench, "demo", second.id)


def test_interleaved_brief_and_old_pending_draft_are_supplied(workbench):
    first = begin(workbench, "Do not repeat old exploration")
    finish(workbench, first)
    brief = discussion.begin_turn(
        workbench,
        "demo",
        "Interleaved brief request",
        "local",
        "researcher",
        "brief",
        configuration=CONFIG,
    )
    finish(workbench, brief, text="# Interleaved proposal\n")
    assert plan(workbench, brief) is None
    discussion.save_proposal_draft(workbench, "demo", brief.id, "# Edited current draft\n")
    second = begin(workbench)
    prompt = discussion.get_turn_prompt(workbench, "demo", second.id)
    assert "Interleaved brief request" in prompt and "Interleaved proposal" in prompt
    assert "Edited current draft" in prompt and "UNCONFIRMED" in prompt
    assert "Do not repeat old exploration" not in prompt
    assert plan(workbench, second).previous == first.id
    finish(workbench, second)
    third = begin(workbench)
    prompt = discussion.get_turn_prompt(workbench, "demo", third.id)
    assert "Interleaved brief request" not in prompt
    assert "Edited current draft" in prompt


@pytest.mark.parametrize("action", ["apply", "dismiss"])
def test_proposal_disposition_clears_draft_inherited_by_native_session(workbench, action):
    first = begin(workbench)
    finish(workbench, first)
    brief = discussion.begin_turn(
        workbench, "demo", "Propose a brief", "local", "researcher", "brief"
    )
    finish(workbench, brief, text="# Proposed brief\nA cautious suggestion.\n")
    second = begin(workbench)
    assert "UNCONFIRMED WORKING BRIEF" in discussion.get_turn_prompt(workbench, "demo", second.id)
    finish(workbench, second)
    if action == "apply":
        discussion.apply_proposal(
            workbench, "demo", brief.id, "# Proposed brief\nA cautious suggestion.\n", "researcher"
        )
    else:
        discussion.dismiss_proposal(workbench, "demo", brief.id, "researcher")
    third = begin(workbench)
    prompt = discussion.get_turn_prompt(workbench, "demo", third.id)
    assert plan(workbench, third).mode == "resume"
    assert "No pending proposal; earlier unconfirmed drafts are inactive" in prompt
    assert "saved brief above is authoritative" in prompt
    assert "UNCONFIRMED WORKING BRIEF" not in prompt


def test_resume_bypasses_only_full_rebuild_limit(workbench):
    first = begin(workbench, "Large inherited input " + "x" * 60_000)
    finish(workbench, first, text="y" * 60_000)
    second = begin(workbench, "Continue")
    assert plan(workbench, second).mode == "resume"
    finish(workbench, second)
    with pytest.raises(FormatError, match="submitted request exceeds"):
        begin(workbench, "z" * 100_001)
    with pytest.raises(FormatError, match="fresh file-context rebuild"):
        begin(workbench, fresh=True)
    with pytest.raises(FormatError, match="no history was truncated"):
        discussion.preview_context(workbench, "demo")


def test_unrecovered_orphan_is_not_automatically_retried(workbench):
    first = begin(workbench)
    with pytest.raises(FormatError, match="unresolved turn"):
        begin(workbench)
    assert discussion.load_discussion(workbench, "demo").turns[0].status == "running"
    assert plan(workbench, first).mode == "fresh"
    assert not directory(workbench, first).joinpath("outcome.md").exists()


def test_recovered_success_is_not_native_resume_eligible(workbench, monkeypatch):
    first = begin(workbench)
    original = discussion._write

    def crash(repository, relative, document, replace=False):
        if relative.endswith("/task.md") and replace:
            raise OSError("crash after outcome")
        return original(repository, relative, document, replace)

    with monkeypatch.context() as patch:
        patch.setattr(discussion, "_write", crash)
        with pytest.raises(OSError, match="crash after outcome"):
            finish(workbench, first)
    recovered = discussion.recover_turn(workbench, "demo", first.id, "researcher")
    assert recovered.status == "completed" and recovered.session_id == "native-1"
    second = begin(workbench)
    assert plan(workbench, second).reason == "previous-recovered"


def test_manifest_and_task_publish_together_before_invocation(workbench, monkeypatch):
    original = discussion.os.rename

    def inspect_staging(source, destination):
        assert source.joinpath("task.md").is_file()
        assert source.joinpath("prompt.md").is_file()
        assert source.joinpath("continuation.md").is_file()
        assert not destination.exists()
        assert not source.joinpath("outcome.md").exists()
        return original(source, destination)

    monkeypatch.setattr(discussion.os, "rename", inspect_staging)
    first = begin(workbench)
    assert plan(workbench, first).mode == "fresh"


def test_manifest_write_failure_never_publishes_partial_request(workbench, monkeypatch):
    original = discussion._write

    def fail_manifest(repository, relative, document, replace=False):
        if relative.endswith("/continuation.md"):
            raise OSError("manifest unavailable")
        return original(repository, relative, document, replace)

    monkeypatch.setattr(discussion, "_write", fail_manifest)
    with pytest.raises(OSError, match="manifest unavailable"):
        begin(workbench)
    assert discussion.load_discussion(workbench, "demo").turns == ()
    assert not list((workbench / "projects/demo/runs/conversations/main").iterdir())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("anchor", "../../brief.md"),
        ("previous", "bad"),
        ("configuration", "secret-token"),
        ("mode", "retry"),
        ("reason", ["resume"]),
        ("session_id", "wrong-session"),
        ("anchor", None),
    ],
)
def test_corrupt_continuation_is_refused_read_only(workbench, field, value):
    first = begin(workbench)
    path = directory(workbench, first) / "continuation.md"
    doc = decode(path.read_bytes())
    doc.header[field] = value
    path.write_bytes(encode(doc))
    task_path = directory(workbench, first) / "task.md"
    task = decode(task_path.read_bytes())
    task.header["continuation_sha256"] = digest(path.read_bytes())
    task_path.write_bytes(encode(task))
    before = path.read_bytes()
    with pytest.raises(FormatError):
        plan(workbench, first)
    assert path.read_bytes() == before


def test_continuation_and_inherited_workspace_symlinks_are_refused(workbench, tmp_path):
    first = begin(workbench)
    finish(workbench, first)
    second = begin(workbench)
    outside = tmp_path / "outside"
    outside.mkdir()
    directory(workbench, first).joinpath("research").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FormatError, match="symlinks forbidden"):
        discussion.get_research_workspace(workbench, "demo", second.id)
    with pytest.raises(FormatError, match="symlinks forbidden"):
        discussion.prepare_research_workspace(workbench, "demo", second.id)
    directory(workbench, first).joinpath("research").unlink()
    manifest = directory(workbench, second) / "continuation.md"
    external = outside / "manifest.md"
    external.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(external)
    with pytest.raises(FormatError, match="symlinks forbidden"):
        plan(workbench, second)


def test_manifest_references_cannot_skip_latest_explorer(workbench):
    first = begin(workbench)
    finish(workbench, first)
    second = begin(workbench)
    finish(workbench, second)
    third = begin(workbench)
    path = directory(workbench, third) / "continuation.md"
    doc = decode(path.read_bytes())
    doc.header["previous"] = first.id
    path.write_bytes(encode(doc))
    task_path = directory(workbench, third) / "task.md"
    task = decode(task_path.read_bytes())
    task.header["continuation_sha256"] = digest(path.read_bytes())
    task_path.write_bytes(encode(task))
    with pytest.raises(FormatError, match="most recent earlier"):
        plan(workbench, third)


def test_new_metadata_does_not_change_legacy_read_behavior(workbench):
    first = discussion.begin_turn(workbench, "demo", "Legacy message", "local", "researcher")
    finish(workbench, first)
    assert plan(workbench, first) is None
    assert "Legacy message" in discussion.preview_context(workbench, "demo")
    assert "Legacy message" in discussion.preview_context(workbench, "demo", configuration=CONFIG)


@pytest.mark.parametrize("configuration", ["plaintext", "A" * 64, "a" * 63, 1, []])
def test_invalid_configuration_writes_nothing(workbench, configuration):
    with pytest.raises(FormatError, match="fingerprint"):
        discussion.begin_turn(
            workbench, "demo", "Question", "local", "researcher", configuration=configuration
        )
    assert not (workbench / "projects/demo/runs/conversations").exists()


@pytest.mark.parametrize("mutation", ["delete", "modify", "unmark"])
def test_native_manifest_cannot_silently_become_stateless(workbench, mutation):
    first = begin(workbench)
    finish(workbench, first)
    second = begin(workbench)
    path = directory(workbench, second) / "continuation.md"
    if mutation == "delete":
        path.unlink()
    elif mutation == "modify":
        doc = decode(path.read_bytes())
        doc.header["session_id"] = "changed-session"
        path.write_bytes(encode(doc))
    else:
        task_path = directory(workbench, second) / "task.md"
        task = decode(task_path.read_bytes())
        del task.header["continuation_sha256"]
        task_path.write_bytes(encode(task))
    with pytest.raises(FormatError, match="continuation"):
        plan(workbench, second)
    with pytest.raises(FormatError, match="continuation"):
        finish(workbench, second)
    assert not directory(workbench, second).joinpath("outcome.md").exists()


def test_loading_and_context_validate_history_with_linear_task_reads(workbench, monkeypatch):
    for index in range(8):
        turn = begin(workbench, f"Turn {index}")
        finish(workbench, turn)
    count = 0
    original = discussion._task

    def count_reads(*args, **kwargs):
        nonlocal count
        count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(discussion, "_task", count_reads)
    assert len(discussion.load_discussion(workbench, "demo").turns) == 8
    assert count <= 2 * 8
    count = 0
    assert "NATIVE CONTINUATION" in discussion.preview_context(
        workbench, "demo", configuration=CONFIG
    )
    assert count <= 2 * 8 + 3
