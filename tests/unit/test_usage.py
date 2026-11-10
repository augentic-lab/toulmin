"""R6: the usage.json archive file and the tools' usage records; no model is run."""

import pytest

from toulmin.core.usage import Usage, claude_usage, codex_usage, decode_usage, encode_usage


def test_claude_input_sums_uncached_and_cache_tokens_and_keeps_the_record():
    result = {
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 2000,
                  "cache_creation_input_tokens": 300, "output_tokens": 400},
        "modelUsage": {"claude-x": {"costUSD": 0.05}},
        "total_cost_usd": 0.05,
    }  # fmt: skip
    usage = claude_usage(result)
    kept = {"usage": result["usage"], "modelUsage": result["modelUsage"]}
    assert usage == Usage("claude", 2310, 2000, 400, None, 0.05, kept)
    assert claude_usage({"result": "no usage"}) is None


def test_codex_sums_turns_and_leaves_an_unreported_count_unknown():
    events = [
        {"type": "thread.started"},
        {"type": "turn.completed", "usage": {"input_tokens": 5, "cached_input_tokens": 4,
                                             "output_tokens": 3}},
        {"type": "turn.completed", "usage": {"input_tokens": 7, "cached_input_tokens": 1,
                                             "output_tokens": 2, "reasoning_output_tokens": 1}},
    ]  # fmt: skip
    usage = codex_usage(events)
    assert (usage.input_tokens, usage.cached_input_tokens, usage.output_tokens) == (12, 5, 5)
    assert usage.reasoning_output_tokens is None  # the first turn did not report it
    assert codex_usage([{"type": "thread.started"}]) is None


def test_round_trip_and_refusals():
    usage = Usage("codex", 12, 5, 5, None, None, {"turns": []})
    assert decode_usage(encode_usage(usage)) == usage
    for raw in (b"[]", b'{"schema_version": 2, "tool": "x"}', b'{"schema_version": 1}',
                b'{"schema_version": 1, "tool": "x", "input_tokens": -1}', b"\xff"):  # fmt: skip
        with pytest.raises(ValueError, match="usage.json"):
            decode_usage(raw)
