"""Bind preview/offline reads stay file-only; legacy lifecycle uses the common guard."""

import pytest

from tests.acceptance.test_wo5_compatibility import legacy_workspace
from tests.acceptance.wo_support import git, invoke, tree, v2_workspace
from toulmin.adapters.aoe import AoESession
from toulmin.application.aoe import AoEWorkspace
from toulmin.application.sources import filesystem_identity
from toulmin.core.sources import render_bindings


def legacy_binding(wo):
    legacy_workspace(wo)
    (wo.root / "tools/sources.local.toml").write_bytes(
        render_bindings({"source-main": (str(wo.source), filesystem_identity(wo.source))})
    )


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("operation", ["preview", "offline"])
def test_bind_preview_and_offline_status_never_query_native_tools(
    wo, native, monkeypatch, version, operation
):
    if version == 1:
        legacy_binding(wo)
        project = "latency"
    else:
        v2_workspace(wo.root, wo.source)
        project = None
    AoEWorkspace(wo.root, project, native).open(codex_sandbox="inherit")
    target = wo.tmp / "clone"
    git(wo.source, "clone", "-q", str(wo.source), str(target))

    def forbidden(*args, **kwargs):
        pytest.fail("preview/offline read attempted to construct a native client")

    monkeypatch.setattr("toulmin.adapters.aoe.AoEClient", forbidden)
    monkeypatch.setattr("toulmin.application.aoe.AoEClient", forbidden)
    monkeypatch.setattr("toulmin.cli.aoe.AoEClient", forbidden)
    before = tree(wo.root)
    if operation == "preview":
        invoke("source", "bind", "source-main", target, "--root", wo.root)
    else:
        scope = (project,) if project else ("--workspace",)
        invoke("aoe", "status", *scope, "--offline", "--root", wo.root)
    assert tree(wo.root) == before


@pytest.mark.parametrize("state", ["unknown", "archived"])
def test_v1_rebind_requires_known_inactive_lifecycle_on_selected_checkout(
    wo, native, monkeypatch, state
):
    legacy_binding(wo)
    target = wo.tmp / "clone"
    git(wo.source, "clone", "-q", str(wo.source), str(target))
    native.other = [
        (
            "other-profile",
            AoESession("f" * 16, wo.source, "codex", state, "idle", "native-writer", "Other"),
        )
    ]
    monkeypatch.setattr("toulmin.adapters.aoe.AoEClient", lambda *a, **kw: native)
    before = tree(wo.root)
    invoke(
        "source",
        "bind",
        "source-main",
        target,
        "--root",
        wo.root,
        "--confirm",
        code=1 if state == "unknown" else 0,
    )
    if state == "unknown":
        assert tree(wo.root) == before
    assert not native.created and not native.sent
