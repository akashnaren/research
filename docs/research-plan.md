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

- **Step 1 — lock the metrics and the analysis layer.** Freeze the token
  accounting in Section 3, confirm the harness records every dependent
  variable, and add `harness/report.py` so runs turn into the table and the
  Pareto figure. Prerequisite question: *are C3 and C4 exactly matched in
  operations and grain?* (Yes by construction: same action set; C3 omits the
  view document, C4 adds it. Verified in `minishop/tools.py` vs
  `minishop/surface.py`.)

- **Step 1a — model-free baselines (done).** Two things that must hold before
  any model run, both executable with no API call:

  - *Observation-cost baseline* (`harness/obs_cost.py`). Replay each task's
    canonical path and count, with a fixed reference tokenizer (`o200k_base`),
    the observation tokens each condition imposes per step. This measures the
    "how heavy is one look" term of Section 3 deterministically. First numbers,
    over the success tasks along the minimal path:

    | condition | median obs tokens / task | median obs tokens / step |
    | --- | --- | --- |
    | C1 (screenshot, gpt-4o high-detail estimate) | 6630 | 1105 |
    | C3 (flat tools + schema) | 3073 | 512 |
    | C4 (view document) | 2732 | 453 |

    Reading: text observations are ~2.4x cheaper per step than a screenshot,
    and the view document (C4) is slightly cheaper than flat tools (C3) because
    C3 must resend the tool schema on every call while the C4 document is
    compact. This is only the observation term along the *minimal* path; the
    step-count differences (where C3's lack of a current view is expected to
    cost extra steps and illegal actions) are what the model runs add.

  - *Surface-backend consistency invariant*
    (`tests/test_surface_consistency.py`). The C4 document must never advertise
    an action as available that the backend rejects, and its size enums must
    match stock exactly. This makes the hand-authored C4 a trustworthy upper
    bound. Enforced by tests along every canonical path.

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

This section lists the strands at a high level; the literature-grounded
positioning, the strand-by-strand comparison table, and the honest limits of
the novelty claim are in the "Novelty and positioning" section below.

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

## Novelty and positioning

This section states, grounded in the current literature rather than from
memory, what is genuinely new in this work and what is not. The claims below
were checked against primary sources (papers and official docs); the ones we
could verify are cited at the end of the section, and where a source could not
be confirmed we say so instead of asserting a detail.

### Core contribution

Prior work overwhelmingly asks *which agent or model is better* at operating a
computer, holding the interface's representation fixed as a property of the
benchmark. This study inverts the design: it holds the application, the task
set, the grader, and the model fixed, and treats the **interface
representation itself as the independent variable**, comparing four
representations of the same store (screenshot C1, accessibility/DOM tree C2,
flat tools C3, and a purpose-built JSON view document C4). Because C3 and C4
expose the *same operations at the same grain*, any C3-versus-C4 difference is
attributable to the view document alone — current-view identity, per-action
`enabled` flags, and argument JSON Schemas — and not to a different action
vocabulary. The dependent variables are read on a **cost–reliability (tokens
versus success) Pareto frontier**, an efficiency lens rather than a
success-only leaderboard. That combination — a controlled A/B/C/D of interface
*representation*, with a backend-faithful agent-authored surface as one arm,
measured on a Pareto frontier with a deterministic execution grader — is what
we have not found in the existing literature.

The two intended papers claim different things. **Paper 1 (agent-native UI
protocol)** claims the controlled comparison and the specific agent-authored,
constraint-carrying view document. **Paper 2 (Agent Experience / AX metric
suite)** claims the framing and packaging of tokens, steps, success, illegal
actions, hallucination, and latency into a UX-analogous metric suite for agent
interfaces; the individual metrics are not themselves new (see limitations).

### How this study differs from each strand of prior work

| Prior-work strand | Representative work (verified) | What it does | How this study differs |
| --- | --- | --- | --- |
| DOM / accessibility-tree web agents | Mind2Web; WebArena | Operate the human page from its HTML / accessibility tree; the tree is so large it must be filtered (Mind2Web's MindAct ranks DOM elements with a small LM first). | These are our C2. They inherit and are stuck with the human-derived tree; we treat that tree as one condition among four and compare it against an agent-authored surface under a fixed model and grader. |
| Screenshot / pixel computer-use agents and models | Claude computer use; UI-TARS; SeeClick (and CogAgent-style GUI grounding) | Perceive raw screenshots and emit pixel coordinates / low-level actions; grounding is the central difficulty and screenshots cost ~1–2k tokens each. | These are our C1, and specialized pixel-native models are deliberately deferred to a final check. Our question is not how to ground pixels better but whether a non-pixel, agent-authored representation is Pareto-superior for ordinary general models. |
| Optimizing the human representation for agents | UIFormer ("From User Interface to Agent Interface"); Prune4Web | Automatically prune / restructure the human UI tree (DOM, a11y tree) to cut tokens; UIFormer reports UI representation is 80–99% of agent token cost and achieves ~49–56% token reduction. | Closest in spirit, but it *compresses a human-derived tree* and keeps it faithful to the human DOM. C4 is authored from backend state, not derived from the human page, and we measure it as a controlled arm rather than as a plug-in optimizer. We explicitly contrast "optimize the tree" with "author a view document." |
| Proposed agent-UI protocols / "OpenAPI for GUIs" | A2UI; Model Context Protocol (MCP) | A2UI is a declarative JSON protocol in the *opposite direction* — an agent generates UI for a human renderer. MCP standardizes tools, resources, and prompts (JSON-RPC, JSON-Schema tool inputs) for exposing capabilities to models. | Our C4 is application→agent, not agent→human (A2UI), and is richer than MCP's tools/resources: it is a per-view state-plus-affordance document whose `enabled` flags encode *a priori* action validity, matched in grain to a flat-tools control (C3) so the added value of the document can be isolated. We use C4 as a measurement probe, not a proposed standard. |
| Benchmarks for GUI / web agents | WebArena; VisualWebArena; Mind2Web; WebShop; AndroidWorld; MiniWoB++ | Measure agent/model *capability* (task success, sometimes step/element accuracy) via execution- or state-based grading, with the observation modality fixed by the benchmark. | We reuse the execution-grading idea but not the goal: our fixed variable is the model and our varied variable is the interface. We additionally report a model-free, tokenizer-based observation-cost baseline as a deterministic lower bound, which capability benchmarks do not provide. |

### Distilled differentiators (the ones that hold up)

1. **Interface representation as a controlled independent variable.** App,
   tasks, grader, and model are held fixed; only the representation changes.
   Benchmarks and system papers vary the agent/model and fix the interface, so
   they cannot attribute an effect to representation. This is the strongest and
   most defensible novelty (paper 1).
2. **Matched action grain between C3 and C4.** C3 and C4 share one action set;
   C4 only adds the view document. This isolates the effect of the document
   (current view + `enabled` flags + argument schemas) from the effect of a
   different action vocabulary — an identification move we did not find in prior
   work (paper 1).
3. **A backend-faithful, agent-authored view document (C4).** Unlike C1/C2
   (reuse the human surface) and unlike UIFormer/Prune4Web (compress the
   human-derived tree), C4 is authored from backend state and is kept
   consistent with the backend by a tested surface-consistency invariant. It is
   also distinct from A2UI (agent→human direction) and richer than MCP's
   tools/resources (paper 1).
4. **Constraint-carrying affordances with an ablation.** C4's `enabled` flags
   and argument JSON Schemas prune invalid actions before the model acts, and a
   planned ablation removes the flags/enums to separate *compactness* from
   *constraint-pruning*. The general idea of action masking / constrained
   decoding is old, so the contribution here is the controlled ablation that
   disentangles the two mechanisms, not the idea of constraints (paper 1).
5. **Cost–reliability as a Pareto question.** We ask whether a representation is
   *Pareto-superior* (no more costly, at least as reliable), not merely whether
   success is higher. Token efficiency of UI representations is itself studied
   (UIFormer), but framing representations on a per-model cost–reliability
   frontier — the "AX" efficiency lens — is the contribution here (paper 1 for
   the method; paper 2 for the metric-suite framing).
6. **Deterministic execution grader plus a model-free observation-cost
   baseline.** Execution grading is standard; the smaller genuine addition is
   the deterministic, tokenizer-based observation-cost baseline that gives a
   model-free lower bound on per-condition cost before any API call.

### What this is NOT (honest limits of the novelty claim)

- **"Representation matters for agents" is already known.** Mind2Web filters the
  DOM because it is too large; SeeClick is motivated by HTML being "lengthy and
  occasionally inaccessible"; UIFormer measures UI representation at 80–99% of
  agent token cost. Our contribution is the *controlled measurement* and the
  specific agent-authored surface, not the observation that representation has
  an effect.
- **Execution-based grading is not new.** WebArena, VisualWebArena, WebShop, and
  AndroidWorld all grade by program/state checks. We adopt this rather than
  inventing it.
- **Token-efficient UI representation is not new.** UIFormer and Prune4Web
  already reduce UI-tree tokens; our novelty is treating representation as a
  controlled variable on a Pareto frontier, not the fact that compact
  representations are cheaper.
- **An agent-facing surface is "in the air."** A2UI and MCP both point at
  agent-facing structured interfaces. C4 is one concrete, minimal instance used
  as a probe; we do not claim to propose a standard.
- **Constrained/valid-action masking is an old idea** in RL and tool use; only
  the ablation that separates it from compactness is ours.
- **The AX metric suite (paper 2) is largely synthesis.** Each metric
  (tokens, steps, success, illegal actions, hallucination, latency) already
  exists; the contribution is packaging them as a UX-analogous suite and using
  them as design feedback on interfaces, which is a framing contribution more
  than a new measurement.
- **Scope limits generality.** One synthetic shopping app, ten tasks, general
  (non-specialized) models, and a hand-authored C4 whose quality is a confound.
  These bound the strength of any novelty claim and are detailed in Section 8.

### Key references (verified)

- WebArena: A Realistic Web Environment for Building Autonomous Agents — https://arxiv.org/abs/2307.13854
- VisualWebArena: Evaluating Multimodal Agents on Realistic Visually Grounded Web Tasks — https://aclanthology.org/2024.acl-long.50/
- Mind2Web: Towards a Generalist Agent for the Web — https://arxiv.org/abs/2306.06070
- WebShop: Towards Scalable Real-World Web Interaction with Grounded Language Agents — https://proceedings.neurips.cc/paper_files/paper/2022/file/82ad13ec01f9fe44c01cb91814fd7b8c-Paper-Conference.pdf
- AndroidWorld: A Dynamic Benchmarking Environment for Autonomous Agents — https://arxiv.org/abs/2405.14573
- MiniWoB++ (Reinforcement Learning on Web Interfaces using Workflow-Guided Exploration) — https://arxiv.org/abs/1802.08802 ; docs: https://miniwob.farama.org/
- Anthropic: Introducing computer use (Claude 3.5 Sonnet) — https://www.anthropic.com/news/3-5-models-and-computer-use
- UI-TARS: Pioneering Automated GUI Interaction with Native Agents — https://arxiv.org/abs/2501.12326
- SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents — https://aclanthology.org/2024.acl-long.505/
- UIFormer / From User Interface to Agent Interface: Efficiency Optimization of UI Representations for LLM Agents — https://arxiv.org/abs/2512.13438
- Prune4Web: DOM Tree Pruning Programming for Web Agent — https://ojs.aaai.org/index.php/AAAI/article/download/40772/44733
- A2UI (Agent-to-UI) Protocol — https://a2ui.org/
- Model Context Protocol (MCP) — https://modelcontextprotocol.io/

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
