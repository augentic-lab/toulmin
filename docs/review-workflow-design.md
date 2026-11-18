# R10/R11: continuous critique and explicit review profiles

Status: researcher authorized design and implementation on 2026-11-18. This is an
additive implementation plan, not a scientific ruling or authorization to run paid
research reviews. R10/R11 use existing file ownership, decide and independent-session
boundaries. Development is isolated from concurrent uncommitted UX changes.

## User journey

1. Continue discussing a project in its current native coordinator session.
2. When critique is useful, inspect `toulmin review PROJECT --profile hypothesis --dry-run`.
3. Prepare `toulmin draft review PROJECT --profile hypothesis`; explain Why now and move
   the draft to the existing project proposal directory.
4. Researcher uses `toulmin decide`: inspect actual roles, model IDs, effort, synthesizer,
   inputs, omitted roles, total session cap and local availability limits before applying.
5. Fresh isolated reviewers inspect only their manifests. An independent synthesis runs
   when at least two outputs contain usable drafts. Outputs and failures are archived.
6. Coordinator continues; researcher separately rules on intake. A handoff or replacement
   coordinator is an optional explicit context-management operation.

Stage changes and gates retain their existing meaning. No automatic archive, handoff,
Claim status change, Objection intake or quota-consuming invocation is added.

## R10: guidance and ordering

Replace the old R4 suggestion that a handoff/fresh coordinator should precede new-stage
work. Lead critique with dry-run -> review proposal -> decide. Keep file-derived warnings
and the actual unfinished-handoff journal guard: data-integrity recovery is distinct from
requiring a new handoff. Put the optional context hint after substantive next moves.
Update stage notices, state/map guidance, project guide, user/protocol docs and shipped
copies consistently. Plain open can resume a binding; only explicit replacement starts
another coordinator. Independent review/synthesis session isolation is unchanged.

## R11: configuration and compatibility

Extend tools/models.toml, leaving old files readable and old direct review defaults intact:

```toml
# Existing files retain their limits. Total round cap includes synthesis.
# Named profiles are opt-in; old files need no edits to keep direct review working.
[profiles.hypothesis]
description = "Hypothesis-focused; industry and alternatives are outside this profile"
personas = ["reviewer-skeptic", "reviewer-theorist"]
models = ["sol", "opus"]
synthesizer = "sonnet"

[profiles.full]
description = "All four critique roles"
personas = ["reviewer-skeptic", "reviewer-industry", "reviewer-theorist", "reviewer-why-not-x"]
models = ["sol", "opus"]
synthesizer = "sonnet"

[models.sol]
adapter = "codex"
model = "gpt-6.1-sol"
effort = "high"
env = { CODEX_HOME = "~/.codex-toulmin" }

[models.opus]
adapter = "claude-code"
model = "claude-opus-5-5"
effort = "high"

[models.sonnet]
adapter = "claude-code"
model = "claude-sonnet-5-5"
effort = "medium"
```

These are the researcher's proposed starting hypotheses, not quality/cost rankings or
claims of account access. Exact IDs stay configurable ordinary data. Ship commented
examples rather than changing an existing workspace or auto-selecting a new profile.
Hypothesis is four reviews plus at most one synthesis (five); full is eight plus at most
one (nine). An eight-session cap refuses the full round before any invocation; raising
it is an explicit operator choice. Legacy direct review remains review-only unless a
profile or an explicit synthesizer requests the combined round. Existing decide reviews
retain rotation when no synthesizer is chosen, with total quota now enforced.
Fresh templates set max_runs to nine for the existing eight-review plus synthesis
round. Existing workspaces are not rewritten; their explicit caps remain authoritative.

CLI additions: --profile and --synthesizer on review and draft review. Explicit persona/
model/synthesizer selections override profile fields and are shown in full. No per-role
model router or provider-specific L1 enum. Profiles require nonempty concrete configured
model IDs for reviewers and synthesis. Legacy default models remain possible and the
preview labels them unreported defaults rather than known IDs. Typed optional effort is
translated only at adapter boundaries; conflicting model/effort/fallback selectors in
extra_args must not silently contradict a profile. Never silently retry another model.

ReviewRequest v1 gains optional profile and synthesizer strings; old requests are unchanged.
Older Toulmin readers reject the new fields explicitly; no old data is rewritten and no
migration is required. New request support is additive; seven research object schemas,
gates and intake formats do not change. Document the L2 reason in protocols.md.

## Approval, identity and availability

The preview distinguishes configured alias, requested model ID, effort/default, command,
roles/coverage and synthesis. Show reviews + conditional synthesis = maximum total,
parallelism and timeout; do not estimate subscription dollars from API list prices.
Local preflight checks executable/login/isolation prerequisites without model requests;
explicitly state model/account availability is unverified until the provider responds.
Errors remain errors and are archived; requested identity and provider-reported identity
are distinguished. Credentials/environment values are never printed in plans.

Between preview and apply, compare an approval fingerprint covering selected configuration
(including private environment/extra-argument hashes), exact reviewer prompt hashes and
the synthesizer's static manifest and prompt. Freeze those static synthesis inputs before
reviewers start; append only the resulting archived outputs when synthesis is planned.
A changed config/model/effort/synthesizer/input aborts before markers or model calls and
requires a fresh preview. Starting a direct confirmed command freezes its current plan.

## Provenance and calibration

Archive an additive `review-plan.json` sidecar next to each affected Run's output, without
adding formal Run fields or feeding the profile metadata to reviewers. Record version,
profile/description, common round identity, public selected configuration and its digest,
role/model alias, exact input-prompt digest, and planned review/synthesis/total counts.
Do not archive secrets, environment values or absolute machine paths in this sidecar.
The Run continues to record actual reported model, native identity, duration and usage.
Failed sessions retain plan provenance too. Existing Runs without a sidecar stay valid.

Extend the existing read-only calibration report to group recorded configurations,
separating the same profile name with different configuration hashes. Include review/
synthesis/failure counts, known duration/tokens/provider-reported USD with explicit unknown
counts, and input digests/roles for bounded comparisons. Existing intake outcomes provide
adoption/duplicate counts; neither adoption nor agreement establishes correctness.
Verified actionable findings, omissions, human adjudication time and subscription usage
need actual researcher observations; report these as unmeasured rather than inventing them.
No automatic ranking or claims that a narrow profile improves quality/cost are permitted.

## Executable acceptance

- R10: enter critique with a live fake coordinator; notices and next moves lead to the
  three-step review entry. No archive/replacement/handoff is called or required. Optional
  context hints remain, and existing journal/gate/approval/isolation tests stay valid.
- Config: legacy file/request readable; named profile validation, exact IDs/effort,
  unknown names/fields, missing synthesizer, raw conflicting selectors and empty IDs fail
  clearly without writes or provider sessions.
- Preview: five versus nine total sessions, roles/omissions, concrete models/effort and
  synthesis choice shown; full at cap eight refused. Dry-run/skip/reject launch nothing.
- Decide: changed config/inputs after preview refuse before side effects. Approval executes
  exactly previewed fake sessions and one conditional fresh synthesis; no scientific intake.
- Archive/calibration: sidecar matches exact selected config/input and reported Run usage;
  missing metrics remain unknown; same-name changed configs separate; legacy Runs remain
  included in old reports. Malformed sidecars diagnosed without rewriting records.
- A bounded fake-provider comparison reproduces the 5/9 session-count difference on
  controlled inputs; explicitly not a model-quality, subscription-cost or live access trial.
- Run focused tests then all required checks with optional TUI dependencies. Preserve
  unrelated UX edits. No automatic push or modification of real research workspaces.

## Checked provider documentation

- [Official OpenAI configuration reference](https://developers.openai.com/codex/config-reference/):
  model and model_reasoning_effort are explicit settings; supported effort depends on model/client.
- [Official Claude model configuration](https://code.claude.com/docs/en/model-config):
  exact IDs can pin a model; aliases and available effort depend on provider/client/account.
  Preserve requested settings, surface actual reports/errors, and never assert access from config.
