"""WO5 acceptance: reviewed derivation, strict formats and unchanged legacy data paths."""

import copy
import json
import shutil

import pytest

from tests.acceptance.wo_support import (
    ACTOR,
    WS,
    catalog,
    catalog_bytes,
    child,
    child_input,
    disposition,
    invoke,
    onboard_a,
    propose,
    role_map,
    sha,
    tree,
    v2_workspace,
)
from toulmin.application.aoe import AoEWorkspace
from toulmin.application.onboarding import prepare as legacy_prepare
from toulmin.cli.initialize import initialize_workspace
from toulmin.core.codec import decode
from toulmin.core.sources import Source, render_catalog
from toulmin.protocols import onboarding


@pytest.mark.parametrize("working", [False, True])
def test_later_derive_links_confirmed_context_without_moving_notes_or_starting_writer(
    wo, native, working
):
    onboard_a(wo.root, wo.source)
    notebook = wo.root / "runs/notebook.md"
    notebook.write_text("# Workspace notebook\nEntries unconfirmed.\nKeep original history.\n")
    overview = (wo.root / "overview.md").read_bytes()
    charter = (wo.root / "WORKSPACE.md").read_bytes()
    local = (wo.root / "tools/sources.local.toml").read_bytes()
    original = tree(wo.source)
    path = child_input(wo.root, "latency", context=True)
    args = ["project", "propose", "latency", "--input", path, "--source", "source-main"]
    if working:
        args += ["--working-source", "source-main"]
    first = propose(wo.root, *args)
    disposition(wo.root, first, reject=True)
    assert not (wo.root / "projects/latency").exists()
    packet = propose(wo.root, *args)
    data = json.loads((packet / "packet.md").read_bytes())
    assert data["operation"] == "child-derive" and data["mode"] is None
    disposition(wo.root, packet)
    assert len(catalog(wo.root)["definitions"]) == 1
    assert role_map(wo.root)[("project", "latency", "source-main")] == (
        "working" if working else "reference"
    )
    assert (wo.root / "overview.md").read_bytes() == overview
    assert (wo.root / "WORKSPACE.md").read_bytes() == charter
    assert (wo.root / "tools/sources.local.toml").read_bytes() == local
    assert notebook.read_text().endswith("Keep original history.\n")
    assert not (wo.root / "projects/latency/runs/notebook.md").exists()
    creation = decode(
        (wo.root / "projects/latency/runs/creation/creation.md").read_bytes(), "creation"
    )
    assert any(
        s["path"] == "overview.md" and s["sha256"] == sha(overview)
        for s in creation.header["sources"]
    )
    assert tree(wo.source) == original and not native.created


@pytest.mark.parametrize(
    "damage",
    [
        "unknown-version",
        "bool-version",
        "unknown-root",
        "missing-array",
        "extra-definition",
        "revision-bool",
        "revision-zero",
        "wrong-method",
        "wrong-identity",
        "duplicate-id",
        "duplicate-association",
        "missing-id",
        "workspace-project",
        "missing-child",
        "no-workspace",
        "two-working",
        "bad-role",
        "unknown-association",
    ],
)
def test_v2_catalog_invalid_shapes_fail_without_repair(wo, damage):
    definition = v2_workspace(wo.root, wo.source)
    data = catalog(wo.root)
    definitions = data["definitions"]
    associations = data["associations"]
    if damage == "unknown-version":
        raw = catalog_bytes(definitions, associations).replace(
            b"schema_version = 2", b"schema_version = 99"
        )
    elif damage == "bool-version":
        raw = catalog_bytes(definitions, associations).replace(
            b"schema_version = 2", b"schema_version = true"
        )
    elif damage == "unknown-root":
        raw = b'extra = "not allowed"\n' + catalog_bytes(definitions, associations)
    elif damage == "missing-array":
        raw = b"schema_version = 2\ndefinitions = []\n"
    else:
        if damage == "extra-definition":
            definitions[0]["project"] = "workspace"
        elif damage == "revision-bool":
            # JSON true is also TOML true, unlike JSON-encoded nested objects.
            definitions[0]["definition_revision"] = True
        elif damage == "revision-zero":
            definitions[0]["definition_revision"] = 0
        elif damage == "wrong-method":
            definitions[0]["identity_method"] = "directory-anchors-v1"
        elif damage == "wrong-identity":
            definitions[0]["identity"] = "directory:" + "a" * 64
        elif damage == "duplicate-id":
            definitions.append(copy.deepcopy(definition))
        elif damage == "duplicate-association":
            associations.append(copy.deepcopy(associations[0]))
        elif damage == "missing-id":
            associations[0]["source"] = "not-registered"
        elif damage == "workspace-project":
            associations[0]["scope"]["project"] = "latency"
        elif damage == "missing-child":
            associations.append(
                {
                    "scope": {"kind": "project", "project": "latency"},
                    "source": "source-main",
                    "role": "reference",
                }
            )
        elif damage == "no-workspace":
            associations.clear()
        elif damage == "two-working":
            second = dict(definition, id="source-other")
            definitions.append(second)
            associations.append({"scope": WS, "source": "source-other", "role": "working"})
        elif damage == "bad-role":
            associations[0]["role"] = "owner"
        raw = catalog_bytes(definitions, associations)
        if damage == "unknown-association":
            raw += b'unknown = "refuse"\n'
    (wo.root / "sources.toml").write_bytes(raw)
    before = tree(wo.root)
    result = invoke("source", "list", "--workspace", "--root", wo.root, code=1)
    assert "sources.toml" in result.output
    assert tree(wo.root) == before


@pytest.mark.parametrize("children", [(), ("latency",), ("latency", "throughput")])
def test_scope_compatibility_preserves_command_specific_records_directory_convenience(
    wo, native, monkeypatch, children
):
    initialize_workspace(wo.root)
    for name in children:
        child(wo.root, name)
    monkeypatch.chdir(wo.root)
    result = invoke("open", "--profile", native.profile, "--no-attach")
    assert "scope: workspace" in result.output.lower()
    if not children:
        return
    monkeypatch.chdir(wo.root / f"projects/{children[0]}/runs")
    inferred = invoke("open", "--profile", native.profile, "--no-attach")
    assert f"project: {children[0]}" in inferred.output.lower()
    explicit = invoke("open", "--root", wo.root, "--profile", native.profile, "--no-attach")
    assert "scope: workspace" in explicit.output.lower()
    override = invoke("open", "--workspace", "--profile", native.profile, "--no-attach")
    assert "scope: workspace" in override.output.lower()
    assert "workspace" in invoke("status").output.lower()
    assert children[0] in invoke("map").output
    mapped = invoke("map", "--workspace", "--root", wo.root).output.lower()
    assert "workspace" in mapped


def legacy_workspace(wo):
    initialize_workspace(wo.root)
    child(wo.root, "latency")
    # Valid v1 data with intentionally noncanonical whitespace.
    from toulmin.application.sources import inspect_source

    identity = inspect_source(wo.root, wo.source).identity
    raw = render_catalog((Source("source-main", "latency", "git", "working", identity),))
    (wo.root / "sources.toml").write_bytes(b"# Handwritten historical catalog\n" + raw)
    return (wo.root / "sources.toml").read_bytes()


def test_v1_read_write_remains_v1_and_workspace_intake_requires_separate_opt_in_upgrade(wo):
    legacy = legacy_workspace(wo)
    before = tree(wo.root)
    invoke("source", "list", "--root", wo.root)
    invoke("status", "latency", "--root", wo.root)
    assert tree(wo.root) == before
    result = invoke("onboard", wo.source, "--root", wo.root, "--project", "new-project", code=1)
    assert "source upgrade" in result.output and tree(wo.root) == before
    assert (wo.root / "sources.toml").read_bytes() == legacy


def test_catalog_upgrade_is_reviewed_preserves_legacy_bytes_roles_and_no_working_choice(wo):
    legacy = legacy_workspace(wo)
    old_child = tree(wo.root / "projects/latency")
    first = propose(wo.root, "source", "upgrade")
    assert (wo.root / "sources.toml").read_bytes() == legacy
    assert (first / "legacy/sources.v1.toml").read_bytes() == legacy
    disposition(wo.root, first, reject=True)
    assert (wo.root / "sources.toml").read_bytes() == legacy
    packet = propose(wo.root, "source", "upgrade")
    disposition(wo.root, packet)
    # Conversion does not bind an unavailable checkout or choose workspace working.
    assert (packet / "legacy/sources.v1.toml").read_bytes() == legacy
    assert tree(wo.root / "projects/latency") == old_child
    assert role_map(wo.root) == {
        ("project", "latency", "source-main"): "working",
        ("workspace", None, "source-main"): "reference",
    }
    assert not (wo.root / "tools/sources.local.toml").exists()
    assert not (wo.root / "overview.md").exists()
    data = json.loads((packet / "packet.md").read_bytes())
    assert data["operation"] == "catalog-upgrade"
    assert {i["path"] for i in data["images"]} == {"sources.toml"}
    before = tree(wo.root)
    (wo.root / "sources.toml").write_text("schema_version = 999\n")
    damaged = tree(wo.root)
    invoke("source", "list", "--root", wo.root, code=1)
    assert tree(wo.root) == damaged and damaged != before
    invoke("status", "latency", "--root", wo.root)


def test_pending_v1_onboarding_finishes_unchanged_and_blocks_upgrade(wo):
    initialize_workspace(wo.root)
    initial = legacy_prepare(wo.root, wo.source, "first")
    onboarding.apply(wo.root, initial.loaded.directory, ACTOR, confirmed=True)
    packet = legacy_prepare(wo.root, wo.source, "latency")
    original = tree(wo.root)
    invoke("source", "upgrade", "--root", wo.root, code=1)
    assert tree(wo.root) == original
    onboarding.apply(wo.root, packet.loaded.directory, ACTOR, confirmed=True)
    receipt = (wo.root / packet.loaded.directory / "receipt.md").read_bytes()
    before = tree(wo.root)
    onboarding.apply(wo.root, packet.loaded.directory, "replay", confirmed=True)
    assert tree(wo.root) == before
    assert (wo.root / packet.loaded.directory / "receipt.md").read_bytes() == receipt


@pytest.mark.parametrize("version", [1, 2, 3])
def test_old_native_binding_offline_reads_do_not_upgrade_or_move_archives(wo, native, version):
    initialize_workspace(wo.root)
    child(wo.root, "latency")
    if version == 1:
        (wo.root / "WORKSPACE.md").unlink()
    if version == 3:
        from toulmin.application.sources import inspect_source
        from toulmin.core.sources import render_bindings

        inspection = inspect_source(wo.root, wo.source)
        (wo.root / "sources.toml").write_bytes(
            render_catalog(
                (Source("source-main", "latency", "git", "working", inspection.identity),)
            )
        )
        from toulmin.application.sources import filesystem_identity

        (wo.root / "tools/sources.local.toml").write_bytes(
            render_bindings({"source-main": (str(wo.source), filesystem_identity(wo.source))})
        )
    first = AoEWorkspace(wo.root, "latency", native).open()
    assert first.binding.version == version
    AoEWorkspace(wo.root, "latency", native).acknowledge(first.binding.token)
    before = tree(wo.root)
    AoEWorkspace(wo.root, "latency", native).status(check_session=False)
    invoke("status", "latency", "--root", wo.root)
    assert tree(wo.root) == before
    assert (first.context_path.parent / "manifest.json").exists()
    assert (first.context_path.parent / "receipt.json").exists()


def test_bind_requires_preview_then_explicit_confirmation_and_changes_only_local_mapping(
    wo, native, monkeypatch
):
    monkeypatch.setattr("toulmin.adapters.aoe.AoEClient", lambda *a, **kw: native)
    v2_workspace(wo.root, wo.source)
    target = wo.tmp / "clone"
    # Local clone only; git never contacts a remote.
    from tests.acceptance.wo_support import git

    git(wo.source, "clone", "-q", str(wo.source), str(target))
    before = tree(wo.root)
    invoke("source", "bind", "source-main", target, "--root", wo.root)
    assert tree(wo.root) == before
    invoke("source", "bind", "source-main", target, "--root", wo.root, "--confirm")
    after = tree(wo.root)
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    assert changed == {"tools/sources.local.toml"}
    assert str(target) in (wo.root / "tools/sources.local.toml").read_text()


@pytest.mark.parametrize(
    "kind", ["symlink", "nested-source", "nested-root", "git-subdirectory", "alias-id"]
)
def test_source_path_safety_and_checkout_alias_conflicts_never_register(wo, kind):
    v2_workspace(wo.root, wo.source)
    source = wo.source
    if kind == "symlink":
        source = wo.tmp / "alias"
        source.symlink_to(wo.source, target_is_directory=True)
    elif kind == "nested-source":
        source = wo.root / "nested"
        source.mkdir()
    elif kind == "nested-root":
        source = wo.tmp
    elif kind == "git-subdirectory":
        source = wo.source / "subdir"
        source.mkdir()
    before = tree(wo.root)
    invoke(
        "source",
        "add",
        source,
        "--workspace",
        "--register-source",
        "new-id",
        "--rationale",
        "Explicit registration cannot bypass overlap or alias checks",
        "--root",
        wo.root,
        code=1,
    )
    assert tree(wo.root) == before


@pytest.mark.parametrize("flag", ["--project-input", "--project-overview"])
def test_project_only_inputs_cannot_imply_child(wo, flag):
    path = wo.tmp / "input.md"
    path.write_text("Must not silently create child\n")
    invoke("onboard", wo.source, "--root", wo.root, "--init", flag, path, code=2)
    assert not wo.root.exists()


def test_noninteractive_queue_lists_only_and_explicit_apply_requires_seal_actor_and_confirm(
    wo, monkeypatch
):
    packet = propose(wo.root, "onboard", wo.source, "--init")
    before = tree(wo.root)
    invoke("decide", "--workspace", "--root", wo.root)
    assert tree(wo.root) == before
    args = ["workspace", "apply", packet.relative_to(wo.root), "--root", wo.root]
    for extra in (
        ["--confirm", "--confirmed-by", ACTOR],
        ["--expect-seal", (packet / "seal").read_text().strip(), "--confirm"],
    ):
        monkeypatch.setenv("TOULMIN_ACTOR", "Environment must not approve v2 packets")
        invoke(*args, *extra, code=2)
        assert tree(wo.root) == before
    disposition(wo.root, packet, seal="a" * 64, code=1)
    assert tree(wo.root) == before


def test_edited_directory_recovery_requires_distinct_checkout_then_separate_selection(wo):
    directory = wo.tmp / "directory-source"
    directory.mkdir()
    (directory / "README.md").write_text("Original directory anchors.\n")
    v2_workspace(wo.root, directory)
    original_definition = catalog(wo.root)["definitions"][0]
    (directory / "README.md").write_text("Legitimate edits; anchors changed.\n")
    moved = wo.tmp / "moved-directory"
    directory.rename(moved)
    before = tree(wo.root)
    invoke("source", "bind", "source-main", moved, "--root", wo.root, "--confirm", code=1)
    assert tree(wo.root) == before
    # Moving the same inode cannot bypass the old binding's collision guard.
    invoke(
        "source",
        "add",
        moved,
        "--workspace",
        "--register-source",
        "source-edited",
        "--rationale",
        "Retain source-main provenance",
        "--root",
        wo.root,
        code=1,
    )
    assert tree(wo.root) == before
    distinct = wo.tmp / "distinct-directory"
    shutil.copytree(moved, distinct)
    packet = propose(
        wo.root,
        "source",
        "add",
        distinct,
        "--workspace",
        "--register-source",
        "source-edited",
        "--rationale",
        "Recover edits; retain source-main archived anchors",
    )
    disposition(wo.root, packet)
    assert role_map(wo.root)[("workspace", None, "source-main")] == "working"
    assert role_map(wo.root)[("workspace", None, "source-edited")] == "reference"
    assert original_definition in catalog(wo.root)["definitions"]
    packet = propose(
        wo.root,
        "source",
        "working",
        "--workspace",
        "source-edited",
        "--rationale",
        "Continue at separately reviewed source",
    )
    disposition(wo.root, packet)
    assert role_map(wo.root)[("workspace", None, "source-main")] == "reference"
    assert role_map(wo.root)[("workspace", None, "source-edited")] == "working"
    assert (moved / "README.md").read_text() == (distinct / "README.md").read_text()


@pytest.mark.parametrize("missing", [False, True])
def test_c_work_at_preserves_existing_workspace_reference_only_selection(wo, missing):
    v2_workspace(wo.root, wo.source)
    data = catalog(wo.root)
    data["associations"][0]["role"] = "reference"
    (wo.root / "sources.toml").write_bytes(catalog_bytes(data["definitions"], data["associations"]))
    from tests.acceptance.wo_support import repository

    target = repository(wo.tmp / "new-target")
    if missing:
        (wo.root / "tools/sources.local.toml").unlink()
        before = tree(wo.root)
        invoke(
            "onboard",
            wo.source,
            "--project",
            "latency",
            "--source-id",
            "source-main",
            "--root",
            wo.root,
            "--work-at",
            target,
            code=1,
        )
        assert tree(wo.root) == before
        return
    packet = propose(
        wo.root,
        "onboard",
        wo.source,
        "--project",
        "latency",
        "--source-id",
        "source-main",
        "--work-at",
        target,
        "--register-working-source",
        "source-target",
    )
    disposition(wo.root, packet)
    roles = role_map(wo.root)
    assert all(role == "reference" for (kind, _, _), role in roles.items() if kind == "workspace")
    assert roles[("project", "latency", "source-target")] == "working"
    assert roles[("project", "latency", "source-main")] == "reference"


@pytest.mark.parametrize("file", ["catalog", "local", "binding", "overview"])
def test_unknown_active_formats_do_not_fallback_to_archived_legacy_or_repair(wo, native, file):
    onboard_a(wo.root, wo.source)
    path = {
        "catalog": wo.root / "sources.toml",
        "local": wo.root / "tools/sources.local.toml",
        "binding": wo.root / ".aoe/binding.json",
        "overview": wo.root / "overview.md",
    }[file]
    path.parent.mkdir(parents=True, exist_ok=True)
    if file == "binding":
        path.write_text('{"schema_version": 99}\n')
        args = ("aoe", "status", "--workspace", "--offline", "--root", wo.root)
    elif file in {"catalog", "local"}:
        path.write_text("schema_version = 99\n")
        args = ("status", "--workspace", "--root", wo.root)
    else:
        path.write_bytes(path.read_bytes().replace(b"schema_version: 1", b"schema_version: 99", 1))
        args = ("status", "--workspace", "--root", wo.root)
    before = tree(wo.root)
    invoke(*args, code=1)
    assert tree(wo.root) == before and not native.created and not native.sent


def test_legacy_explicit_child_overview_alias_never_becomes_workspace_overview(wo):
    body = wo.tmp / "child-overview.md"
    body.write_text("# Child-specific details\nCHILD-OVERVIEW-MARKER\n")
    packet = propose(
        wo.root, "onboard", wo.source, "--init", "--project", "latency", "--overview", body
    )
    disposition(wo.root, packet)
    assert (wo.root / "projects/latency/overview.md").read_bytes() == body.read_bytes()
    assert "CHILD-OVERVIEW-MARKER" not in (wo.root / "overview.md").read_text()


def test_existing_v1_project_role_writer_keeps_catalog_and_packet_version(wo):
    from toulmin.protocols import context_change

    legacy_workspace(wo)
    # A second v1 source permits a real working-role change under the old protocol.
    first = Source("source-main", "latency", "git", "working", "opaque-v1-identity")
    second = Source("source-other", "latency", "git", "reference", "opaque-v1-other")
    (wo.root / "sources.toml").write_bytes(render_catalog((first, second)))
    packet = context_change.propose_source_role(
        wo.root, "latency", "source-other", rationale="Old command"
    )
    context_change.apply(wo.root, packet.loaded.directory, ACTOR, confirmed=True)
    import tomllib

    assert tomllib.loads((wo.root / "sources.toml").read_text())["schema_version"] == 1
    assert (
        json.loads((wo.root / packet.loaded.directory / "packet.md").read_bytes())["schema_version"]
        == 1
    )
