"""O3 startup refusals must remain actionable, including managed policy/dead panes.

These are screen fixtures only: no native process or trust prompt is operated.
"""

import pytest

from toulmin.adapters.aoe import AoEClient


@pytest.mark.parametrize("dead", [False, True], ids=["live-pane", "dead-pane"])
@pytest.mark.parametrize(
    "failure,detail",
    [
        (
            "Error adding directories: Ignoring --add-dir (/records space) because the "
            "effective permissions do not allow additional writable roots.",
            "additional writable roots",
        ),
        (
            "Error: sandbox mode workspace-write is not allowed by managed requirements.toml",
            "requirements.toml",
        ),
    ],
)
def test_permission_refusal_explains_explicit_local_recovery_without_bypass(dead, failure, detail):
    screen = failure + "\n"
    if dead:
        screen += "\n" * 60 + "Pane is dead (status 1)\n"
    reason = AoEClient._not_prompt("codex", screen)
    assert reason is not None
    assert detail in reason
    assert "--new-session" in reason
    # Name Toulmin's actual recovery surface, rather than advising an unspecified
    # global/native setting change. Managed policy remains an operator boundary.
    assert "--codex-sandbox" in reason or "managed" in reason.lower()
    assert "danger-full-access" not in reason
    assert "--yolo" not in reason


def test_old_permission_text_above_a_healthy_composer_is_not_a_current_refusal():
    screen = (
        "Error: sandbox mode workspace-write is not allowed by managed requirements.toml\n"
        "Recovered in the operator's terminal\n› "
    )
    assert AoEClient._not_prompt("codex", screen) is None
