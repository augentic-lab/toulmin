# R11 bounded automated comparison

Status: automated fake-provider comparison, not a live model-quality or account trial.

Executed test:
`tests/cli/test_review_profiles.py::test_bounded_comparison_preserves_common_inputs_and_records_five_vs_nine`.
The test creates two temporary copies of the same project/brief/Claims/manifests and uses
fake Claude/Codex executables. No subscription CLI, network or real research project.

| Plan | Reviewers | Independent synthesis | Actual fake invocations |
| --- | --- | --- | --- |
| hypothesis: skeptic/theorist x two configured model IDs | 4 | 1 | 5 |
| full: four roles x the same two configured model IDs | 8 | 1 | 9 |

Assertions: the four shared role/model prompts have identical SHA-256 digests; each
Run has the expected profile/configuration/input provenance; all 14 invocations are
accounted for; synthesis sees only the approved static inputs and its own outputs.
Additional tests refuse full coverage at cap eight, preserve zero calls on skip/reject,
reject stale configurations/static inputs before approval, and isolate coordinator edits.
Read-only calibration tests distinguish configuration changes, missing metrics and
corrupt sidecars and preserve original files.

This establishes the mechanical session-count/input/provenance behavior only. It does
not measure useful findings, omissions, scientific correctness, real token efficiency,
subscription cost, human adjudication time or real provider availability. Those remain
unmeasured pending a researcher-approved comparison using actual research inputs.
The narrower plan omits industry/alternative coverage; fewer calls do not establish
better value. Preserve no-benefit results and use evidence, not agreement, to decide.
