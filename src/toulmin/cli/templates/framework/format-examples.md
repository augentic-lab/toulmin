# L1 v1: examples of all seven object types

These are format examples, not actual research evidence. Assume the project is named demo, the sample Run's input/output files exist, and the researcher actually made the recorded confirmations.
See [formats.md](formats.md) for all field constraints. Each complete Markdown block is a valid sample; the single replacement immediately after it creates an invalid sample of that type.
Validation must distinguish structural validity from authentic provenance/correct conclusions; this section cannot prove the latter.

## Claim — C-001.md

````markdown
---
schema_version: 1
id: C-001
status: proposed
created: "2026-10-31T09:00:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T09:00:00Z"}
type: problem
importance: core
tags: [workload]
validation_plan: "Measure the queueing-delay distribution with a fixed input trace; retain scripts and raw samples."
---
## Statement
Queueing delay is the main source of tail latency under the specified load.
````

Invalid variant: replace `type: problem` with `type: workload`. Report an invalid type; workload may only be a tag.

Superseded variant (valid once C-002 and D-002 exist): set `status: superseded`, add `superseded_by: C-002` and `decisions: [D-002]`. Removing `superseded_by`, or keeping it while the status is not superseded, is invalid.

## Run — R-001.md

````markdown
---
schema_version: 1
id: R-001
status: completed
created: "2026-10-31T10:00:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T10:10:00Z"}
model: example-model
role: reviewer
input_files: [projects/demo/brief.md, projects/demo/claims/C-001.md]
output: projects/demo/runs/20261031T100000Z-review
session_id: null
duration_seconds: null
---
## Summary
An independent reviewer was invoked manually. The raw response is saved in output.md; session ID and duration were unavailable.
````

Invalid variant: replace `status: completed` with `status: running`. Reject an unfinished Run presented for archival; never fill in completed automatically.

## Evidence — E-001.md

````markdown
---
schema_version: 1
id: E-001
status: valid
created: "2026-10-31T10:15:00Z"
source:
  kind: run
  ref: R-001
  path: projects/demo/runs/20261031T100000Z-review/output.md
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T10:20:00Z"}
target: C-001
direction: supports
kind: derivation
grade: model-asserted
provenance:
  - description: "The reviewer's derivation, not yet independently verified."
    path: projects/demo/runs/20261031T100000Z-review/output.md
---
## Material
The reviewer derived the effect of queueing. This material alone cannot support the Claim.
````

Invalid variant: change only grade to verified without supplying verification. Report missing verification method, result and artifacts.

## Objection — O-001.md

````markdown
---
schema_version: 1
id: O-001
status: open
created: "2026-10-31T10:30:00Z"
source:
  kind: run
  ref: R-001
  path: projects/demo/runs/20261031T100000Z-review/output.md
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T10:35:00Z"}
target: C-001
severity: major
---
## Content
A fixed request distribution does not adequately represent production workloads with distribution drift.

## Response

## Ruling
````

Invalid variant: change target to E-001. The reference exists, but an Objection may target only a Claim.

## Decision — D-001.md

````markdown
---
schema_version: 1
id: D-001
status: active
created: "2026-10-31T11:00:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T11:00:00Z"}
related: [C-001, O-001]
---
## Context
The existing derivation does not cover drifting workloads.

## Choice
Keep the original Claim proposed and expand the experiment plan first.

## Rejected alternatives
Do not mark the Claim supported yet.

## Rationale
There is no verified supporting evidence, and an open major Objection remains.
````

Invalid variant: change related to []. Report missing references to the objects being ruled on.

## Exploration — X-001.md

````markdown
---
schema_version: 1
id: X-001
status: pending
created: "2026-10-31T11:10:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T11:10:00Z"}
lens: workload-drift
---
## Content
Compare queueing delay under fixed and gradually changing distributions.
````

Invalid variant: change only status to adopted without supplying adopted_as. Report the missing reference to the resulting Claim.

## Spec — S-001.md

````markdown
---
schema_version: 1
id: S-001
status: todo
created: "2026-10-31T11:20:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T11:20:00Z"}
target: C-001
evidence: []
---
## Requirements
Implement a request replayer with a fixed random seed, recording per-request queueing and service times.

## Acceptance criteria
An independent session runs python replay.py --seed 7 --trace drift.json; it exits 0 and produces per-request CSV.
A validation script must check that CSV request counts match the trace and all times are nonnegative, and report p99 and the runtime environment.
This accepts measurement integrity only. The researcher rules on Claim support from the actual results.
````

Invalid variant: change target to X-001. A Spec must target a Claim, not an unadopted exploration.
