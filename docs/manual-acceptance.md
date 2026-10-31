# Stage 2 manual acceptance (pending)

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
| Real idea and research directory | Researcher selection pending |
| First-day date / session ID | Not performed; do not supply simulated values |
| Claim / Run / Objection / Decision paths | Not created |
| Raw output / applied handoff / Git commit | Not created |
| Next-day date / new session ID / entry files | Not performed |
| Recovery check: goal / unresolved objections / next step / provenance | Not performed |
| Researcher ruling and stage retrospective | Acceptance pending |

Completing four commands and automated tests neither advances the research PROJECT.stage nor establishes manual acceptance of software roadmap stage 2.
