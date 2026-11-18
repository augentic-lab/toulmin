"""WO4 fake-native acceptance: source cwd, scoped v4 receipt and permission boundaries."""

import json

import pytest

from tests.acceptance.wo_support import (
    WS,
    canonical,
    child_input,
    definition_sha,
    disposition,
    invoke,
    propose,
    repository,
    sha,
    tree,
    v2_workspace,
)
from toulmin.adapters.aoe import AoEError, AoESession
from toulmin.application.aoe import AoEWorkspace
from toulmin.core.documents import FormatError

BINDING_KEYS = {
    "schema_version",
    "scope",
    "title",
    "root",
    "profile",
    "agent",
    "session_id",
    "provider_session_id",
    "context",
    "token",
    "fingerprint",
    "manifest_sha256",
    "delivery",
    "known_ids",
    "message",
    "cwd",
    "source_id",
    "source_identity",
    "cwd_identity",
    "catalog_sha256",
    "definition_sha256",
}


def open_workspace(wo, native, **kwargs):
    return AoEWorkspace(wo.root, None, native).open(codex_sandbox="inherit", **kwargs)


def test_zero_child_native_v4_separates_portable_context_from_local_manifest_and_receipt(
    wo, native
):
    definition = v2_workspace(wo.root, wo.source)
    (wo.root / "runs/notebook.md").write_text(
        "# Workspace notebook\nEntries are unconfirmed.\nLatest provisional measurement plan.\n"
    )
    before_source = tree(wo.source)
    view = open_workspace(wo, native)
    binding = json.loads((wo.root / ".aoe/binding.json").read_bytes())
    assert set(binding) == BINDING_KEYS and binding["schema_version"] == 4
    assert binding["scope"] == WS and binding["cwd"] == str(wo.source)
    assert binding["catalog_sha256"] == sha((wo.root / "sources.toml").read_bytes())
    assert binding["definition_sha256"] == definition_sha(definition)
    assert native.created[0][:4] == (wo.source, None, "codex", wo.root)
    assert view.context_status == "submitted" and binding["delivery"] == "submitted"
    local = wo.root / ".aoe/contexts" / binding["token"]
    manifest_bytes = (local / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert binding["manifest_sha256"] == sha(manifest_bytes)
    assert set(manifest) == {
        "schema_version",
        "scope",
        "token",
        "fingerprint",
        "profile",
        "session_id",
        "provider_session_id",
        "files",
        "working_source",
    }
    assert manifest["schema_version"] == 4 and manifest["scope"] == WS
    working = manifest["working_source"]
    assert set(working) == {
        "cwd",
        "source_id",
        "identity",
        "cwd_identity",
        "catalog_sha256",
        "definition_sha256",
    }
    assert working["cwd"] == binding["cwd"] and working["identity"] == definition["identity"]
    assert (local / "local.json").is_file()
    assert not (local / "receipt.json").exists()
    archive = view.context_path.parent
    assert not (archive / "manifest.json").exists() and not (archive / "receipt.json").exists()
    assert {"context.md", "state.md", "guide.md"} <= set(manifest["files"])
    for name, digest in manifest["files"].items():
        assert sha((archive / name).read_bytes()) == digest
    for path in archive.rglob("*"):
        if path.is_file():
            assert str(wo.source).encode() not in path.read_bytes(), path
            assert str(wo.root).encode() not in path.read_bytes(), path
    guide = (archive / "guide.md").read_text().lower()
    assert "workspace" in guide and "source" in guide and "decide" in guide
    assert "unconfirmed" in (archive / "notebook.md").read_text().lower()
    assert (
        not [p for p in (wo.root / "projects").iterdir() if p.is_dir()]
        and tree(wo.source) == before_source
    )
    result = AoEWorkspace(wo.root, None, native).acknowledge(binding["token"])
    assert result.context_status == "acknowledged"
    ack = json.loads((local / "receipt.json").read_bytes())
    assert set(ack) == {
        "schema_version",
        "scope",
        "token",
        "fingerprint",
        "session_id",
        "provider_session_id",
        "received_at",
        "manifest_sha256",
    }
    assert ack["schema_version"] == 4 and ack["scope"] == WS
    assert ack["manifest_sha256"] == sha(manifest_bytes)
    assert tree(wo.source) == before_source


@pytest.mark.parametrize("tamper", ["scope", "token", "cwd", "definition", "snapshot"])
def test_v4_wrong_scope_token_cwd_or_changed_manifest_cannot_acknowledge(wo, native, tamper):
    v2_workspace(wo.root, wo.source)
    view = open_workspace(wo, native)
    binding = json.loads((wo.root / ".aoe/binding.json").read_bytes())
    local = wo.root / ".aoe/contexts" / binding["token"]
    path = local / "manifest.json"
    manifest = json.loads(path.read_bytes())
    if tamper == "scope":
        manifest["scope"] = {"kind": "project", "project": "missing"}
    elif tamper == "token":
        manifest["token"] = "f" * 32
    elif tamper == "cwd":
        manifest["working_source"]["cwd"] = str(wo.tmp)
    elif tamper == "definition":
        manifest["working_source"]["definition_sha256"] = "f" * 64
    else:
        (view.context_path.parent / "state.md").write_text("changed snapshot\n")
    if tamper != "snapshot":
        path.write_bytes(canonical(manifest))
    before = tree(wo.root)
    with pytest.raises(FormatError):
        AoEWorkspace(wo.root, None, native).acknowledge(binding["token"])
    assert tree(wo.root) == before and not (local / "receipt.json").exists()


def test_notebook_and_source_changes_stale_context_without_rewriting_confirmed_context(wo, native):
    v2_workspace(wo.root, wo.source)
    path = wo.root / "runs/notebook.md"
    path.write_text("# Workspace notebook\nEntries unconfirmed.\nFirst plan.\n")
    service = AoEWorkspace(wo.root, None, native)
    first = service.open(codex_sandbox="inherit")
    service.acknowledge(first.binding.token)
    path.write_text(path.read_text() + "New unconfirmed observation.\n")
    assert "stale" in service.status(check_session=False).context_status
    with pytest.raises(FormatError):
        service.acknowledge(first.binding.token)
    second = service.refresh()
    assert second.binding.token != first.binding.token and second.binding.cwd == first.binding.cwd
    service.acknowledge(second.binding.token)
    (wo.source / "main.py").write_text("print('ordinary dirty edit')\n")
    assert "stale" in service.status().context_status
    assert not (wo.root / "overview.md").exists()


def test_selection_change_never_redirects_live_session_and_replacement_preserves_history(
    wo, native
):
    v2_workspace(wo.root, wo.source)
    original = open_workspace(wo, native)
    other = repository(wo.tmp / "direction")
    packet = propose(
        wo.root,
        "source",
        "add",
        other,
        "--workspace",
        "--register-source",
        "source-next",
        "--working",
        "--rationale",
        "Continue in another checkout",
    )
    disposition(wo.root, packet)
    service = AoEWorkspace(wo.root, None, native)
    before = tree(wo.root)
    with pytest.raises(FormatError):
        service.refresh()
    with pytest.raises(FormatError):
        service.open()
    assert tree(wo.root) == before and len(native.created) == 1
    assert native.sessions[original.binding.session_id].path == wo.source
    native.archive()
    replacement = service.open(new_session=True, codex_sandbox="inherit")
    assert (
        replacement.binding.cwd == str(other)
        and replacement.binding.scope == original.binding.scope
    )
    assert original.context_path.exists() and len(native.created) == 2
    assert replacement.binding.title != original.binding.title


@pytest.mark.parametrize("profile", ["fixture", "other-profile"])
def test_workspace_project_writers_conflict_across_scopes_and_profiles(wo, native, profile):
    v2_workspace(wo.root, wo.source, children=("latency",))
    native.other = [
        (
            profile,
            AoESession(
                "f" * 16, wo.source, "claude", "live", "idle", "other-native", "Other writer"
            ),
        )
    ]
    before = tree(wo.root)
    with pytest.raises(FormatError, match="(?i)(writer|checkout|session)"):
        open_workspace(wo, native)
    assert tree(wo.root) == before and not native.created and not native.sent


def test_unknown_cross_profile_lookup_fails_closed_but_offline_status_is_available(wo, native):
    v2_workspace(wo.root, wo.source)
    native.lookup_error = True
    before = tree(wo.root)
    with pytest.raises((FormatError, AoEError)):
        open_workspace(wo, native)
    assert tree(wo.root) == before and not native.created
    invoke("status", "--workspace", "--root", wo.root)
    assert tree(wo.root) == before


def test_workspace_permission_is_explicit_saved_in_existing_mechanism_and_scope_local(wo, native):
    v2_workspace(wo.root, wo.source, children=("latency",))
    options = ("open", "--workspace", "--root", wo.root, "--profile", native.profile, "--no-attach")
    missing = invoke(*options, code=1)
    assert "--codex-sandbox" in missing.output and not native.created
    assert not (wo.root / "tools/native.local.toml").exists()
    invoke(*options, "--codex-sandbox", "workspace-write")
    assert native.created[-1][4] == {"codex_sandbox": "workspace-write"}
    policy = wo.root / "tools/native.local.toml"
    assert policy.exists() and "workspace-write" in policy.read_text()
    saved = policy.read_bytes()
    # Saved settings persist across application instances and never auto-grant to child scope.
    native.archive()
    child_options = (
        "open",
        "latency",
        "--root",
        wo.root,
        "--profile",
        native.profile,
        "--no-attach",
    )
    invoke(*child_options, code=1)
    assert len(native.created) == 1 and policy.read_bytes() == saved
    invoke(*options, "--new-session")
    assert native.created[-1][4] == {"codex_sandbox": "workspace-write"}
    assert policy.read_bytes() == saved and len(native.created) == 2


def test_permission_prompt_is_unlocked_and_revalidates_changes_across_scopes(wo, native):
    v2_workspace(wo.root, wo.source, children=("latency",))
    service = AoEWorkspace(wo.root, None, native)
    choices = []

    def choose(source, stale):
        choices.append((source.path, stale))
        # The callback must be outside both root/binding and checkout locks. A second
        # scoped service can finish its launch here; the original must revalidate.
        AoEWorkspace(wo.root, "latency", native).open(codex_sandbox="inherit")
        return "workspace-write"

    with pytest.raises(FormatError):
        service.open(choose_codex_sandbox=choose)
    assert choices == [(wo.source, False)] and len(native.created) == 1
    assert not (wo.root / ".aoe/binding.json").exists()
    assert native.created[0][1] == "latency"


def test_creating_child_keeps_workspace_session_and_private_notebook_out_of_child_context(
    wo, native
):
    v2_workspace(wo.root, wo.source)
    (wo.root / "runs/notebook.md").write_text(
        "# Workspace notebook\nUnconfirmed.\nPRIVATE-ROOT-NOTE\n"
    )
    first = open_workspace(wo, native)
    binding = (wo.root / ".aoe/binding.json").read_bytes()
    packet = propose(
        wo.root,
        "project",
        "propose",
        "latency",
        "--input",
        child_input(wo.root, "latency"),
        "--source",
        "source-main",
    )
    disposition(wo.root, packet)
    assert (wo.root / ".aoe/binding.json").read_bytes() == binding
    assert len(native.created) == 1 and native.sessions[first.binding.session_id].path == wo.source
    # References without an explicit working selection must not inherit workspace cwd.
    with pytest.raises(FormatError):
        AoEWorkspace(wo.root, "latency", native).open()
    native.archive()
    role = propose(wo.root, "source", "working", "latency", "source-main", "Choose child checkout")
    disposition(wo.root, role)
    view = AoEWorkspace(wo.root, "latency", native).open(codex_sandbox="inherit")
    assert view.binding.version == 4
    assert "PRIVATE-ROOT-NOTE" not in "\n".join(
        p.read_text() for p in view.context_path.parent.rglob("*.md")
    )
    assert first.context_path.exists()


def test_uncertain_workspace_native_creation_recovers_same_id_without_second_launch(wo, native):
    v2_workspace(wo.root, wo.source)
    native.create_uncertain = True
    with pytest.raises(AoEError):
        open_workspace(wo, native)
    native.create_uncertain = False
    result = AoEWorkspace(wo.root, None, native).open()
    assert len(native.created) == 1 and result.binding.session_id in native.sessions
    assert result.context_status == "submitted" and len(native.sent) == 1


def test_workspace_status_map_and_generated_guides_offer_source_work_without_gates(wo):
    v2_workspace(wo.root, wo.source)
    before = tree(wo.root)
    for command in ("status", "map"):
        output = invoke(command, "--workspace", "--root", wo.root).output.lower()
        assert "source-main" in output and "workspace" in output
        assert "overview" in output and ("task" in output or "engineering" in output)
        assert "g1" not in output and "missing claim" not in output
    assert tree(wo.root) == before
    text = (wo.root / "AGENTS.md").read_text().lower()
    assert "workspace" in text and "source" in text
    draft = invoke("draft", "overview", "--workspace", "--root", wo.root)
    assert "runs/drafts/overview-" in draft.output
    assert [p for p in (wo.root / "projects").iterdir() if p.is_dir()] == []


def test_concurrent_workspace_and_project_launches_admit_at_most_one_checkout_writer(wo, native):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    v2_workspace(wo.root, wo.source, children=("latency",))
    barrier = Barrier(2)

    def attempt(project):
        barrier.wait(timeout=5)
        try:
            return AoEWorkspace(wo.root, project, native).open(codex_sandbox="inherit")
        except (FormatError, AoEError) as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, project) for project in (None, "latency")]
        results = [future.result(timeout=15) for future in futures]
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert len(native.created) == 1 and len(native.sent) == 1


def test_source_reference_without_working_selection_refuses_instead_of_records_cwd_fallback(
    wo, native
):
    from tests.acceptance.wo_support import catalog, catalog_bytes

    v2_workspace(wo.root, wo.source)
    data = catalog(wo.root)
    data["associations"][0]["role"] = "reference"
    (wo.root / "sources.toml").write_bytes(catalog_bytes(data["definitions"], data["associations"]))
    before = tree(wo.root)
    result = invoke(
        "open", "--workspace", "--root", wo.root, "--profile", native.profile, "--no-attach", code=2
    )
    assert "source working" in result.output
    assert tree(wo.root) == before and not native.created
