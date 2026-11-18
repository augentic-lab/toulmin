"""Rebinding one source must not reserve unrelated checkouts or edit their records."""

import json

import pytest

from tests.acceptance.wo_support import (
    catalog_bytes,
    git,
    invoke,
    repository,
    tree,
    v2_workspace,
)
from toulmin.adapters.aoe import AoESession
from toulmin.application.sources import filesystem_identity, inspect_source


@pytest.mark.parametrize("managed", [False, True])
def test_unrelated_sources_writer_does_not_prevent_selected_rebind(
    wo, native, monkeypatch, managed
):
    definition = v2_workspace(wo.root, wo.source)
    other = repository(wo.tmp / "unrelated")
    identity = inspect_source(wo.root, other).identity
    other_definition = {**definition, "id": "source-other", "identity": identity}
    (wo.root / "sources.toml").write_bytes(
        catalog_bytes(
            [definition, other_definition],
            [
                {"scope": {"kind": "workspace"}, "source": "source-main", "role": "working"},
                {"scope": {"kind": "workspace"}, "source": "source-other", "role": "reference"},
            ],
        )
    )
    local = wo.root / "tools/sources.local.toml"
    local.write_text(
        local.read_text()
        + "\n[bindings.source-other]\n"
        + f'path = {json.dumps(str(other))}\nfilesystem = "{filesystem_identity(other)}"\n'
    )
    row = AoESession("f" * 16, other, "codex", "live", "idle", "native-other", "Other")
    native.other = [("other-profile", row)]
    native.sessions[row.id] = row
    monkeypatch.setattr("toulmin.adapters.aoe.AoEClient", lambda *a, **kw: native)
    if managed:
        binding = wo.root / ".aoe/binding.json"
        binding.parent.mkdir(exist_ok=True)
        binding.write_text(
            json.dumps({"cwd": str(other), "session_id": row.id, "profile": "other-profile"})
        )
    target = wo.tmp / "clone"
    git(wo.source, "clone", "-q", str(wo.source), str(target))
    before = tree(wo.root)
    invoke("source", "bind", "source-main", target, "--root", wo.root, "--confirm")
    after = tree(wo.root)
    assert {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)} == {
        "tools/sources.local.toml"
    }
    import tomllib

    bindings = tomllib.loads(local.read_text())["bindings"]
    assert bindings["source-other"] == {
        "path": str(other),
        "filesystem": filesystem_identity(other),
    }
    assert bindings["source-main"]["path"] == str(target)
    assert not native.created and not native.sent
