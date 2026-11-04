"""WX3: model reports from native session logs, in temporary CLI homes only (see conftest)."""

import json
import os
from pathlib import Path

import pytest

from toulmin.adapters import provider_logs
from toulmin.adapters.provider_logs import reported_model

CODEX_ID = "01a1a775-aead-7141-b726-f4bd59118453"
CLAUDE_ID = "5d0f6a1e-2b7c-4c1e-9f2a-0c3d4e5f6a7b"


def lines(path: Path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in records))
    return path


def codex_log(*records, provider=CODEX_ID):
    home = Path(os.environ["CODEX_HOME"])
    name = f"rollout-2026-11-04T16-47-49-{provider}.jsonl"
    return lines(home / "sessions/2026/11/04" / name, *records)


def claude_log(*records, provider=CLAUDE_ID):
    home = Path(os.environ["CLAUDE_CONFIG_DIR"])
    return lines(home / "projects/-tmp-serving" / f"{provider}.jsonl", *records)


def turn(model, effort="medium"):
    return {"type": "turn_context", "payload": {"model": model, "effort": effort}}


def test_codex_reports_the_latest_turn():
    path = codex_log(
        {"type": "session_meta", "payload": {"model_provider": "openai"}},
        turn("gpt-older", "low"),
        "not json {",
        turn("gpt-6-luna"),
        {"type": "event_msg", "payload": {"thread_settings": {"model": "ignored"}}},
    )
    report = reported_model("codex", CODEX_ID)
    assert report == provider_logs.ModelReport("gpt-6-luna", "medium", str(path))


def test_claude_skips_synthetic_messages_and_keeps_effort():
    claude_log(
        {"type": "user", "message": {"content": "hello"}},
        {"type": "assistant", "effort": "high", "message": {"model": "claude-opus-5-5"}},
        {"type": "assistant", "message": {"model": "<synthetic>"}},
    )
    report = reported_model("claude", CLAUDE_ID)
    assert (report.model, report.effort) == ("claude-opus-5-5", "high")


@pytest.mark.parametrize(
    ("agent", "provider"),
    [
        ("codex", None),
        ("codex", "*"),
        ("codex", "../../etc"),
        ("gemini", CODEX_ID),
        ("codex", "a" * 8),
    ],
)
def test_unknown_or_unsafe_lookups_report_nothing(agent, provider):
    codex_log(turn("gpt-6-luna"))
    assert reported_model(agent, provider) is None


def test_unrecognized_values_are_not_reported():
    codex_log(turn("has a space"), turn("bad\nmodel"))
    assert reported_model("codex", CODEX_ID) is None
    codex_log(turn("gpt-6-luna", effort="Very High!"))
    assert reported_model("codex", CODEX_ID).effort is None


def test_a_symlinked_log_is_ignored(tmp_path):
    real = lines(tmp_path / "elsewhere.jsonl", turn("gpt-6-luna"))
    link = Path(os.environ["CODEX_HOME"]) / f"sessions/2026/11/04/rollout-x-{CODEX_ID}.jsonl"
    link.parent.mkdir(parents=True)
    link.symlink_to(real)
    assert reported_model("codex", CODEX_ID) is None


def test_only_the_tail_is_scanned_across_block_boundaries(monkeypatch):
    monkeypatch.setattr(provider_logs, "BLOCK", 64)
    monkeypatch.setattr(provider_logs, "TAIL_LIMIT", 1024)
    filler = [{"type": "event_msg", "payload": {"n": n}} for n in range(60)]
    codex_log(turn("gpt-early"), *filler)
    assert reported_model("codex", CODEX_ID) is None  # beyond the scanned tail
    codex_log(turn("gpt-early"), *filler, turn("gpt-6-luna"), *filler[:5])
    assert reported_model("codex", CODEX_ID).model == "gpt-6-luna"
