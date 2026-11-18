"""R4: real native adapter and coordinator; only the AoE command transport is fake.

The transport retains add arguments as AoE does for resume/restart. No AoE,
provider, Chief process, user configuration or live research data is accessed.
"""

import json
import shlex
import sys

import pytest
from typer.testing import CliRunner

from tests.acceptance.wo_support import WS, catalog, definition_sha, sha, tree, v2_workspace
from toulmin.adapters.aoe import AoEClient, AoEError
from toulmin.application import native_policy
from toulmin.application.aoe import AoEWorkspace
from toulmin.application.sources import filesystem_identity, resolve_source
from toulmin.cli.app import app
from toulmin.core.repository import Repository

PRELAUNCH_ERROR = (
    "codex_sandbox requires workspace-write or inherit for a Codex project "
    "with an additional records directory"
)


class CommandTransport(AoEClient):
    """Inherit create/show/readiness/send unchanged; refuse any unknown operation."""

    def __init__(self):
        # Resolve an explicit executable without probing a real AoE installation.
        # _run is the sole replaced boundary: this executable is never launched.
        super().__init__(profile="r4-disposable", command=sys.executable)
        self.rows = {}
        self.calls = []
        self.saved_args = {}

    def _run(self, *args, timeout=15.0):
        self.calls.append(args)
        if args in (("list", "--json"), ("list", "--all", "--json")):
            return json.dumps(list(self.rows.values()))
        if args[:2] == ("session", "show"):
            assert args[3:] == ("--json",)
            return json.dumps(self.rows[args[2]])
        if args[:2] == ("session", "capture"):
            return "› " if self.rows[args[2]]["tool"] == "codex" else "> "
        if args[0] == "add":
            sid = f"{len(self.rows) + 1:016x}"
            assert "--launch" in args and timeout == 45.0
            self.saved_args[sid] = (
                args[args.index("--extra-args") + 1] if "--extra-args" in args else ""
            )
            self.rows[sid] = {
                "id": sid,
                "profile": self.profile,
                "path": args[1],
                "tool": args[args.index("--tool") + 1],
                "state": "live",
                "status": "idle",
                "title": args[args.index("-t") + 1],
                "agent_session_id": "native-" + sid,
            }
            return f"Added session: {sid}\n"
        if args[0] == "send":
            assert args[1] == "--no-revive" and args[3] == "--"
            assert args[2] in self.rows
            return ""
        raise AssertionError(f"No real command fallback permitted: {args}")

    @property
    def launches(self):
        return [args for args in self.calls if args[0] == "add"]


def native_args(mode, records):
    return (["--sandbox", "workspace-write"] if mode == "workspace-write" else []) + [
        "--add-dir",
        str(records),
    ]


@pytest.mark.parametrize("mode", ["workspace-write", "inherit"])
def test_real_adapter_accepts_workspace_and_persists_exact_native_arguments(tmp_path, mode):
    source = tmp_path / "code 'quoted' 中文"
    records = tmp_path / "research records 'quoted'"
    source.mkdir()
    records.mkdir()
    client = CommandTransport()
    session = client.create(
        source, None, "codex", title="Workspace: R4", add_directory=records, codex_sandbox=mode
    )
    assert session.path == source and session.title == "Workspace: R4"
    assert client.launches == [
        (
            "add",
            str(source),
            "-t",
            "Workspace: R4",
            "-g",
            "research",
            "--tool",
            "codex",
            "--launch",
            "--extra-args",
            shlex.join(native_args(mode, records)),
        )
    ]
    saved = client.saved_args[session.id]
    assert shlex.split(saved) == native_args(mode, records)
    assert client.show(session.id) == session
    assert client.saved_args[session.id] == saved and len(client.launches) == 1


@pytest.fixture
def real_adapter(wo, monkeypatch):
    v2_workspace(wo.root, wo.source)
    client = CommandTransport()
    # Select the test transport; do not replace create, readiness or workflow methods.
    monkeypatch.setattr("toulmin.cli.aoe.AoEClient", lambda *a, **kw: client)
    monkeypatch.setattr("toulmin.application.aoe.AoEClient", lambda *a, **kw: client)
    return client


def cli_open(wo, client, *options):
    result = CliRunner().invoke(
        app,
        [
            "open",
            "--workspace",
            "--root",
            str(wo.root),
            "--agent",
            "codex",
            "--profile",
            client.profile,
            "--no-attach",
            *options,
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads((wo.root / ".aoe/binding.json").read_bytes())


@pytest.mark.parametrize("mode", ["workspace-write", "inherit"])
def test_real_workspace_cli_launch_delivers_context_and_reuses_saved_arguments(
    wo, real_adapter, mode
):
    before = tree(wo.source)
    binding = cli_open(wo, real_adapter, "--codex-sandbox", mode)
    sid = binding["session_id"]
    assert binding["schema_version"] == 4 and binding["scope"] == WS
    assert binding["cwd"] == str(wo.source) and binding["delivery"] == "submitted"
    assert binding["provider_session_id"] == "native-" + sid
    assert shlex.split(real_adapter.saved_args[sid]) == native_args(mode, wo.root)
    policy = native_policy.load(Repository(wo.root))[None]
    assert policy.sandbox == mode and policy.cwd == str(wo.source)
    assert policy.records_root == str(wo.root)
    saved = dict(real_adapter.saved_args)
    assert cli_open(wo, real_adapter)["session_id"] == sid
    assert real_adapter.saved_args == saved and len(real_adapter.launches) == 1
    assert len([call for call in real_adapter.calls if call[0] == "send"]) == 1
    assert tree(wo.source) == before


def pending_prelaunch_binding(wo, client, mode):
    """Reproduce the frozen v4 local state left by the old pre-add validation error."""
    definition = catalog(wo.root)["definitions"][0]
    binding = {
        "schema_version": 4,
        "scope": WS,
        "title": "Workspace: R4 pending",
        "root": str(wo.root),
        "profile": client.profile,
        "agent": "codex",
        "session_id": None,
        "provider_session_id": None,
        "context": None,
        "token": None,
        "fingerprint": None,
        "manifest_sha256": None,
        "delivery": "none",
        "known_ids": [],
        "message": PRELAUNCH_ERROR,
        "cwd": str(wo.source),
        "source_id": "source-main",
        "source_identity": definition["identity"],
        "cwd_identity": filesystem_identity(wo.source),
        "catalog_sha256": sha((wo.root / "sources.toml").read_bytes()),
        "definition_sha256": definition_sha(definition),
    }
    path = wo.root / ".aoe/binding.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(binding) + "\n")
    source = resolve_source(wo.root, None, "source-main")
    native_policy.save(
        Repository(wo.root), None, native_policy.LaunchPolicy.choice(mode, wo.root, source)
    )
    return path.read_bytes()


@pytest.mark.parametrize("mode", ["workspace-write", "inherit"])
def test_explicit_retry_after_known_prelaunch_failure_creates_once_and_preserves_history(
    wo, real_adapter, mode
):
    pending = pending_prelaunch_binding(wo, real_adapter, mode)
    assert not real_adapter.list_sessions()
    binding = cli_open(wo, real_adapter, "--new-session", "--codex-sandbox", mode)
    sid = binding["session_id"]
    assert binding["delivery"] == "submitted" and sid is not None
    assert len(real_adapter.launches) == 1
    assert shlex.split(real_adapter.saved_args[sid]) == native_args(mode, wo.root)
    history = list((wo.root / ".aoe/bindings").glob("*.json"))
    assert len(history) == 1 and history[0].read_bytes() == pending
    assert cli_open(wo, real_adapter)["session_id"] == sid
    assert len(real_adapter.launches) == 1


def test_retry_recovers_matching_uncertain_creation_instead_of_launching_duplicate(
    wo, real_adapter
):
    pending_prelaunch_binding(wo, real_adapter, "inherit")
    existing = real_adapter.create(
        wo.source, None, "codex", title="Workspace: R4 pending", add_directory=wo.root
    )
    view = AoEWorkspace(wo.root, None, real_adapter).open(new_session=True)
    assert view.binding.session_id == existing.id and view.context_status == "submitted"
    assert len(real_adapter.launches) == 1
    assert not (wo.root / ".aoe/bindings").exists()


@pytest.mark.parametrize(
    "invalid",
    [
        "title-missing",
        "title-empty",
        "title-control",
        "title-long",
        "agent",
        "claude-mode",
        "mode",
        "no-records",
        "missing-records",
        "missing-source",
        "same-directory",
        "records-in-source",
        "source-in-records",
    ],
)
def test_workspace_invalid_launch_refuses_before_command_transport(tmp_path, invalid):
    source = tmp_path / "code"
    records = tmp_path / "records"
    source.mkdir()
    records.mkdir()
    options = {
        "title": "Workspace: R4",
        "add_directory": records,
        "codex_sandbox": "workspace-write",
    }
    agent = "codex"
    if invalid.startswith("title-"):
        options["title"] = {
            "title-missing": None,
            "title-empty": " ",
            "title-control": "x\ny",
            "title-long": "x" * 201,
        }[invalid]
    elif invalid == "agent":
        agent = "other"
    elif invalid == "claude-mode":
        agent = "claude"
    elif invalid == "mode":
        options["codex_sandbox"] = "danger-full-access"
    elif invalid == "no-records":
        options["add_directory"] = None
    elif invalid == "missing-records":
        options["add_directory"] = tmp_path / "missing"
    elif invalid == "missing-source":
        source = tmp_path / "missing"
    elif invalid == "same-directory":
        options["add_directory"] = source
    elif invalid == "records-in-source":
        nested = source / "records"
        nested.mkdir()
        options["add_directory"] = nested
    else:
        source = records / "code"
        source.mkdir()
    client = CommandTransport()
    with pytest.raises(AoEError):
        client.create(source, None, agent, **options)
    assert not client.calls and not client.rows


@pytest.mark.parametrize(
    "project,agent,mode",
    [
        ("demo", "codex", "workspace-write"),
        ("demo", "codex", "inherit"),
        ("demo", "claude", None),
        (None, "claude", None),
    ],
)
def test_project_and_claude_launch_arguments_remain_compatible(tmp_path, project, agent, mode):
    source, records = tmp_path / "code", tmp_path / "records"
    source.mkdir()
    records.mkdir()
    client = CommandTransport()
    result = client.create(
        source, project, agent, title="Existing behavior", add_directory=records, codex_sandbox=mode
    )
    assert shlex.split(client.saved_args[result.id]) == native_args(mode, records)
    args = client.launches[0]
    assert args[args.index("-g") + 1] == ("research/demo" if project else "research")
    assert args[args.index("--tool") + 1] == agent
