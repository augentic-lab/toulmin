# Continuous critique and explicit review profiles

Keep the project coordinator conversation open when entering critique. Prepare a
review plan, propose it, and confirm it in `toulmin decide`. Independent reviewers
and synthesis still get fresh isolated sessions with only the allowed inputs.
Handoff and coordinator replacement are optional context-management choices.

## Configure a bounded round

Add named model entries and profiles to the research workspace's `tools/models.toml`.
Do not overwrite the existing limits or review-only Codex home. Exact model IDs below
are the researcher's starting proposal, not evidence of access or a quality ranking.
Effort support depends on the model/client. Check provider errors and actual reports.

```toml
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

[profiles.hypothesis]
description = "Hypothesis-focused; industry and alternatives omitted"
personas = ["reviewer-skeptic", "reviewer-theorist"]
models = ["sol", "opus"]
synthesizer = "sonnet"

[profiles.full]
description = "Four-role coverage"
personas = ["reviewer-skeptic", "reviewer-industry", "reviewer-theorist", "reviewer-why-not-x"]
models = ["sol", "opus"]
synthesizer = "sonnet"
```

Hypothesis plans four independent reviews and at most one synthesis: five sessions.
Full plans eight reviews and at most one synthesis: nine. The existing review.max_runs
must cover the **total**, including synthesis. If it is eight, full refuses before
starting anything; deliberately set nine or choose a smaller plan. Roles omitted from
a narrow profile do not become covered by calling its synthesis.

```sh
toulmin review NAME --profile hypothesis --dry-run
toulmin draft review NAME --profile hypothesis --claim C-001
```

Fill the proposed Why now, review it and put it under the project's runs/proposals/
as instructed by draft. Then run `toulmin decide`. Explicit --personas/--models
on review, --persona/--model on draft review, and --synthesizer on either command
override the corresponding profile selections. Decide displays the actual selection.
Only apply or an explicit direct --confirm starts sessions and consumes quota.
Changes to selected configuration or static reviewer/synthesizer inputs between
preview and apply require another preview. Coordinator edits during a running round
do not change its frozen static inputs. New outputs are added only to synthesis.

## Read the preview honestly

It shows aliases, requested model IDs, effort or unreported defaults, adapter/command,
coverage, synthesizer, total count, parallelism and timeout. Local checks confirm
only executable/login/isolation prerequisites; they do not prove model entitlement.
There is no automatic substitute. A provider-reported identity different from an
explicit request is archived as a failed profile session with the raw answer retained.
When a tool does not report model identity, it remains unknown in the plan record;
the existing Run model can be the requested fallback and is not proof of service.
No currency estimate is inferred from session count or API prices.

## Compare recorded results

```sh
toulmin calibration --project NAME --root ROOT
```

Affected outputs include an auxiliary review-plan.json with nonsecret configuration
and input digests. The new profile section separates same-name changed configurations;
it shows failures, aggregate session-seconds (not parallel wall-clock latency), reported
tokens/USD with unknown counts, roles and input fingerprints, and intake outcomes.
Secrets and environment values are never printed or placed in this sidecar.
Legacy Runs/configs/requests remain readable and their ordinary reports remain included.
Malformed sidecars are diagnosed without changing the underlying research files.

Intake/adoption, agreement and Objection count are not scientific correctness. For a
real bounded comparison, keep common role inputs fixed and record verified actionable
findings, important omissions, human adjudication time and actual subscription usage.
Those metrics remain unmeasured until someone records them; retain a no-benefit result.
The automated fake-provider comparison in tests/cli/test_review_profiles.py verifies
five versus nine sessions and identical shared review inputs, not model quality,
subscription savings or live account access. See review-profile-trial.md.

Compatibility: review-request schema v1 accepts optional profile/synthesizer strings.
Old requests/configs need no migration; older software rejects the new request fields.
Existing direct `review` remains review-only without a profile or --synthesizer. Existing
combined decide rounds still rotate synthesis if no explicit selection is given, but
now enforce the total session cap. No scientific object or gate schema changes.

Provider references checked for this implementation:
[OpenAI configuration](https://developers.openai.com/codex/config-reference/) and
[Claude model configuration](https://code.claude.com/docs/en/model-config).
