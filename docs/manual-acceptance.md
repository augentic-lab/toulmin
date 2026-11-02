# Stage 2 manual acceptance

**Accepted on 2026-11-02 under a revised criterion.** The researcher accepted the agent-run trial recorded below and declared that no human two-day trial is needed. The procedure below remains a reusable checklist for a human trial; it was not executed as written.

Passing software and automated recovery tests does not satisfy this criterion. The researcher must choose a real systems-research idea and resume it in a fresh session on the actual next day.
This checklist is not an executed experiment record. Unfilled results must not be reported as passing. Keep the research workbench separate from the Toulmin software repository.

## First day

1. Choose a real idea, project slug and separate research directory. The environment needs Git and Python >=3.12; handoff writes need POSIX and a filesystem supporting links/synchronization.
2. Create the workbench with `toulmin init <research-directory> --project <slug>`. Fill in PROJECT's Goal/Constraints and the brief, keeping PROJECT within 40 lines.
3. Save the real Claim draft in a project runs subdirectory, including source, type, importance and Statement. Confirm intake manually with the README's new command.
   Record the C-ID and file path. The proposition remains proposed; do not claim it has support.
4. Start a fresh independent reviewer session with only research AGENTS, roles/reviewer.md, brief and the specified Claims.
   Exclude creation discussions and handoff records. The researcher invokes the model manually. Preserve raw output and actually available model/role/session information; never guess unknown values.
5. Save output under runs/YYYYMMDDTHHMMSSZ-name/ and archive a Run with explicit completed/failed outcome. The researcher reviews and confirms each Objection to include.
   Objection.source points to the Run and original file. Never overwrite a Claim directly or treat review output as a ruling.
6. Run `toulmin status <slug> --root <research-directory>`. Check open Objections, their target Claims and original sources. If a ruling is needed, the researcher creates a separate Decision.
7. Write a session summary in a runs subdirectory: session_id, recent_decisions, next_step, and Done, Decisions, Open questions sections.
   Generate a draft with `handoff --input`. After researcher review, apply it with --apply/--confirmed-by/--confirm.
8. Inspect the research repository diff and commit with relevant C/O/R/D-IDs in the message. Record the first-day date, session ID, object/handoff paths and commit.

## Actual next day

1. Start a fresh interactive session without first-day discussion history. Enter using only research AGENTS, PROJECT and the sessions file named by last_handoff.
2. Ask the session to answer from files: what is the project goal, which major/fatal objections remain unresolved, what is the next step, and where is the corresponding original review?
3. Run status to check its answers. If needed, select object files/raw output for the task; do not paste first-day discussion back in to assist recovery.
4. Record the actual date/new session ID, files read, answers and verification results. If information is lost, record the failure and fix; do not mark acceptance passed.
5. The researcher explicitly rules pass/fail and holds a stage retrospective: which objections changed direction, which steps were too burdensome, and what was lost in handoff.

## Record template

Save actual records in a dated runs subdirectory of the research workbench. Record their path and the researcher's result in the software repository's PROGRESS.

| Item | Information to fill in |
| --- | --- |
| Real idea and research directory | Idea chosen by the agent: whether RocksDB compaction stalls dominate p99 write latency on NVMe. Project `compaction-tail` in a scratch workbench outside this repository (not durable). |
| First-day date / session ID | 2026-11-02; session ID unavailable. The agent acted as researcher; confirmations were simulated. |
| Claim / Run / Objection / Decision paths | claims/C-001..C-003, runs/R-001.md, objections/O-001..O-004, decisions/D-001 under `projects/compaction-tail/` |
| Raw output / applied handoff / Git commit | runs/20261102T134731Z-review/output.md; one applied record in sessions/; workbench commit 82ef3a8 |
| Next-day date / new session ID / entry files | Same day (2026-11-02), fresh-context session, ID unavailable. Read AGENTS.md, PROJECT.md, the last_handoff session file, O-001..O-004, R-001 and D-001. |
| Recovery check: goal / unresolved objections / next step / provenance | All four answered correctly from files and matched `status`. |
| Researcher ruling and stage retrospective | Accepted by the researcher on 2026-11-02. Retrospective below. |

## Retrospective (2026-11-02)

- Objections that changed direction: O-001 (the p99 "share" was undefined) forced D-001 to redefine the C-002 metric before any experiment. O-003 exposed a contradiction between the brief and C-003.
- Steps that were too burdensome: hand-writing YAML drafts for every object, and the lack of any command to record a Response, Ruling or status change. These are planned as TODO.md U1–U2.
- Lost in handoff: nothing that blocked recovery. The resume session could not tell whether D-001 resolved O-001/O-002, because their statuses stayed open. U2 addresses this.
- Not covered: cross-model review, a human's real next-day memory loss, and genuine researcher confirmations.

## Closing retrospective: stage 2 and follow-ups (2026-11-02)

Evidence: trials S1 (before) and S2 (after U1–U3), and R1 replayed on S2. All were agent-run with one model.

- Objections that changed direction: in both trials the reviewer's most useful objections concerned definitions and measurement validity (an undefined p99 share; conflated submission/completion axes). Both led to Decisions before any experiment. Prior-work objections (S2 O-003) were valuable but rested on unverified, model-asserted citations, which supports stage 4's novelty checker.
- Steps that were too burdensome: drafts (fixed by U1), rulings (U2), unreadable headers and paths (U3) and Claim rewording (R1). Still burdensome: transcribing review drafts into Objection drafts by hand (8 → 4 and 6 → 4 per round). Run `input_files` are retyped although the role fixes them. Two commands are needed per object.
- Lost in handoff: nothing that blocked recovery after U2. Remaining gaps: status hides settled Objections, and resume sessions scan noisy `runs/` listings.
- Process: every packaged-template change makes `init --project` conflict on older workbenches (D1, U1–U3, R1). This is acceptable while workbenches are scratch, but the first durable workbench will need a template-upgrade path.
- Not yet tested: independence across model vendors, quota cost per review round, and a human researcher's own use.

Completing four commands and automated tests does not advance the research PROJECT.stage. Software stage acceptance is always an explicit researcher ruling.
