# Pilot protocol (frozen)

This document is the experimental protocol for the first study. Implementation must follow it. Changes belong here first, then in code.

## Question

On one application, with tasks and a grader held fixed, how do four interface conditions differ in task success, input tokens, step count, and illegal actions?

## Independent variable

The interface used to observe and act on the application.

| ID | Condition | Observation | Actions |
| --- | --- | --- | --- |
| C1 | Screenshot | Image of the human page | Click coordinates, type, scroll |
| C2 | Accessibility / DOM | Text tree of the human page | Click or fill named elements |
| C3 | Flat tools | Function schemas only; no current-view document | Call those functions |
| C4 | View document | JSON for the current view | Invoke an enabled action with typed arguments |

C3 and C4 must expose the **same operations at the same grain**. C4 additionally supplies current view identity, enabled/disabled flags, and argument constraints.

## Held constant (pilot)

- Application: MiniShop (catalogue, product, checkout)
- Backend state and hidden-state grader
- Task set (`dualsurface/minishop/data/tasks.json`)
- Decoding: temperature 0
- Step cap: 20
- History: task text, prior actions, current observation only

## Models

The mechanism is hypothesized to be general. Effect size is not assumed to be the same across models.

**Main line of the research (now):** general, publicly accessible models that can do all four conditions in one API: images and structured output. The pilot default is `gpt-4o-mini` (OpenAI). The primary general model for a reported table is `gpt-4o`. Substitutes that meet the same constraint (one checkpoint for every condition) are allowed if recorded in the run metadata: for example Gemini 2.0 Flash, Claude Sonnet without a computer-use tool.

**Not used in the main line:** models or endpoints specialized for computer use (Claude computer-use, UI-TARS, Operator-class systems, GUI-pretrained action models). Those are a **final check**, after the general-model table is stable, to see whether specialization changes the ranking of C1 versus C4.

Never mix models across conditions in the same comparison. If a vision-capable general model is unavailable, drop C1 from that run and state the limitation.

Report results as model × condition. Do not pool models into one number.

## Dependent variables

- Success: order record matches the task specification. Binary.
- Input tokens / output tokens: provider usage, including image tokens on C1. Sum over steps.
- Steps: model calls until success or cap.
- Illegal actions: backend rejection.

Do not use another model as the primary grader.

## C4 document (minimum)

`view`, `state`, `entities`, `affordances[]` with `id`, `enabled`, and `input` JSON Schema. No layout or Markdown projection in the pilot. Authored by a hand-written function of backend state.

## Sanity check before any model call

A non-model script must complete every task that is expected to succeed through C3 and through C4 (`python -m harness.scripted`).

## Deliberately later

JSON versus Markdown; compiling C4 from HTML; authoring cost; a second application; specialized computer-use models; an agent experience metric suite.
