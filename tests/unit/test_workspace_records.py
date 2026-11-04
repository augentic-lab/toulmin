"""WI3 L1 records: activity, resource descriptions, receipts, rendering and digests."""

import os

import pytest

from toulmin.core.activity import validate_activity
from toulmin.core.codec import decode
from toulmin.core.documents import FormatError
from toulmin.core.material import tree_v1
from toulmin.core.proposals import (
    CharterChange,
    charter_after,
    validate_receipt,
)
from toulmin.core.render import fence, header
from toulmin.core.resources import validate_description
from toulmin.core.workspace import render_initial, validate_charter

RECEIPT = "runs/20261104T101500Z-proposal-" + "a" * 32 + "/receipt.md"
ACTIVITY = """---
schema_version: 1
kind: workspace-activity
scope: {kind: workspace}
created: "2026-11-04T09:30:00Z"
purpose: "p"
recorded_by: {kind: agent, role: explorer, agent: codex, model: null, session_id: null}
capture: {coverage: summary, complete: true, limits: "Final summary only."}
sources: []
---
## Summary
Short.
"""
DESCRIPTION = f"""---
schema_version: 1
resource: trace
title: "T"
status: active
kind: data
location: {{path: shared/data/trace, url: null}}
version: {{method: tree-v1, sha256: {"ab" * 32}, revision: null}}
origin: "o"
revision: 1
previous_sha256: null
receipt: {RECEIPT}
---
## Purpose
P.

## Limitations
L.
"""


def test_activity_summary_requires_limits():
    assert validate_activity(decode(ACTIVITY.encode())).coverage == "summary"
    text = ACTIVITY.replace('limits: "Final summary only."', "limits: null")
    with pytest.raises(FormatError, match="capture.limits"):
        validate_activity(decode(text.encode()))


def test_activity_rejects_unknown_sections_and_project_scope():
    with pytest.raises(FormatError, match="body.Claims"):
        validate_activity(decode((ACTIVITY + "\n## Claims\nx\n").encode()))
    text = ACTIVITY.replace("scope: {kind: workspace}", "scope: {kind: project, project: x}")
    with pytest.raises(FormatError, match="scope"):
        validate_activity(decode(text.encode()))


def test_description_requires_exactly_one_location_and_previous_digest():
    assert validate_description(decode(DESCRIPTION.encode()), "trace").revision == 1
    both = DESCRIPTION.replace("url: null}", 'url: "https://example.org"}')
    with pytest.raises(FormatError, match="exactly one of path or url"):
        validate_description(decode(both.encode()), "trace")
    second = DESCRIPTION.replace("revision: 1\n", "revision: 2\n")
    with pytest.raises(FormatError, match="previous_sha256"):
        validate_description(decode(second.encode()), "trace")
    with pytest.raises(FormatError, match="filename stem"):
        validate_description(decode(DESCRIPTION.encode()), "other")


def test_rejected_receipt_requires_reason_and_no_results():
    text = (
        "---\nschema_version: 1\nkind: workspace-receipt\n"
        f"record: {RECEIPT.replace('receipt.md', 'packet.md')}\nrecord_sha256: {'cd' * 32}\n"
        'disposition: rejected\nactor: "R"\nat: "2026-11-04T10:50:00Z"\napproval_text: null\n'
        "reason: null\nresults: []\n---\nReceipt.\n"
    )
    with pytest.raises(FormatError, match="reason"):
        validate_receipt(decode(text.encode()))
    valid = text.replace("reason: null", 'reason: "Not now."')
    assert validate_receipt(decode(valid.encode())).reason == "Not now."


def test_charter_after_keeps_handoff_fields_and_canonical_section_order():
    before = render_initial("Lab").replace(b"next_step: null", b'next_step: "Plan."')
    change = CharterChange(None, {"Focus": "F.", "Direction": "D."})
    after = charter_after(before, change, RECEIPT)
    document = decode(after)
    charter = validate_charter(document)
    assert charter.revision == 1 and charter.receipt == RECEIPT and charter.next_step == "Plan."
    assert document.body == "## Direction\nD.\n\n## Focus\nF.\n"
    removed = charter_after(after, CharterChange(None, {"Direction": None, "Focus": None}), RECEIPT)
    assert decode(removed).body.startswith("No confirmed direction yet.")


def test_render_quotes_ambiguous_scalars_and_fences_backticks():
    text = header([("a", "true"), ("b", "123"), ("c", "plain/path.md"), ("d", None)])
    assert text == '---\na: "true"\nb: "123"\nc: plain/path.md\nd: null\n---\n'
    assert decode(text.encode()).header == {
        "a": "true",
        "b": "123",
        "c": "plain/path.md",
        "d": None,
    }
    assert fence("x ```` y\n", "diff").startswith("`````diff\n")


def test_tree_digest_refuses_links(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/a.txt").write_text("a\n")
    first = tree_v1(tmp_path / "data")
    (tmp_path / "data/empty").mkdir()  # empty directories are ignored
    assert tree_v1(tmp_path / "data") == first
    os.symlink("a.txt", tmp_path / "data/link")
    with pytest.raises(ValueError, match="only regular files"):
        tree_v1(tmp_path / "data")
