# Research plan: agent-facing interfaces and their cost

This document is the paper-oriented roadmap for the first study. It builds on
[`PROTOCOL.md`](../PROTOCOL.md), which is the frozen experimental design.
Where the two overlap, `PROTOCOL.md` governs the experiment and this document
governs the write-up, the analysis, and the order of work. Nothing here
weakens a constraint in `PROTOCOL.md`.

## 1. The problem, stated plainly

A computer-use agent works in a loop: it observes the current state of an
application, decides on one action, performs it, and observes again. Every
observation is placed into the model's context window as input tokens, and
every decision is emitted as output tokens. The application does not change;
only the *representation* of the application that the agent reads changes.

The same screen can be presented to a model in very different ways:

- as a **screenshot** (pixels the model must visually parse and ground into
  coordinates);
- as an **accessibility or DOM tree** (a verbose text description of the human
  page, including much structure the task does not need);
- as a set of **flat tools** (function signatures with no description of the
  current view, so the model must track state across turns from memory);
- as a **view document** authored for the agent (a compact JSON object naming
  the current view, the entities in it, and exactly the actions that are valid
  right now, with their argument constraints).

These representations differ in two ways that matter for cost and reliability:
how many tokens the same state costs, and how much of the model's effort goes
to *parsing and grounding* the observation rather than to *choosing* the
action. Our claim is that the interface is a control variable, not a fixed
cost of automation, and that a representation authored for the agent can be
both cheaper and more reliable than reusing the human interface.

The applied version of this question — the one that motivates the work but is
not itself the contribution — is whether applications will eventually ship an
agent-facing surface alongside their human GUI, the way they ship an API
today, and whether doing so saves enough tokens and errors to be worth the
authoring cost. The paper does not answer the product question. It provides a
measurement method and evidence about the underlying trade-off.

## 2. What we are assessing

We hold one application, one task set, and one grader fixed, and we vary only
the interface. The four interface conditions are defined in `PROTOCOL.md`:

| ID | Condition | Observation | Actions |
| --- | --- | --- | --- |
| C1 | Screenshot | Image of the human page | Click coordinates, type, scroll |
| C2 | Accessibility / DOM | Text tree of the human page | Click or fill named elements |
| C3 | Flat tools | Function schemas only; no current-view document | Call those functions |
| C4 | View document | JSON for the current view | Invoke an enabled action with typed arguments |

C3 and C4 expose the **same operations at the same grain**. This is essential:
it means any difference between C3 and C4 is attributable to the *view
document* (current-view identity, enabled/disabled flags, argument
constraints), not to a different action vocabulary.

### Research questions

- **RQ1.** Does the interface representation change the agent's token cost,
  step count, task success, and rate of illegal actions, on a fixed task set?
- **RQ2.** Is there a representation that is *Pareto-superior* — no more costly
  and at least as reliable — to reusing the human interface? Specifically, does
  the view document (C4) dominate the screenshot (C1) and the tree (C2)?
- **RQ3.** Is the effect model-agnostic? Does the ranking of conditions hold
  across several general models, or is it an artifact of one model?

### Hypotheses

- **H1.** Cost and reliability differ significantly across conditions.
- **H2.** C4 lies on the cost–reliability efficient frontier; C1 in particular
  is dominated because image observations are expensive and grounding is
  error-prone.
- **H3.** The *ordering* of conditions is stable across general models even if
  the *magnitude* of the gap is not. (`PROTOCOL.md`: the mechanism is assumed
  general; the effect size is not assumed constant.)

## 3. Where the cost comes from (the accounting to measure)

For one run, total input tokens decompose per step:

```
input_tokens(run) = sum over steps of
    [ system_prompt + task_text + prior_actions + current_observation ]
```

The system prompt, task text, and running list of prior actions are roughly
constant across conditions (history is fixed to "task + prior actions +
current observation" by `PROTOCOL.md`). The term that varies by condition is
`current_observation`, and the number of steps varies too. So a useful way to
think about total cost is:

```
input_tokens(run) ≈ per_step_observation_cost(condition) × steps
                     + fixed_overhead × steps
```

This yields the two levers the study measures:

1. **Per-step observation cost.** C1 pays image tokens (large, and only
   sometimes itemized by the provider). C2 pays for a verbose tree. C3 pays
   almost nothing per step (short status objects) but carries no view. C4 pays
   for a compact, task-relevant document.
2. **Step count.** A representation that hides state (C3) or is hard to ground
   (C1) can cause extra steps, retries, and illegal actions, each of which adds
   another full observation to the context. Fewer, better-informed steps can
   make a slightly more expensive per-step representation cheaper overall.

Output tokens and illegal actions are reported separately: illegal actions are
backend rejections and are the cleanest signal that a representation is leading
the model to attempt things that are not currently valid.

## 4. Metrics (dependent variables)

From `PROTOCOL.md`, per run:

- **Success** — order record matches the task specification (binary). For
  refusal tasks, success means the agent correctly did *not* place the
  forbidden order.
- **Input tokens / output tokens** — provider usage, summed over steps,
  including image tokens on C1 when the API reports them.
- **Steps** — model calls until success or the step cap (20).
- **Illegal actions** — backend rejections (HTTP 400 `{"illegal": true}`).

The harness already records all of these per step and rolls them up per run
(`harness/model_loop.py::_summarize`). The grader is execution-based and does
not use another model (`minishop/grader.py`), as `PROTOCOL.md` requires.

**Measurement caveat on image tokens.** Not every provider itemizes image
tokens in a separate usage field; some fold them into `prompt_tokens`. The
harness reads a dedicated `image_tokens` field when present and otherwise
leaves it null (`harness/openai_compat.py::extract_usage`). When comparing C1
across providers, report total input tokens as the primary cost and treat the
itemized image-token count as secondary and provider-dependent.

## 5. How to present the results

Results are reported as **model × condition**. They are never pooled into a
single number across models (`PROTOCOL.md`). The reporting layer that produces
these artifacts from trace files is `harness/report.py`.

1. **Primary figure — cost–reliability frontier.** A scatter plot with median
   input tokens per task on the x-axis (lower is better) and success rate on
   the y-axis (higher is better). Each point is one (model, condition) cell.
   Points that are not dominated by any other point form the efficient
   frontier. H2 predicts C4 is on the frontier and C1 is below-and-right of it
   (more expensive, less reliable). `harness/report.py::pareto_frontier`
   computes which points are on the frontier.

2. **Primary table — per (model, condition).** Success rate, median steps,
   median input/output/image tokens, and illegal actions per step. This is the
   backbone table of the results section; `harness/report.py::markdown_table`
   emits it, and a CSV is written alongside for any external plotting.

3. **Secondary — token breakdown and error composition.** A grouped bar chart
   of median input tokens by condition makes the per-step cost difference
   legible. Illegal-actions-per-step by condition shows where a representation
   induces invalid attempts.

4. **Statistical treatment.** Because tasks are paired across conditions (the
   same 10 tasks run under each condition), report per-task paired differences
   rather than only marginal means, and give bootstrap confidence intervals.
   This is a pilot with a small task set: state the limited statistical power
   plainly and do not over-claim significance.

## 6. Model policy

The main line uses **general, accessible models** that can do all four
conditions through one API (vision plus structured output): default
`gpt-4o-mini`, reported table `gpt-4o`, with additional general models sourced
from Vertex (mid-tier Gemini, Claude Sonnet without the computer-use tool,
Grok) recorded in `harness/models.py`. One model is used for all of C1–C4
within a comparison; models are never mixed across conditions.

**Specialized computer-use models (Claude computer-use, UI-TARS,
Operator-class systems) are deliberately deferred to the end** of the study, as
a final check on whether specialization changes the C1-versus-C4 ranking. They
are out of the main line and are not registered in `harness/models.py`. This
ordering is intentional: we first establish whether the interface effect exists
for ordinary models, and only then ask whether a model trained specifically for
GUIs erases the screenshot's disadvantage.

## 7. Step-by-step plan

Each step names a decision and, where relevant, a prerequisite question that
must be answered before moving on.

- **Step 0 — infrastructure (done).** MiniShop store, four conditions, ten
  tasks, execution-based grader, scripted non-model sanity check, and the model
  loop that writes per-run traces. Prerequisite met: a non-model policy
  completes every expected-success task on C3 and C4 and is correctly rejected
  on the refusal tasks (`python -m harness.scripted`).

- **Step 1 — lock the metrics and the analysis layer (this change).** Freeze
  the token accounting in Section 3, confirm the harness records every
  dependent variable, and add `harness/report.py` so runs turn into the table
  and the Pareto figure. Prerequisite question: *are C3 and C4 exactly matched
  in operations and grain?* (Yes by construction: same action set; C3 omits the
  view document, C4 adds it. Verified in `minishop/tools.py` vs
  `minishop/surface.py`.)

- **Step 2 — main-line run on one general model.** Run `gpt-4o-mini` (then
  `gpt-4o` for the reported table) across C1–C4 on all ten tasks at temperature
  0. Produce the per-(model, condition) table and the cost–reliability frontier.
  Prerequisite question: *is a single pass stable enough at temperature 0?*
  Tool-calling and vision are not perfectly deterministic, so run a small number
  of repeats per cell and report variability.

- **Step 3 — model-agnosticism (RQ3).** Add two or three general models
  (e.g. `gemini-flash`, `sonnet`, `grok-fast`) and check whether the ordering of
  conditions holds. Prerequisite questions: *does every model support all four
  conditions in one API?* If a model is not vision-capable, drop C1 for that
  model and state the limitation (`PROTOCOL.md`). *Is C4's advantage from fewer
  tokens or from constraint-pruning?* Plan an ablation that removes the
  enabled/disabled flags and argument enums from the C4 document, leaving only
  the view and entities, to separate "compact and current" from "constraints
  block invalid actions."

- **Step 4 — specialized models as a final check.** Only after the general-model
  table is stable, add one or more computer-use-specialized systems to test
  whether specialization changes the C1-versus-C4 ranking. Keep them out of the
  main-line comparison and report them as a separate check.

- **Step 5 — write-up.** Structure below.

## 8. Threats to validity

- **External validity.** One synthetic application (a small store). A second
  application is explicitly future work in `PROTOCOL.md`. State this as the main
  limitation and do not generalize beyond "a controlled shopping task."
- **Construct validity of the C4 document.** C4 is hand-authored. Its quality is
  a confound: a badly written view document would understate C4. Author it once,
  freeze it, and describe it fully so the result is reproducible.
- **Confounding C4's two advantages.** Compactness and constraint-pruning are
  separate mechanisms; the Step 3 ablation is what disentangles them.
- **Refusal tasks are easy to pass by inaction.** A do-nothing agent passes a
  refusal task. Report refusal-task outcomes separately from success tasks so a
  high refusal-pass rate cannot inflate the headline success number.
- **Provider usage reporting.** Image-token itemization is provider-dependent
  (Section 4). Anchor cost on total input tokens.
- **Determinism.** Temperature 0 is not full determinism; repeats and
  variability reporting (Step 2) address this.

## 9. Related work to position against

- **Reusing the human interface** — DOM/accessibility-tree agents and
  screenshot/computer-use agents. These are C1 and C2 in our design; the point
  is that they inherit a representation built for humans.
- **Optimizing the human interface for agents** — work that prunes or restructures
  UI trees to be cheaper for LLM agents (e.g. UIFormer-style tree optimization).
  This is adjacent: it improves C2 rather than replacing it with an
  agent-authored surface. We should contrast "optimize the tree" with "author a
  view document."
- **Proposed agent-UI protocols** — emerging JSON/markup protocols for
  agent-facing surfaces (e.g. A2UI). None is a de-facto standard. Our C4 is a
  minimal instance of that idea used here as a measurement probe, not a proposed
  standard.

## 10. Paper structure

1. Introduction — the interface as a control variable; the cost of reusing
   human UIs.
2. Related work — Section 9.
3. Study design — application, conditions (C1–C4), task set, grader, metrics;
   the C3/C4 same-grain constraint.
4. Metrics and analysis — Sections 3–5, including the Pareto method.
5. Results — model × condition table and the cost–reliability frontier; the
   constraint-pruning ablation; model-agnosticism.
6. Threats to validity — Section 8.
7. Discussion — what the evidence implies for shipping agent-facing surfaces;
   the specialized-model check.
8. Limitations and future work — second application, larger task set, the AX
   metric suite (the second paper).
