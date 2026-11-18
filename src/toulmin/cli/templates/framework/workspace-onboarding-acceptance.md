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

## Known technical follow-up before the live trial

Source rebind currently reconciles managed bindings only; an unmanaged live session in
another profile, a moved old checkout inode, or unknown all-profile inventory can escape
that local check. Native launch already checks all profiles. Four disposable proposed
rebind cases are expected RED and must not be reported as passing compatibility evidence.
A narrow approved-test amendment is awaiting Chief approval: add the existing fake native
fixture to the successful-bind case, then add these four cases and strengthen the L3 guard.
Do not call WO3/WO5 complete or begin a final live rebind trial before this is addressed.

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
