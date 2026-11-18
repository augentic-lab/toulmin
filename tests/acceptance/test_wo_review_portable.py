"""R1: edited portable values fail as domain errors, never Python type errors."""

import json
from copy import deepcopy

import pytest

from tests.acceptance.wo_support import invoke, propose, sha, tree
from toulmin.core.documents import Document, FormatError
from toulmin.core.scoped_tasks import parse_import, validate_request
from toulmin.core.workspace_onboarding import (
    LIMITS,
    canonical,
    envelope,
    inventory,
    overview,
    source_pin,
)


def observed():
    return {
        "schema_version": 2,
        "kind": "git",
        "identity": "git:" + "1" * 64,
        "observed_at": "2026-11-18T01:00:00Z",
        "head": "2" * 40,
        "status": "",
        "files": [],
        "truncated": False,
        "read_bytes": 0,
        "limits": LIMITS,
        "coverage": "fixture",
        "exclusions": [],
    }


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        (field, bad)
        for field in ("kind", "limits", "files", "coverage", "exclusions", "head")
        for bad in ([], {}, True, None)
        if not (field in {"files", "exclusions"} and bad == [])
    ],
)
def test_malformed_observation_values_raise_domain_error(field, bad):
    value = observed()
    value[field] = bad
    with pytest.raises(FormatError):
        inventory(canonical(value), "edited-inventory.json")


@pytest.mark.parametrize("bad", [[], {}, True, None])
def test_malformed_source_pin_discriminator_raises_domain_error(bad):
    pin = {
        "source": "source-main",
        "catalog_sha256": "a" * 64,
        "definition_sha256": "b" * 64,
        "identity": bad,
        "snapshot": "runs/example/inventory/source-main.json",
        "snapshot_sha256": "c" * 64,
        "head": "2" * 40,
    }
    with pytest.raises(FormatError):
        source_pin(pin)


def test_resealed_malformed_inventory_cli_refuses_without_mutation(wo):
    packet = propose(wo.root, "onboard", wo.source, "--init", "--register-source", "source-main")
    raw = json.loads((packet / "packet.md").read_bytes())
    target = packet / raw["inventories"][0]["path"]
    value = json.loads(target.read_bytes())
    value["kind"] = []
    target.write_bytes(canonical(value))
    raw["inventories"][0]["sha256"] = sha(target.read_bytes())
    for item in raw["inputs"]:
        if item["path"] == target.relative_to(wo.root).as_posix():
            item["sha256"] = sha(target.read_bytes())
    (packet / "packet.md").write_bytes(canonical(raw))
    (packet / "seal").write_text(sha(canonical(raw)) + "\n")
    before = tree(wo.root)
    result = invoke(
        "workspace",
        "apply",
        packet,
        "--root",
        wo.root,
        "--confirm",
        "--confirmed-by",
        "Fixture operator",
        "--expect-seal",
        sha(canonical(raw)),
        code=1,
    )
    assert "TypeError" not in result.output and tree(wo.root) == before


@pytest.mark.parametrize("bad", [{"kind": []}, [], {"kind": "project", "project": []}])
@pytest.mark.parametrize("target", ["overview", "request", "packet", "import"])
def test_portable_scope_errors_are_domain_errors(wo, bad, target):
    packet = propose(wo.root, "onboard", wo.source, "--init", "--register-source", "source-main")
    data = json.loads((packet / "packet.md").read_bytes())
    after = next(image for image in data["images"] if image["path"] == "overview.md")
    from toulmin.core.codec import decode, encode

    document = decode((wo.root / after["after_image"]).read_bytes())
    document.header["scope"] = bad
    pin = deepcopy(document.header["sources"][0])
    fields = {
        "schema_version": 2,
        "kind": "task-request",
        "scope": bad,
        "source": "source-main",
        "source_pin": pin,
        "baseline": pin["head"],
        "tool": "fixture",
        "checks": ["true"],
        "protected": [],
        "budget": {"rounds": 1, "hours": 1},
        "test_first": True,
        "trust": False,
    }
    data["scope"] = bad
    imported = {
        "schema_version": 2,
        "kind": "task-import",
        "scope": bad,
        "source_pin": pin,
        "submission_sha256": "a" * 64,
        "task_id": "fixture",
        "request": "runs/proposals/task-20261118T100000Z.md",
        "request_sha256": "b" * 64,
        "actor": "Fixture",
        "at": "2026-11-18T01:00:00Z",
        "state": "done",
        "head": pin["head"],
        "tool": "fixture",
        "command": None,
        "session_id": None,
        "files": {
            name: "c" * 64
            for name in ("task.md", "commits.txt", "diffstat.txt", "review.md", "contract.json")
        },
        "disposition": "applying",
        "run": None,
    }
    with pytest.raises(FormatError):
        if target == "overview":
            overview(encode(document), "edited-overview.md")
        elif target == "request":
            validate_request(
                Document(fields, "## Goal\nDo it.\n## Scope\nOne file.\n", "edited.md")
            )
        elif target == "packet":
            envelope(canonical(data), "edited-packet.json")
        else:
            parse_import(canonical(imported), "edited-import.json")


@pytest.mark.parametrize("artifact", ["manifest", "receipt"])
def test_v4_context_versions_must_be_integer_even_when_manifest_is_rehashed(wo, native, artifact):
    from tests.acceptance.wo_support import v2_workspace
    from toulmin.application.aoe import AoEWorkspace

    v2_workspace(wo.root, wo.source)
    service = AoEWorkspace(wo.root, None, native)
    view = service.open(codex_sandbox="inherit")
    local = wo.root / ".aoe/contexts" / view.binding.token
    if artifact == "receipt":
        service.acknowledge(view.binding.token)
    path = local / (artifact + ".json")
    value = json.loads(path.read_bytes())
    value["schema_version"] = 4.0
    path.write_bytes(canonical(value))
    if artifact == "manifest":
        binding_path = wo.root / ".aoe/binding.json"
        binding = json.loads(binding_path.read_bytes())
        binding["manifest_sha256"] = sha(path.read_bytes())
        binding_path.write_bytes(canonical(binding))
    before = tree(wo.root)
    with pytest.raises(FormatError):
        service.acknowledge(view.binding.token)
    assert tree(wo.root) == before


def test_opaque_v1_identity_remains_readable_and_upgrade_refuses_without_rewriting(wo):
    from tests.acceptance.test_wo5_compatibility import legacy_workspace
    from toulmin.core.sources import parse_catalog, read_catalog

    original = legacy_workspace(wo)
    old = parse_catalog(original)[0].identity.encode()
    raw = original.replace(old, b"historical-opaque-identity")
    path = wo.root / "sources.toml"
    path.write_bytes(raw)
    before = tree(wo.root)
    assert read_catalog(wo.root)[0].identity == "historical-opaque-identity"
    invoke("source", "list", "--project", "latency", "--root", wo.root)
    result = invoke("source", "upgrade", "--root", wo.root, code=1)
    assert "v1" in result.output and "identity" in result.output
    assert path.read_bytes() == raw and tree(wo.root) == before
