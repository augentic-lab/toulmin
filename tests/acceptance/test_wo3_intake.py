"""WO3 acceptance: reviewed A/B/C, immutable pins and forward-only publication.

Contract: docs/workspace-onboarding-contract.md, W03-A through W03-schema.
No test result in this module constitutes live or researcher usability acceptance.
"""

import json
from pathlib import Path

import pytest

from tests.acceptance.wo_support import (
    ACTOR,
    OVERVIEW,
    WS,
    canonical,
    catalog,
    child,
    child_input,
    definition_sha,
    disposition,
    git,
    invoke,
    onboard_a,
    outer_packets,
    propose,
    repository,
    role_map,
    sha,
    tree,
    v2_workspace,
)
from toulmin.core import workspace_journal
from toulmin.core.codec import decode

ENVELOPE_KEYS = {
    "schema_version",
    "kind",
    "operation",
    "scope",
    "created",
    "origin",
    "mode",
    "project",
    "creation",
    "catalog_version",
    "inputs",
    "preconditions",
    "images",
    "inventories",
    "source_actions",
    "association_changes",
    "notes",
    "rationale",
}
PIN_KEYS = {
    "source",
    "catalog_sha256",
    "definition_sha256",
    "identity",
    "snapshot",
    "snapshot_sha256",
    "head",
}


def test_a_requires_no_project_and_seals_exact_portable_overview_before_apply(wo):
    before = tree(wo.source)
    packet = propose(wo.root, "onboard", wo.source, "--init", "--register-source", "source-main")
    raw = (packet / "packet.md").read_bytes()
    data = json.loads(raw)
    assert raw == canonical(data)
    assert set(data) == ENVELOPE_KEYS
    assert data["mode"] == "A" and data["scope"] == WS
    assert data["project"] is None and data["creation"] is None
    assert data["catalog_version"] == 2 and data["operation"] == "onboarding"
    assert not (wo.root / "sources.toml").exists()
    assert not (wo.root / "overview.md").exists()
    assert [p for p in (wo.root / "projects").iterdir() if p.is_dir()] == []
    overview = next(i for i in data["images"] if i["path"] == "overview.md")
    frozen = (wo.root / overview["after_image"]).read_bytes()
    doc = decode(frozen, "sealed overview")
    assert doc.header["receipt"] == packet.relative_to(wo.root).as_posix() + "/receipt.md"
    assert doc.header["scope"] == WS and doc.header["revision"] == 1
    assert doc.header["coverage"] and doc.header["limits"] and doc.header["supersedes"] is None
    pin = doc.header["sources"][0]
    assert set(pin) == PIN_KEYS and pin["source"] == "source-main"
    assert pin["head"] == git(wo.source, "rev-parse", "HEAD")
    assert sha((wo.root / pin["snapshot"]).read_bytes()) == pin["snapshot_sha256"]
    before_preview = tree(wo.root)
    disposition(wo.root, packet, confirm=False)
    assert tree(wo.root) == before_preview
    disposition(wo.root, packet)
    assert (wo.root / "overview.md").read_bytes() == frozen
    assert [p for p in (wo.root / "projects").iterdir() if p.is_dir()] == []
    assert role_map(wo.root) == {("workspace", None, "source-main"): "working"}
    definition = catalog(wo.root)["definitions"][0]
    assert pin["definition_sha256"] == definition_sha(definition)
    assert pin["catalog_sha256"] == sha((wo.root / "sources.toml").read_bytes())
    for path in (wo.root / "runs").rglob("*"):
        if path.is_file():
            assert str(wo.source).encode() not in path.read_bytes(), path
    assert tree(wo.source) == before
    receipt = decode((packet / "receipt.md").read_bytes(), "receipt").header
    assert receipt["schema_version"] == 1 and receipt["kind"] == "workspace-receipt"
    assert receipt["record_sha256"] == sha(raw) and receipt["actor"] == ACTOR
    assert receipt["approval_text"] and receipt["reason"] is None
    assert any(
        r["path"] == "overview.md" and r["after_sha256"] == sha(frozen) for r in receipt["results"]
    )
    stable = tree(wo.root)
    disposition(wo.root, packet, actor="Another operator")
    assert tree(wo.root) == stable


def test_a_rejection_replay_is_final_and_leaves_only_skeleton_and_archive(wo):
    packet = propose(wo.root, "onboard", wo.source, "--init")
    disposition(wo.root, packet, reject=True)
    stable = tree(wo.root)
    disposition(wo.root, packet, reject=True, actor="Different actor")
    assert tree(wo.root) == stable
    disposition(wo.root, packet, code=1)
    for name in ("sources.toml", "tools/sources.local.toml", "overview.md"):
        assert not (wo.root / name).exists()
    assert not [p for p in (wo.root / "projects").iterdir() if p.is_dir()]
    receipt = decode((packet / "receipt.md").read_bytes(), "receipt").header
    assert receipt["disposition"] == "rejected" and receipt["results"] == []
    assert receipt["actor"] == ACTOR and receipt["approval_text"] is None


def test_b_creates_exactly_requested_child_two_receipts_and_no_native_launch(wo, native):
    path = child_input(wo.tmp / "external-drafts", "latency")
    packet = propose(
        wo.root,
        "onboard",
        wo.source,
        "--init",
        "--project",
        "latency",
        "--project-input",
        path,
        "--register-source",
        "source-main",
    )
    data = json.loads((packet / "packet.md").read_bytes())
    creation = wo.root / data["creation"]["path"]
    marker = creation / "onboarding"
    assert marker.read_bytes() == packet.relative_to(wo.root).as_posix().encode()
    assert data["creation"]["seal"] == (creation / "seal").read_text().strip()
    for key in ("inputs", "preconditions"):
        assert {
            "path": marker.relative_to(wo.root).as_posix(),
            "sha256": sha(marker.read_bytes()),
        } in data[key]
    assert not (wo.root / "projects/latency").exists()
    disposition(wo.root, packet)
    assert [p.name for p in (wo.root / "projects").iterdir() if p.is_dir()] == ["latency"]
    assert len(catalog(wo.root)["definitions"]) == 1
    assert role_map(wo.root) == {
        ("workspace", None, "source-main"): "working",
        ("project", "latency", "source-main"): "working",
    }
    for receipt in (packet / "receipt.md", creation / "receipt.md"):
        assert decode(receipt.read_bytes(), str(receipt)).header["actor"] == ACTOR
    charter = decode((wo.root / "projects/latency/PROJECT.md").read_bytes(), "charter")
    assert charter.header["stage"] == "explore" and charter.header["recent_decisions"] == []
    assert "fixed local trace" in (wo.root / "projects/latency/brief.md").read_text()
    assert not native.created and not native.sent
    assert not list((wo.root / "projects/latency/claims").glob("*.md"))
    stable = tree(wo.root)
    disposition(wo.root, packet)
    assert tree(wo.root) == stable


@pytest.mark.parametrize("old_children", [(), ("first", "second")])
@pytest.mark.parametrize("new_source", [False, True])
def test_c_adds_one_child_and_preserves_all_old_roles_context_and_trees(
    wo, old_children, new_source
):
    onboard_a(wo.root, wo.source)
    for name in old_children:
        child(wo.root, name)
        (wo.root / f"projects/{name}/runs/notebook.md").write_text("Private old history.\n")
    old = {name: tree(wo.root / f"projects/{name}") for name in old_children}
    context = {name: (wo.root / name).read_bytes() for name in ("WORKSPACE.md", "overview.md")}
    local = (wo.root / "tools/sources.local.toml").read_bytes()
    source = repository(wo.tmp / "distinct") if new_source else wo.source
    flags = ["--register-source", "source-second"] if new_source else ["--source-id", "source-main"]
    path = child_input(wo.root, "latency")
    packet = propose(
        wo.root, "onboard", source, "--project", "latency", "--project-input", path, *flags
    )
    data = json.loads((packet / "packet.md").read_bytes())
    assert data["mode"] == "C" and data["notes"] is not None
    assert not {"WORKSPACE.md", "overview.md"} & {i["path"] for i in data["images"]}
    disposition(wo.root, packet)
    assert set(p.name for p in (wo.root / "projects").iterdir() if p.is_dir()) == {
        *old_children,
        "latency",
    }
    for name, contents in old.items():
        assert tree(wo.root / f"projects/{name}") == contents
    for name, raw in context.items():
        assert (wo.root / name).read_bytes() == raw
    assert role_map(wo.root)[("workspace", None, "source-main")] == "working"
    if new_source:
        assert len(catalog(wo.root)["definitions"]) == 2
        assert role_map(wo.root)[("workspace", None, "source-second")] == "reference"
    else:
        assert len(catalog(wo.root)["definitions"]) == 1
        assert (wo.root / "tools/sources.local.toml").read_bytes() == local
        assert not any(i["path"] == "tools/sources.local.toml" for i in data["images"])


@pytest.mark.parametrize("mode", ["A", "B", "C"])
def test_work_at_uses_target_in_exact_scope_without_copy_or_implicit_workspace_reselection(
    wo, mode
):
    target = repository(wo.tmp / "target")
    if mode == "C":
        onboard_a(wo.root, wo.source)
    flags = [] if mode == "C" else ["--init"]
    if mode != "A":
        flags += [
            "--project",
            "latency",
            "--project-input",
            child_input(wo.tmp / "inputs", "latency"),
        ]
    source = wo.source
    packet = propose(
        wo.root,
        "onboard",
        source,
        *flags,
        "--work-at",
        target,
        "--source-id" if mode == "C" else "--register-source",
        "source-main",
        "--register-working-source",
        "source-target",
    )
    before = tree(source), tree(target)
    disposition(wo.root, packet)
    roles = role_map(wo.root)
    if mode == "C":
        assert roles[("workspace", None, "source-main")] == "working"
        assert roles[("workspace", None, "source-target")] == "reference"
    else:
        assert roles[("workspace", None, "source-main")] == "reference"
        assert roles[("workspace", None, "source-target")] == "working"
    if mode != "A":
        assert roles[("project", "latency", "source-main")] == "reference"
        assert roles[("project", "latency", "source-target")] == "working"
    assert (tree(source), tree(target)) == before


@pytest.mark.parametrize("state", ["healthy", "empty", "corrupt", "staged"])
def test_duplicate_child_refuses_before_packet_or_source_registration(wo, state):
    v2_workspace(wo.root, wo.source)
    if state == "healthy":
        child(wo.root, "latency")
    elif state == "staged":
        # An interrupted child publication reserves the requested name even though
        # its final directory is still absent.
        from toulmin.core.repository import Repository

        intent = workspace_journal.Intent(
            "project-create",
            "runs/fixture/packet.md",
            "a" * 64,
            ACTOR,
            "2026-11-18T10:00:00Z",
            "Fixture operator approval",
            (workspace_journal.Image("projects/latency/PROJECT.md", None, b"staged fixture"),),
            "projects/.creating-" + "a" * 32,
        )
        workspace_journal.prepare(Repository(wo.root), intent)
        (wo.root / intent.staging).mkdir()
    else:
        folder = wo.root / "projects/latency"
        folder.mkdir()
        if state == "corrupt":
            (folder / "PROJECT.md").write_text("damaged\n")
    before = tree(wo.root)
    invoke("onboard", wo.source, "--root", wo.root, "--project", "latency", code=1)
    assert tree(wo.root) == before


@pytest.mark.parametrize(
    "case,code",
    [
        ("no-root", 2),
        ("missing-no-init", 1),
        ("empty-no-init", 1),
        ("unrelated", 1),
        ("initialized-init", 1),
        ("existing-no-project", 2),
    ],
)
def test_invalid_intake_root_intent_never_mutates(wo, monkeypatch, case, code):
    from toulmin.cli.initialize import initialize_workspace

    args = ["onboard", wo.source]
    if case == "no-root":
        monkeypatch.chdir(wo.tmp)
        args += ["--init"]
    else:
        args += ["--root", wo.root]
    if case == "empty-no-init":
        wo.root.mkdir()
    elif case == "unrelated":
        wo.root.mkdir()
        (wo.root / "keep.txt").write_text("Unrelated content.\n")
        args += ["--init"]
    elif case in {"initialized-init", "existing-no-project"}:
        initialize_workspace(wo.root)
        if case == "initialized-init":
            args += ["--init"]
    before = tree(wo.tmp)
    invoke(*args, code=code)
    assert tree(wo.tmp) == before


@pytest.mark.parametrize("change", ["HEAD", "dirty", "checkout", "catalog", "charter"])
def test_first_apply_revalidates_source_and_every_read_baseline(wo, change):
    packet = propose(wo.root, "onboard", wo.source, "--init")
    if change == "HEAD":
        git(
            wo.source,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "New head",
        )
    elif change == "dirty":
        (wo.source / "main.py").write_text("print('changed')\n")
    elif change == "checkout":
        wo.source.rename(wo.tmp / "saved-source")
        repository(wo.source)
    elif change == "catalog":
        (wo.root / "sources.toml").write_text(
            "schema_version = 2\ndefinitions = []\nassociations = []\n"
        )
    else:
        p = wo.root / "WORKSPACE.md"
        p.write_bytes(p.read_bytes() + b"\nExternal charter edit.\n")
    before = tree(wo.root)
    disposition(wo.root, packet, code=1)
    assert tree(wo.root) == before
    assert not (wo.root / "overview.md").exists() and not (packet / "receipt.md").exists()


@pytest.mark.parametrize("target", ["seal", "inventory", "after", "input"])
def test_tampered_packet_dependency_is_preserved_and_refused(wo, target):
    body = wo.tmp / "overview-input.md"
    body.write_text(OVERVIEW)
    packet = propose(wo.root, "onboard", wo.source, "--init", "--overview", body)
    data = json.loads((packet / "packet.md").read_bytes())
    if target == "inventory":
        path = packet / data["inventories"][0]["path"]
    elif target == "after":
        path = wo.root / data["images"][0]["after_image"]
    elif target == "input":
        assert data["inputs"]
        path = wo.root / data["inputs"][0]["path"]
    else:
        path = packet / "seal"
    path.write_bytes(path.read_bytes() + b"tampered\n")
    before = tree(wo.root)
    disposition(wo.root, packet, code=1)
    assert tree(wo.root) == before


@pytest.mark.parametrize("marker_damage", ["delete", "redirect", "change", "orphan"])
def test_owned_v1_child_cannot_escape_outer_ownership(wo, marker_damage):
    packet = propose(wo.root, "onboard", wo.source, "--init", "--project", "latency")
    data = json.loads((packet / "packet.md").read_bytes())
    creation = wo.root / data["creation"]["path"]
    marker = creation / "onboarding"
    if marker_damage == "delete":
        marker.unlink()
    elif marker_damage == "orphan":
        (packet / "seal").unlink()
    else:
        marker.write_text("runs/some-other-owner" if marker_damage == "redirect" else "changed")
    before = tree(wo.root)
    invoke(
        "project",
        "create",
        "latency",
        "--draft",
        creation.relative_to(wo.root),
        "--root",
        wo.root,
        "--confirmed-by",
        ACTOR,
        "--confirm",
        code=1,
    )
    assert tree(wo.root) == before
    assert not (wo.root / "projects/latency").exists()


@pytest.mark.parametrize(
    "crash_at",
    [
        "before-journal",
        "after-journal",
        "stage",
        "child-rename",
        "catalog",
        "local",
        "receipt",
        "retire",
    ],
)
def test_crash_replay_uses_original_images_and_never_exposes_usable_partial_child(
    wo, native, monkeypatch, crash_at
):
    packet = propose(wo.root, "onboard", wo.source, "--init", "--project", "latency")
    original_write = workspace_journal.write_atomic
    original_rename = workspace_journal.os.rename
    original_retire = workspace_journal.retire

    def write(path, data, **kwargs):
        relative = path.relative_to(wo.root).as_posix()
        stop = (
            (crash_at == "stage" and relative.startswith("projects/.creating-"))
            or (crash_at == "catalog" and relative == "sources.toml")
            or (crash_at == "local" and relative == "tools/sources.local.toml")
            or (crash_at == "receipt" and path.name == "receipt.md")
        )
        if stop:
            raise OSError("fixture publication crash")
        return original_write(path, data, **kwargs)

    def rename(src, dst):
        journal_commit = Path(dst) == wo.root / ".workspace-pending"
        if crash_at == "before-journal" and journal_commit:
            raise OSError("fixture power loss before commit")
        result = original_rename(src, dst)
        if crash_at == "after-journal" and journal_commit:
            raise OSError("fixture power loss after commit")
        if crash_at == "child-rename" and Path(dst) == wo.root / "projects/latency":
            raise OSError("fixture child rename crash")
        return result

    def retire(repository):
        if crash_at == "retire":
            raise OSError("fixture retirement crash")
        return original_retire(repository)

    with monkeypatch.context() as patch:
        patch.setattr(workspace_journal, "write_atomic", write)
        patch.setattr(workspace_journal.os, "rename", rename)
        patch.setattr(workspace_journal, "retire", retire)
        disposition(wo.root, packet, code=1)
    if crash_at == "before-journal":
        assert not (wo.root / ".workspace-pending").exists()
        assert not (wo.root / "projects/latency").exists()
    else:
        assert (wo.root / ".workspace-pending").exists()
        before = tree(wo.root)
        invoke("status", "--workspace", "--root", wo.root, code=1)
        invoke("open", "latency", "--root", wo.root, "--no-attach", code=1)
        assert tree(wo.root) == before and not native.created
        # Once committed, recovery must finish the approved images even if source changes.
        (wo.source / "main.py").write_text("print('changed after durable commit')\n")
    disposition(wo.root, packet, actor="Retry operator")
    assert not (wo.root / ".workspace-pending").exists()
    assert [p.name for p in (wo.root / "projects").iterdir() if p.is_dir()] == ["latency"]
    receipt = decode((packet / "receipt.md").read_bytes(), "receipt").header
    assert receipt["actor"] == ("Retry operator" if crash_at == "before-journal" else ACTOR)
    stable = tree(wo.root)
    disposition(wo.root, packet)
    assert tree(wo.root) == stable


def test_resealed_semantically_false_association_delta_is_rejected(wo):
    packet = propose(wo.root, "onboard", wo.source, "--init")
    data = json.loads((packet / "packet.md").read_bytes())
    data["association_changes"] = []  # Hash integrity alone must never authorize hidden effects.
    (packet / "packet.md").write_bytes(canonical(data))
    (packet / "seal").write_text(sha(canonical(data)) + "\n")
    before = tree(wo.root)
    disposition(wo.root, packet, code=1)
    assert tree(wo.root) == before


def test_two_previews_never_merge_invisible_catalog_changes(wo):
    v2_workspace(wo.root, wo.source)
    packets = [
        propose(wo.root, "onboard", wo.source, "--project", name, "--source-id", "source-main")
        for name in ("first", "second")
    ]
    disposition(wo.root, packets[0])
    before = tree(wo.root)
    disposition(wo.root, packets[1], code=1)
    assert tree(wo.root) == before
    assert not (wo.root / "projects/second").exists()


def test_workspace_understanding_is_separate_reviewed_revision_and_rejection_preserves_old(wo):
    onboard_a(wo.root, wo.source)
    old = (wo.root / "overview.md").read_bytes()
    body = wo.root / "runs/drafts/understanding.md"
    body.write_text(OVERVIEW)
    args = (
        "overview",
        "--workspace",
        "--input",
        body,
        "--source",
        "source-main",
        "--rationale",
        "Reviewed structural checkpoint",
    )
    first = propose(wo.root, *args)
    assert (wo.root / "overview.md").read_bytes() == old
    disposition(wo.root, first, reject=True)
    assert (wo.root / "overview.md").read_bytes() == old
    second = propose(wo.root, *args)
    disposition(wo.root, second)
    doc = decode((wo.root / "overview.md").read_bytes(), "overview")
    assert doc.header["revision"] == 2
    assert doc.header["supersedes"] == decode(old, "old").header["receipt"]
    assert doc.body == OVERVIEW
    # Replay of older successful intake cannot restore its old overview/catalog.
    before = tree(wo.root)
    for packet in outer_packets(wo.root):
        if json.loads((packet / "packet.md").read_bytes())["mode"] == "A":
            disposition(wo.root, packet)
    assert tree(wo.root) == before


@pytest.mark.parametrize(
    "damage", ["extra-staged-file", "extra-published-directory", "neither-image"]
)
def test_recovery_globally_prechecks_every_target_before_any_forward_write(wo, monkeypatch, damage):
    packet = propose(wo.root, "onboard", wo.source, "--init", "--project", "latency")
    original_rename = workspace_journal.os.rename

    def stop(src, dst):
        result = original_rename(src, dst)
        if Path(dst) == wo.root / ".workspace-pending":
            raise OSError("fixture stop immediately after journal commit")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(workspace_journal.os, "rename", stop)
        disposition(wo.root, packet, code=1)
    assert (wo.root / ".workspace-pending").exists()
    from toulmin.core.repository import Repository

    intent = workspace_journal.read_intent(Repository(wo.root))
    if damage == "neither-image":
        (wo.root / "sources.toml").write_text("external catalog edit\n")
    elif damage == "extra-staged-file":
        staging = wo.root / intent.staging
        staging.mkdir()
        (staging / "unreviewed.txt").write_text("Preserve this unexpected file\n")
    else:
        target = wo.root / "projects/latency"
        for image in intent.images:
            if image.path.startswith("projects/latency/"):
                path = wo.root / image.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(image.after)
        (target / "unreviewed-directory").mkdir()
    before = tree(wo.root)
    disposition(wo.root, packet, code=1)
    assert tree(wo.root) == before and (wo.root / ".workspace-pending").exists()


@pytest.mark.parametrize("effect", ["root-overview", "old-child", "old-role", "old-definition"])
def test_c_resealed_packet_cannot_hide_changes_outside_reviewed_new_child(wo, effect):
    v2_workspace(wo.root, wo.source, children=("first",))
    packet = propose(
        wo.root, "onboard", wo.source, "--project", "latency", "--source-id", "source-main"
    )
    data = json.loads((packet / "packet.md").read_bytes())
    if effect in {"root-overview", "old-child"}:
        target = "overview.md" if effect == "root-overview" else "projects/first/overview.md"
        image = packet / "after/forbidden"
        image.write_bytes(b"Unauthorized but correctly hashed effect\n")
        data["images"].append(
            {
                "path": target,
                "before": None,
                "after": sha(image.read_bytes()),
                "before_image": None,
                "after_image": image.relative_to(wo.root).as_posix(),
            }
        )
    else:
        image = next(i for i in data["images"] if i["path"] == "sources.toml")
        path = wo.root / image["after_image"]
        import tomllib

        from tests.acceptance.wo_support import catalog_bytes

        after = tomllib.loads(path.read_text())
        if effect == "old-definition":
            after["definitions"][0]["identity"] = "git:" + "f" * 64
        else:
            old = next(
                a
                for a in after["associations"]
                if a["scope"] == {"kind": "project", "project": "first"}
            )
            old["role"] = "reference"
            data["association_changes"].append(
                {
                    "scope": old["scope"],
                    "source": old["source"],
                    "before": "working",
                    "after": "reference",
                }
            )
        path.write_bytes(catalog_bytes(after["definitions"], after["associations"]))
        image["after"] = sha(path.read_bytes())
    (packet / "packet.md").write_bytes(canonical(data))
    (packet / "seal").write_text(sha(canonical(data)) + "\n")
    before = tree(wo.root)
    disposition(wo.root, packet, code=1)
    assert tree(wo.root) == before


def test_inventory_v2_observation_has_exact_bounded_shape_and_never_executes_helpers(wo):
    (wo.source / ".env").write_text("CREDENTIAL_SENTINEL=must-not-archive\n")
    (wo.source / "binary.bin").write_bytes(b"\x00\xff")
    (wo.source / "large.txt").write_text("x" * 32_001)
    (wo.source / "linked.txt").symlink_to(wo.source / "main.py")
    sentinel = wo.tmp / "executed-helper"
    helper = wo.tmp / "must-not-run.sh"
    helper.write_text(f"#!/bin/sh\ntouch '{sentinel}'\n")
    helper.chmod(0o700)
    git(wo.source, "config", "core.fsmonitor", str(helper))
    before = tree(wo.source)
    packet = propose(wo.root, "onboard", wo.source, "--init")
    envelope = json.loads((packet / "packet.md").read_bytes())
    for item in envelope["inventories"]:
        raw = (packet / item["path"]).read_bytes()
        data = json.loads(raw)
        assert set(data) == {
            "schema_version",
            "kind",
            "identity",
            "observed_at",
            "head",
            "status",
            "files",
            "truncated",
            "read_bytes",
            "limits",
            "coverage",
            "exclusions",
        }
        assert data["schema_version"] == 2 and data["limits"] == {
            "files": 400,
            "bytes": 512000,
            "file_bytes": 32000,
            "candidates": 3200,
        }
        assert data["coverage"] and data["read_bytes"] <= 512000 and len(raw) <= 1_000_000
        assert len({f["path"] for f in data["files"]}) == len(data["files"])
        for entry in data["files"]:
            assert set(entry) in ({"path", "bytes"}, {"path", "bytes", "sha256", "text"})
            assert not Path(entry["path"]).is_absolute()
            if "sha256" in entry:
                assert entry["sha256"] == sha((wo.source / entry["path"]).read_bytes())
        assert b"CREDENTIAL_SENTINEL" not in raw and b"linked.txt" not in raw
    assert not sentinel.exists() and tree(wo.source) == before


@pytest.mark.parametrize("relationship", ["equal", "target-inside-source", "source-inside-target"])
def test_two_source_overlap_refuses_before_initializing_new_records_root(wo, relationship):
    target = wo.source
    if relationship == "target-inside-source":
        target = wo.source / "nested"
        target.mkdir()
    elif relationship == "source-inside-target":
        target = wo.tmp
    before = tree(wo.tmp)
    invoke("onboard", wo.source, "--work-at", target, "--root", wo.root, "--init", code=1)
    assert tree(wo.tmp) == before and not wo.root.exists()


def test_preparation_never_publishes_sealed_child_without_ownership_marker(wo, monkeypatch):
    original_rename = workspace_journal.os.rename
    seen = []

    def observe(src, dst):
        result = original_rename(src, dst)
        if (wo.root / "runs").exists():
            for path in (wo.root / "runs").glob("*-project-*/packet.md"):
                if (path.parent / "seal").exists():
                    marker = path.parent / "onboarding"
                    assert marker.is_file(), (
                        "Child archive and marker must appear in the same rename"
                    )
                    seen.append(marker.read_bytes())
        return result

    with monkeypatch.context() as patch:
        patch.setattr(workspace_journal.os, "rename", observe)
        packet = propose(wo.root, "onboard", wo.source, "--init", "--project", "latency")
    assert seen and set(seen) == {packet.relative_to(wo.root).as_posix().encode()}
