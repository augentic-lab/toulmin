"""R10: optional coordinator context management never blocks independent-review entry."""

from dataclasses import replace

from toulmin.protocols.research_map import AGENT, EITHER, Facts, next_moves
from toulmin.protocols.status import GateItem, GateReadiness


def critique(**changes: object) -> Facts:
    values = dict(
        stage="critique",
        invalid=False,
        gates=(
            GateReadiness("G1", "critique", True, ()),
            GateReadiness(
                "G2",
                "brief-final",
                False,
                (GateItem("C-001 supported or planned", False, "no verified support"),),
            ),
        ),
        proposals=0,
        undecided=(),
        uncovered=(),
        objections=(),
        current_claims=True,
        reviewed=False,
        handoff_due="critique",
    )
    return replace(Facts(**values), **changes)


def test_stage_change_leads_with_dry_run_draft_and_researcher_approval():
    moves = next_moves(critique(), limit=20)
    review = moves[0]
    assert review.actor == AGENT
    assert review.how == "runs/proposals/review-…"
    assert review.text.index("review NAME --dry-run") < review.text.index("draft review NAME")
    assert review.text.index("draft review NAME") < review.text.index("toulmin decide")
    assert "only researcher approval" in review.text
    assert "Continue coordinating in this project conversation" in review.text
    optional = moves[-1]
    assert optional.actor == EITHER
    assert optional.text.startswith("Optional context management")
    assert "continue the current conversation otherwise" in optional.text
    assert "--new-session" in optional.how


def test_optional_context_hint_cannot_displace_review_within_the_move_limit():
    facts = critique(
        proposals=1,
        gates=(
            GateReadiness(
                "G1", "critique", False, (GateItem("core novelty Claim", False, "missing"),)
            ),
            *critique().gates[1:],
        ),
    )
    moves = next_moves(facts)
    assert len(moves) == 3
    assert moves[0].how == "toulmin decide"
    assert "stage critique is past G1" in moves[1].text
    assert moves[2].how == "runs/proposals/review-…"
    assert not any("handoff" in move.text for move in moves)


def test_continuous_entry_preserves_the_changed_material_requirement():
    # C5-F1 still suppresses another round until Evidence or substantive Claims change.
    unchanged = next_moves(critique(reviewed=True), limit=20)
    assert not any(move.how == "runs/proposals/review-…" for move in unchanged)
    assert any(move.text.startswith("Optional context management") for move in unchanged)
    changed = next_moves(critique(reviewed=False), limit=20)
    assert changed[0].how == "runs/proposals/review-…"


def test_continuous_entry_does_not_request_review_without_current_claims():
    moves = next_moves(critique(current_claims=False), limit=20)
    assert not any(move.how == "runs/proposals/review-…" for move in moves)
    assert any("Work toward G2" in move.text for move in moves)


def test_invalid_files_still_take_precedence_over_all_continuity_guidance():
    moves = next_moves(critique(invalid=True))
    assert len(moves) == 1
    assert moves[0].how == "edit the files"
