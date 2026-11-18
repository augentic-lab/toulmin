"""R3: workspace-owned v2 receipts participate in handoff and fresh context restoration."""

import json

import pytest

from tests.acceptance.test_wo5_compatibility import legacy_workspace
from tests.acceptance.wo_support import (
    ACTOR,
    OVERVIEW,
    child_input,
    disposition,
    onboard_a,
    propose,
    repository,
    tree,
)
from toulmin.application.aoe import AoEWorkspace
from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.protocols import workspace_handoff
from toulmin.protocols.workspace_change import applied_receipt
from toulmin.protocols.workspace_context import workspace_research


def summary(root, receipts):
    path = root / "runs/drafts/review-summary.md"
    path.write_text(
        "---\nschema_version: 1\nkind: workspace-handoff-input\n"
        + f"confirmed_changes: {json.dumps(receipts)}\n"
        + "next_step: Continue the smallest measurement.\n"
        + "---\n## Done\nReviewed workspace sources.\n\n## Confirmed changes\n"
        "Only the cited source/understanding changes were confirmed.\n\n"
        "## Pending ideas\nLatency remains unconfirmed.\n\n## Open questions\nWhich trace next?\n"
    )
    return path.relative_to(root).as_posix()


def packet_for(wo, operation):
    if operation == "catalog-upgrade":
        legacy_workspace(wo)
        return propose(wo.root, "source", "upgrade")
    initial = onboard_a(wo.root, wo.source)
    if operation == "onboarding":
        return initial
    if operation == "understanding-update":
        body = wo.tmp / "overview-body.md"
        body.write_text(OVERVIEW)
        return propose(
            wo.root,
            "overview",
            "--workspace",
            "--source",
            "source-main",
            "--input",
            body,
            "--rationale",
            "Reviewed checkpoint",
        )
    if operation == "source-change":
        other = repository(wo.tmp / "other-code")
        return propose(
            wo.root,
            "source",
            "add",
            other,
            "--workspace",
            "--register-source",
            "source-next",
            "--rationale",
            "New reference",
        )
    return propose(
        wo.root,
        "project",
        "propose",
        "latency",
        "--input",
        child_input(wo.root, "latency"),
        "--source",
        "source-main",
    )


@pytest.mark.parametrize(
    "operation",
    ["onboarding", "understanding-update", "source-change", "child-derive", "catalog-upgrade"],
)
def test_all_workspace_v2_receipt_families_can_be_cited_and_discovered(wo, operation):
    packet = packet_for(wo, operation)
    if not (packet / "receipt.md").exists():
        disposition(wo.root, packet)
    receipt = (packet / "receipt.md").relative_to(wo.root).as_posix()
    before = tree(wo.root)
    assert applied_receipt(wo.root, receipt).disposition == "applied"
    assert receipt in workspace_handoff.uncited_receipts(wo.root, ())
    assert receipt not in workspace_handoff.uncited_receipts(wo.root, (receipt,))
    assert tree(wo.root) == before
    drafted = workspace_handoff.draft(wo.root, summary(wo.root, [receipt]))
    assert drafted.loaded.draft.confirmed_changes == (receipt,)
    applied = workspace_handoff.apply(wo.root, drafted.loaded.path, ACTOR, confirmed=True)
    assert applied.status == "applied"
    assert workspace_handoff.latest_handoff(wo.root).record.draft.confirmed_changes == (receipt,)
    assert workspace_handoff.uncited_receipts(wo.root, ()) == []
    state = workspace_research(wo.root)
    assert not state.errors and applied.record in state.context_files


@pytest.mark.parametrize("damage", ["rejected", "seal", "record", "effects", "after-image"])
def test_invalid_v2_receipts_cannot_be_cited_or_reported_as_uncited_applied(wo, damage):
    packet = propose(wo.root, "onboard", wo.source, "--init", "--register-source", "source-main")
    disposition(wo.root, packet, reject=damage == "rejected")
    receipt = (packet / "receipt.md").relative_to(wo.root).as_posix()
    if damage == "seal":
        (packet / "seal").write_text("0" * 64 + "\n")
    elif damage in {"record", "effects"}:
        doc = decode((packet / "receipt.md").read_bytes())
        if damage == "record":
            doc.header["record_sha256"] = "0" * 64
        else:
            doc.header["results"] = []
        (packet / "receipt.md").write_bytes(encode(doc))
    elif damage == "after-image":
        data = json.loads((packet / "packet.md").read_bytes())
        path = wo.root / data["images"][0]["after_image"]
        path.write_bytes(path.read_bytes() + b"tampered")
    path = summary(wo.root, [receipt])
    before = tree(wo.root)
    with pytest.raises(FormatError):
        applied_receipt(wo.root, receipt)
    with pytest.raises(FormatError):
        workspace_handoff.draft(wo.root, path)
    assert receipt not in workspace_handoff.uncited_receipts(wo.root, ())
    assert tree(wo.root) == before and not (wo.root / ".workspace-pending").exists()


def test_fresh_source_backed_context_restores_applied_handoff_with_v2_confirmation(wo, native):
    packet = onboard_a(wo.root, wo.source)
    receipt = (packet / "receipt.md").relative_to(wo.root).as_posix()
    drafted = workspace_handoff.draft(wo.root, summary(wo.root, [receipt]))
    applied = workspace_handoff.apply(wo.root, drafted.loaded.path, ACTOR, confirmed=True)
    view = AoEWorkspace(wo.root, None, native).open(codex_sandbox="inherit")
    assert view.binding.version == 4
    texts = "\n".join(path.read_text() for path in view.context_path.parent.rglob("*.md"))
    assert receipt in texts and "Which trace next?" in texts
    assert applied.record in view.research.context_files
    AoEWorkspace(wo.root, None, native).acknowledge(view.binding.token)
    assert workspace_handoff.latest_handoff(wo.root).record.draft.confirmed_changes == (receipt,)


def test_receipt_damage_after_draft_prevents_handoff_apply_without_recovery(wo):
    packet = onboard_a(wo.root, wo.source)
    receipt = (packet / "receipt.md").relative_to(wo.root).as_posix()
    drafted = workspace_handoff.draft(wo.root, summary(wo.root, [receipt]))
    doc = decode((packet / "receipt.md").read_bytes())
    doc.header["results"] = []
    (packet / "receipt.md").write_bytes(encode(doc))
    before = tree(wo.root)
    assert workspace_handoff.check(wo.root, drafted.loaded)
    with pytest.raises(FormatError):
        workspace_handoff.apply(wo.root, drafted.loaded.path, ACTOR, confirmed=True)
    assert tree(wo.root) == before and not (wo.root / ".workspace-pending").exists()


def test_damaged_cited_receipt_blocks_fresh_context_after_applied_handoff(wo, native):
    packet = onboard_a(wo.root, wo.source)
    receipt = (packet / "receipt.md").relative_to(wo.root).as_posix()
    drafted = workspace_handoff.draft(wo.root, summary(wo.root, [receipt]))
    workspace_handoff.apply(wo.root, drafted.loaded.path, ACTOR, confirmed=True)
    doc = decode((packet / "receipt.md").read_bytes())
    doc.header["record_sha256"] = "0" * 64
    (packet / "receipt.md").write_bytes(encode(doc))
    before = tree(wo.root)
    assert workspace_research(wo.root).errors
    with pytest.raises(FormatError):
        AoEWorkspace(wo.root, None, native).open(codex_sandbox="inherit")
    assert tree(wo.root) == before and not native.created and not native.sent
