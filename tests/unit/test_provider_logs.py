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


# R6: token totals from the same logs


def test_codex_usage_is_the_newest_running_total():
    total = {"input_tokens": 800_000, "cached_input_tokens": 730_000, "output_tokens": 15_300,
             "reasoning_output_tokens": 2_600, "total_tokens": 815_300}  # fmt: skip
    path = codex_log(
        {"type": "event_msg", "payload": {"type": "token_count", "info": None}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 1}, "last_token_usage": {"input_tokens": 1}}}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": total, "last_token_usage": {"input_tokens": 59_000},
            "model_context_window": 475_000}}},
    )  # fmt: skip
    usage = provider_logs.reported_usage("codex", CODEX_ID)
    assert usage == provider_logs.SessionUsage(None, 800_000, 730_000, 15_300, 59_000, 475_000,
                                               str(path))  # fmt: skip


def test_claude_usage_counts_each_request_once():
    def reply(key, cached, output):
        usage = {"input_tokens": 5, "cache_read_input_tokens": cached,
                 "cache_creation_input_tokens": 100, "output_tokens": output}  # fmt: skip
        return {"type": "assistant", "message": {"id": key, "model": "m", "usage": usage}}

    claude_log(
        {"type": "user", "message": {"content": "hello"}},
        reply("msg-1", 1000, 50),
        reply("msg-1", 1000, 50),  # the same request, another content block
        reply("msg-2", 3000, 70),
    )
    usage = provider_logs.reported_usage("claude", CLAUDE_ID)
    assert (usage.requests, usage.input_tokens, usage.cached_input_tokens) == (2, 4210, 4000)
    assert (usage.output_tokens, usage.context_tokens, usage.context_window) == (120, 3105, None)


def test_no_usage_records_mean_not_reported():
    codex_log(turn("gpt-6-luna"))
    assert provider_logs.reported_usage("codex", CODEX_ID) is None
    assert provider_logs.reported_usage("claude", CLAUDE_ID) is None  # no log at all
    assert provider_logs.reported_usage("other", CODEX_ID) is None
