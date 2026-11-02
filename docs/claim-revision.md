# Claim revision (R1) — design proposal

Status: **proposal, pending researcher decisions Q15–Q18 in TODO.md.** Nothing here is implemented.
Basis: PROGRESS S2 finding 1; design.md §4 (Objection "accepted (claim revised)"), L0 principles 2, 5 and 6.

## Problem

Reviews routinely show that a Claim is worded wrongly rather than false: S1's O-001 (undefined p99 share) and S2's O-001 (submission and completion axes conflated) both ended in "rewrite the Claim".
v1 offers no faithful way to do this:

- Editing the Statement in place silently changes what existing Objections and Evidence refer to, and loses the old wording outside Git (principles 2 and 6).
- `refuted` means the researcher judged the proposition false, which is not what happened.
- Creating a new Claim leaves the old one `proposed`/`challenged` forever, with notices the researcher cannot clear. S2 produced "challenged but no open objections" with no correct move.

## Proposal

Revise by **superseding**: a new Claim carries the revised wording, and the old Claim records what replaced it. This mirrors the existing Decision pattern (`active`/`superseded` + `superseded_by`).

1. **L1 format (additive to v1).**
   - Claim gains the status `superseded`. It is not an initial status; `new` still creates only `proposed`.
   - Claim gains the optional field `superseded_by: Claim reference`. It is required when the status is `superseded` and forbidden otherwise. It must not reference the Claim itself.
   - Like `accepted`/`refuted`, a `superseded` Claim must reference at least one Decision.
   - The successor carries no back-reference. One link avoids two facts that could drift, and status derives the reverse direction.
2. **Ruling (L2/L3).** `toulmin rule <p> C-001 --status superseded --superseded-by C-004 --decision D-002 --confirm`. The rules:
   - The successor must be an existing, non-superseded Claim in the same project.
   - The Decision must name both Claims in `related`.
   - `superseded` is terminal for `rule`. Undoing a mistake is a hand edit plus a Decision, so the tool never deletes a link.
   - The same option family closes U2's limitation: `--adopted-as` (Exploration) and `--evidence` (Spec, repeatable and appended) set the reference fields that those statuses require.
3. **What carries over.** Nothing is retargeted automatically. Objections and Evidence keep pointing at the wording they were written against (principle 2):
   - Open Objections on a superseded Claim still count as open, for example toward G2, until the researcher rules them. The usual rulings are `accepted` ("claim revised", citing the Decision) or re-raising the objection against the successor with the original Run as its source.
   - Evidence on a superseded Claim does not count toward the successor. If it still applies, the researcher records new Evidence that targets the successor and reuses the same provenance.
4. **Status (L2/L3).**
   - Superseded Claims leave the condition table and appear in a `Superseded:` list as chains (`C-001 -> C-004`). `-v` adds their summaries.
   - Each open Objection, valid Evidence, Spec, adopted Exploration and brief `[[C-001]]` reference that points at a superseded Claim gets a notice naming the current successor.
   - A cycle or a chain that ends in a missing Claim is a data error (exit 1).
   - Stored statuses are never changed.

## Worked example (S2)

1. Write D-002 with `related: [C-001, C-004, O-001]`, choosing to restate C-001 as a submission-only claim.
2. Run `draft claim` → edit → `new` to create C-004 with the revised Statement.
3. Run `rule C-001 --status superseded --superseded-by C-004 --decision D-002`.
4. Run `rule O-001 --status accepted --decision D-002 --ruling <file>` ("Claim revised as C-004").
5. Status now shows `Superseded: C-001 -> C-004` and no contradictory notice. Any other open Objection on C-001 is flagged until it is ruled on or re-raised against C-004.

Guidance for the workbench AGENTS template: supersede whenever a change could alter what existing Evidence or Objections mean. Fix typos in place and say so in the commit message.

## Alternatives considered

| Option | Why not recommended |
| --- | --- |
| In-place edit with a `revision` counter and `C-001@2` references | Every reference syntax and the brief checker change; the Statement would have several stored versions in one file |
| Reuse `refuted` plus a free-text pointer | Conflates "false" with "reworded", and the pointer is not machine-checkable |
| Back-reference `revises` on the successor as well | Duplicates the link and can drift; status can derive it |
| Automatically retarget open Objections and Evidence to the successor | Changes what reviewers and evidence actually addressed, and a tool would be ruling on relevance |
| Multi-target Objections (Q14) | Separate concern; still deferred |

## Compatibility and migration

- Additive change within `schema_version: 1`: one new Claim status value and one optional field. Every existing file (including S1/S2) stays valid, and no data needs migration, so no script is required.
- Forward incompatibility: older toulmin builds reject `superseded` as an unknown status. This is acceptable for a single researcher who upgrades one installation; the framework CHANGELOG records it. Bumping to v2 would force migrating every object for no semantic gain.
- Template changes (formats.md, format-examples.md, protocols.md, CHANGELOG, AGENTS) trigger the usual `init --project` conflicts on older workbenches.
- Test fixtures key format examples by kind, so the superseded Claim is documented as a variant rather than a second full Claim sample.
