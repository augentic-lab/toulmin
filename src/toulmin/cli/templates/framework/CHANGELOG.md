# Framework changes

## v1 — Skeleton

- Data and protocols follow formats.md and protocols.md. No older persisted objects to migrate.
- AI research output is archived before confirmed intake. Handoff changes non-ruling fields only.
- Stages: explore, critique, brief-final, build, accept, done. Specs are prepared before Build.
- Record future L2 changes here. L1 changes require impact assessment and migration of existing data.
- Handoff drafts require explicit confirmation before recoverable session/PROJECT updates;
  content digests and previous_handoff identify applied history without an index.
- Independent roles follow their input exclusions; interactive resident context must not
  cause reviewers to load handoffs or discussion history.
- 2026-11-02 (L2 note): stage acceptance is a researcher ruling on recorded trial evidence,
  not necessarily a human two-day trial. No object format or command behavior changed.
- U1 (L2 note): `toulmin draft` writes skeletons to runs/drafts/; intake rejects unfilled
  `<fill: ...>` placeholders; `TOULMIN_ACTOR` may supply the default confirmer. v1 unchanged.
- U2 (L2 note): `toulmin rule` records a confirmed status change, Response or Ruling. Status
  changes need an active Decision naming the object; text is appended, never deleted.
- U3 (presentation only): generated headers follow contract field order without folding;
  object timestamps use whole seconds. Older files stay valid; no migration.
- R1 (L1, additive within v1): Claim status `superseded` with `superseded_by`; rule sets it
  and the other status-required links. Older builds reject the new status; no migration.
- C1 (L1/L2, additive within v1): reviews end with a fenced yaml draft block; `toulmin intake`
  takes chosen drafts in as Objections and appends outcomes to intake.md beside the raw
  output. Object fields unchanged; no migration.
- C2 (L1/L2, additive): role files for independent sessions carry an input manifest;
  `toulmin inputs` and `draft run --role` compute input_files. Adds four reviewer personas
  and the synthesizer contract. Object formats unchanged; no migration.
- C3 (L2/L3): `toulmin review` runs read-only headless reviews (Claude Code, Codex) per
  persona x model, archives prompt/output/log and records completed or failed Runs.
  Configuration in tools/models.toml. Object formats unchanged; no migration.
