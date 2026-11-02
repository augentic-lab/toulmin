# Research inquiry walkthrough (UI-R3)

This standalone terminal prototype lets you try research guidance before production integration
or visual-theme selection. It uses the existing optional Textual dependency.

From the repository root:

```sh
uv run --locked --extra tui python prototypes/guided_workbench.py
```

The case starts with a reported observation: some repeated queries are slow. A computation cache
is only one possible direction. Everything is simulated in memory: no model calls, network,
real citations, file import, experimental results or research-project writes. Ctrl+Q discards the
demo. `toulmin tui` remains the unchanged production entry point; this prototype is separate.

## What changed from UI-R2

- Overview names the key unknown, the next action and its reason. Saving a brief stays in Explore;
  it no longer moves directly into review.
- Compare Ideas offers explicitly fixed AI-style suggestions: computation, I/O and lock waits.
  Edit/remove/add hypotheses, or Give Feedback. Your exact correction appears in Context. The
  demo does not pretend to regenerate an AI answer from arbitrary feedback.
- Other Actions offers Inspect Data, Read Papers and Small Test before any Claim/reviewer exists.
  Each starts an editable plan. A plan remains a plan, not evidence.
- Sample Material offers three fictional outcomes for each check. Interpret requires your own
  reason and choice: Test This Lead, Change Direction or Need More Data. The next action follows
  that choice, not an automatic interpretation of the fixture. No choice upgrades evidence,
  changes research stage or closes an issue.
- Handoff includes why the next action matters and a prompt to state what would change direction.
  Previous interpretations retain their source material and reason in Recent Notes on Other Actions.
  Changed plans/material do not inherit a current interpretation from a different source.

## A five-minute trial

Try the controls before reading this route; the point is to find your way without commands.

1. New Sample Project -> Create Sample -> Resume Task. Edit the observation and assumptions in
   the brief; Save Brief. Notice that this leaves you in Explore.
2. Compare Ideas -> Give Feedback. For example: "The workload may be disk-bound; inspect existing
   traces before a new experiment." Record Feedback, inspect Context (F2 on narrow terminals),
   and edit/save the hypotheses. The correction is retained; no model responds automatically.
3. Choose Check -> Inspect Data. Edit the plan, including what would make you change direction,
   then Save Plan -> Sample Material. No Claim or review is needed first.
4. Other Fixture changes the example: A has prominent repeated computation, B prominent I/O waits,
   C insufficient samples. All are fictional. Select Interpret, enter a reason, and choose the
   direction you judge appropriate. Even choosing Test This Lead does not establish a conclusion.
5. Inspect Overview's changed unknown/action/reason. Try an alternative check, or End Session ->
   edit the next step/reason/change condition -> Save + Preview Reopen -> Resume Task.

`Save + Preview Reopen` illustrates resumption in this process, not durable disk recovery.
Home -> Open Sample revisits the sample; Restart Sample clears it. Plans and interpretations
can be revisited. Untriaged suggestions and recorded issues remain distinct in the optional
Review/Resolve path; a saved brief and explicit sample statement are required only for review.
The sample Claim is fixed, not extracted from your edits by a model. Formal G1 remains unmet.

Tab/Shift+Tab moves focus; Enter activates buttons and inserts newlines in editors. Escape opens
Overview, F2 toggles Context at narrow widths without losing draft text/focus, Ctrl+Q exits.
At 60 columns the selector replaces the rail; scroll/Tab reaches text below explanations.

## Feedback we need

Can you identify the largest unknown and why the proposed check matters? Can you choose another
route without being pushed toward a cache or toward AI review? Is it clear where you correct
AI suggestions and where you make a research judgment? Does the return screen preserve the
reason for the next step, not just its name?

## Limits

This wireframe does not validate actual model collaboration, durable persistence, source checking,
real evidence intake, experiments, issue rulings, stage writes or job cancellation. All fixture
results stay labeled fictional; even the paper notes are invented examples, not references.
The three outcome labels record planning judgments in memory, not formal Decision objects.
Q30/Q31 production scope and researcher usability acceptance remain separate from this prototype.

## Actual terminal renders

These SVGs come from Textual, not image generation. The neutral theme is not final styling.
An SVG viewer may substitute a font different from your terminal.

| Moment | Render |
| --- | --- |
| Home | [120 columns](../docs/prototypes/guided-workbench/home-120.svg) |
| Unknown, next action and reason | [120 columns](../docs/prototypes/guided-workbench/overview-120.svg) |
| Observation versus explanation | [120 columns](../docs/prototypes/guided-workbench/explore-120.svg) |
| Competing hypotheses | [120 columns](../docs/prototypes/guided-workbench/hypotheses-120.svg) |
| User feedback retained | [120 columns](../docs/prototypes/guided-workbench/feedback-recorded-120.svg) |
| Three kinds of check | [120 columns](../docs/prototypes/guided-workbench/actions-120.svg) |
| Early validation plan | [80 columns](../docs/prototypes/guided-workbench/validate-80.svg) / [60 columns](../docs/prototypes/guided-workbench/validate-60.svg) |
| Fictional material, no automatic judgment | [120 columns](../docs/prototypes/guided-workbench/material-120.svg) |
| Researcher interpretation | [120 columns](../docs/prototypes/guided-workbench/interpret-120.svg) |
| Changed direction and reason | [120 columns](../docs/prototypes/guided-workbench/decision-120.svg) |
| Simulated return | [120 columns](../docs/prototypes/guided-workbench/resume-120.svg) |
| Optional review plan / triage / issue | [Plan](../docs/prototypes/guided-workbench/review-plan-120.svg), [suggestion](../docs/prototypes/guided-workbench/triage-120.svg), [issue](../docs/prototypes/guided-workbench/issue-120.svg) |

Regenerate the renders:

```sh
uv run --locked --extra tui python prototypes/render_guided_workbench.py /tmp/toulmin-wireframes
```

Automated checks cover navigation and action geometry at 120x36, 80x24 and 60x20, early checks,
feedback, explicit reasoning, interpretation freshness, optional review and no project writes.
These checks cannot establish researcher usability or real model output quality.
