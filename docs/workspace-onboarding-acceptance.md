# WO3–WO5 supervisor live trial recipe

Status: **NOT RUN by this worker.** Automated fake-service results are technical evidence,
not live provider evidence or researcher usability acceptance. Root owns this separately
authorized stage after review/integration; do not run it against an actual research session.
Preserve Weekly-Projects source data and session d4faf008257a406b. Root may rebuild the
explicitly disposable weekly-projects-research records folder; no other deletion is implied.

Use separate disposable committed Git fixtures for code-writing/Chief trials. For a read-only
inventory of Weekly-Projects, keep it as SOURCE reference and choose an already existing,
non-overlapping disposable working fixture with --work-at. Never copy, edit or remove the
original source as an intake effect. Root chooses the actual paths and isolated AoE profile.

## Technical regression status

Both approved fake-only rebind fixture amendments are applied. Regression cases cover unmanaged
writers at the selected source's old/new checkout, a moved old inode, unknown inventory/
lifecycle, and an unrelated source's writer that must not block rebind. Bind checks only
the selected source and preserves all other associations/local entries.

Supervisor R1–R3 regressions cover malformed portable types/strict versions, unknown native
identity in operational Runs, and every workspace v2 receipt family through confirmed
handoff/discovery/restoration, including rejection and tampering. These automated results
do not establish real provider behavior or researcher usability. Independent final Chief
review and the live steps below remain separate pending evidence.

The v1 catalog receives the same check: old/new/moved-inode writers and unknown inventory
refuse, while unrelated/no-writer controls retain exact v1 catalog bytes/roles/identity.
Unknown matching lifecycle refuses; known archived sessions need not block. Preview and
offline status have fake-client sentinels proving they query no native tool, including
when a saved native binding is present. These are technical regression results only.

Root reported 18 real A/B/C CLI actions passed on 092510d with the original source
unchanged, followed by R4: workspace Codex open failed before creating a session. The
real adapter rejected an explicit workspace sandbox choice. R4 regressions exercise the
real adapter, CLI, policy and context above fake command transport, including exact saved
workspace-write/inherit arguments and pending-binding recovery. Root's native retest and
final independent review remain pending; an expired Claude OAuth login blocked review,
which is not a code verdict. These results are not researcher usability acceptance.

Root also reported R5: a valid task-context inventory produced a false missing-seal
diagnostic before a successful task preview/submission. Discovery now uses the declared
change-packet path grammar before reading seals. Real CLI regressions with generated
task/native archives retain diagnostics for genuinely missing seal/packet, tampering and
wrong packet kind, and still offer valid changes. Root owns the live recheck; no archive
was deleted or relabeled to conceal the error.

## A: understand and work with zero projects

```sh
toulmin onboard SOURCE --root ROOT_A --init --register-source source-main
toulmin decide --workspace --root ROOT_A
toulmin status --workspace --root ROOT_A
toulmin map --workspace --root ROOT_A
toulmin source list --workspace --root ROOT_A
```

Inspect inventory coverage/exclusions, proposed overview/pins/roles/seal, then apply in the
operator's terminal. Record the operator approval separately from a researcher ruling.
Check zero child directories, one workspace source definition/working association, confirmed
overview, ignored local binding, no Claim/Spec/Decision and unchanged SOURCE bytes/Git state.
On a second fresh A root, reject and replay rejection: registration/overview/children must
stay absent and the original rejection actor/time must remain unchanged.

```sh
toulmin open --workspace --root ROOT_A --profile TRIAL_PROFILE --no-attach
# If no saved Codex choice and no interactive terminal, explicitly select one:
toulmin open --workspace --root ROOT_A --profile TRIAL_PROFILE --no-attach \
  --codex-sandbox workspace-write
```

Record the actual native cwd, persisted AoE arguments, selected source/checkout pins and
permission display. Native trust/update choices belong to the operator; do not synthesize
them or retry with broader access. Resolve any native prompt, then run the exact printed
`aoe refresh --workspace --root ROOT_A --profile TRIAL_PROFILE` command. Read the announced
tracked context plus ignored local.json, run its exact ack_command, and verify acknowledged.
Record that preparation/submission/attach alone did not claim acknowledgment.

For the known R4 prelaunch failure, retain the failed binding and inspect the selected
profile first. If it contains no matching session, explicitly retry the pending launch:

```sh
aoe -p TRIAL_PROFILE list --json
toulmin open --workspace --root ROOT_A --agent codex --profile TRIAL_PROFILE \
  --codex-sandbox workspace-write --new-session --no-attach
```

Choose `inherit` instead only when that is the intended native restriction. This retry
archives the failed v4 binding and checks for an existing matching creation before adding
one. If a candidate already exists, run `open` without a new sandbox flag to recover its
identity and retain its saved permissions; inspect ambiguous candidates before binding.
Do not delete the pending binding or launch another writer to work around uncertainty.

Discuss one small measurement, append a correctly formatted unconfirmed notebook entry
with `toulmin workspace note --root ROOT_A --input ENTRY`,
and make a reviewed understanding update. Confirm that notes/overview changes stale the
context and refresh stays at the same pinned checkout. Root notebook is not a transcript.

## B/C and later derivation

Prepare a real v1 project-creation input with a concrete independent question, included/
excluded scope and initial Brief/minimal experiment (workspace-formats section 9). Choose
new names; an existing/empty/damaged child name must refuse rather than continue it.

```sh
# B starts a DIFFERENT missing/empty records root:
toulmin onboard SOURCE --root ROOT_B --init --project latency \
  --project-input PROJECT_INPUT --register-source source-main
toulmin decide --workspace --root ROOT_B
# C can target A, which still has zero children:
toulmin onboard SOURCE --root ROOT_A --project latency \
  --project-input PROJECT_INPUT --source-id source-main
toulmin decide --workspace --root ROOT_A
# Later another independent project shares the source without repeated intake:
toulmin project propose throughput --root ROOT_A --input THROUGHPUT_INPUT \
  --source source-main --working-source source-main
toulmin decide --workspace --root ROOT_A
```

Record B's single new child, source roles, v1 creation provenance/two receipts and unchanged
source. Record C's exact reuse: no duplicate definition/local rewrite, no root charter/
overview change and unchanged old children/roles. Repeat C using a distinct fixture checkout
with `--register-source source-fork`; verify new workspace reference and preserved working
selection. Try --work-at in a separate fixture: C changes only the NEW child's working role.
Later derivation must retain workspace history/code and start no second writer.

## Session restoration, replacement and handoff

Open only one writer per checkout. A simultaneous workspace/project/profile writer at the
same path/inode must refuse without sending to, killing or reconfiguring the old session.
Archive the old trial session before explicitly opening its child or replacement.

```sh
toulmin open latency --root ROOT_B --profile TRIAL_PROFILE --no-attach
# Prepare a workspace handoff INPUT with Done/Confirmed changes/Pending ideas/Open questions:
toulmin aoe handoff --workspace --root ROOT_A --input HANDOFF_INPUT
toulmin decide --workspace --root ROOT_A
# After the operator archives the old native session in its AoE profile:
toulmin open --workspace --root ROOT_A --profile TRIAL_PROFILE --new-session --no-attach
```

Record fresh-session restoration from applied handoff, confirmed overview/source pins and
labeled notes; no sibling/root-notebook injection into child context. Check native resume
and restart keep persisted permission args and do not turn partial native logs into a full
transcript. Change a working selection in a disposable root: refresh/open must not redirect
the old binding, and explicit same-scope replacement must retain old contexts/binding history.

## Workspace-only engineering

Use a clean disposable Git fixture, not Weekly-Projects or a live native writer's checkout.
Chief owns its distinct worker worktree. No Claim, Spec or project is required.

```sh
toulmin draft task --workspace --source source-main --name bounded-helper --root ROOT_A
toulmin task preview --workspace TASK_FILE --root ROOT_A
toulmin decide --workspace --root ROOT_A
# Resolve Chief's own native trust prompt and use its existing kickoff/watch workflow.
toulmin task import --workspace TASK_FILE --root ROOT_A
toulmin task import --workspace TASK_FILE --root ROOT_A --confirm --confirmed-by OPERATOR
```

Fill an actual goal/scope, committed baseline, checks, protected paths, tool/command, budget
and trust choice before preview. Inspect the frozen portable submission and ignored exact
local export. Record exact Chief ID/contract/repo/base and manual kickoff. Import done or
abandoned output twice: exactly one operational run.md, private raw artifacts with portable
hashes, no root R-NNN IDs, scientific objects, auto-merge/push/check execution or gate changes.

For each journey retain commands, resolved paths/scope, seals/receipts, observed cwd/args,
context/ack paths and limitations. Label operator approvals and AI-run observations honestly.
Root reviews these technical results; the researcher supplies a separate usability ruling.
