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
