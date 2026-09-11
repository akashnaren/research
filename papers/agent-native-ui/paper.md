# The Interface Is a Variable: Measuring the Cost and Reliability of Purpose-Built UI Representations for LLM Agents

*Working draft. Authors: TBD.*

> Status note (remove before submission): this is an in-progress draft. Sections
> backed by data are written; sections marked *(forthcoming)* await runs listed
> in [`paper-outline.md`](paper-outline.md). Reported numbers are a
> single model (`gemini-2.5-flash`) on a single synthetic application and are
> explicitly provisional.

## Abstract

Language-model agents increasingly operate software by consuming interfaces that
were designed for people: screenshots, accessibility trees, and document object
models. We ask whether the interface *representation* (how an application presents
its state and available actions to an agent) is better understood as a control
variable than as a fixed cost of automation. Holding the application, the task
set, and an execution-based grader (a deterministic checker over backend state,
never a model judge) constant, we compare four representations of the same
store: a screenshot (C1), an accessibility tree (C2), a flat tool catalog (C3),
and a purpose-built JSON *view document* (C4) that names the current view and the
actions valid within it. We measure task success, token cost, step count, and
illegal actions (actions the backend rejects), and report a cost-reliability
frontier with paired per-task inference. On a first model, representations that
reuse the human interface are clearly dominated: the screenshot (C1) costs
roughly ten times the tokens of the cheapest representation and completes fewer
than a third of tasks. Among the structured representations the trade-off is
subtler and model-dependent: the view document (C4) reduces steps but, on this
simple application and this model, does not yet justify its token overhead over
a flat tool catalog (C3). We frame these results as a measurement method and a
first data point, and identify where the advantage of a purpose-built agent
surface is expected to emerge.

## 1. Introduction

An agent that operates software runs a loop: it observes the current state of an
application, decides on one action, performs it, and observes again. Every
observation the agent reads enters the model's context as input tokens, and
every decision is emitted as output tokens. The application itself does not change
across this loop. Only the *representation* of it that the agent reads does.

Today that representation is almost always one built for humans. Three inherited
channels dominate practice, and each fails the agent in a different way.

1. **Screenshots** (our C1). The model must visually parse pixels and ground them
   into click coordinates. Grounding is a known failure mode of GUI agents
   (SeeClick; UI-TARS; Claude computer use). Image cost is a function of
   viewport resolution, not of how much the page actually says, so a blank page
   and a busy page at the same size cost the same. On the MiniShop viewport the
   model-free baseline already prices one look at about 1105 image tokens,
   versus a few hundred for a compact text document (Section 6.1).
2. **Accessibility or DOM trees** (our C2). The model reads a verbose text tree
   built for assistive technology. Mind2Web filters that tree because it is too
   large; UIFormer measures UI representation at 80 to 99 percent of agent
   token cost. The tree also names elements that the backend will reject, so
   named clicks become illegal actions.
3. **Flat tools** (our C3). The model gets function schemas and a short status
   object, with no current-view document. This is close to how MCP exposes
   capabilities. It is cheap per call once the schema is paid, but the model
   must remember which view it is on, which actions are valid, and which
   arguments are legal. That memory burden is light on a tiny store and is
   expected to grow with application complexity.

None of these three was designed to let an agent see, cheaply and
unambiguously, *what is true now and what may be done next.* An
**agent-native** alternative (our C4) is a view document authored from backend
state: current view, entities, and affordances with `enabled` flags and argument
schemas. It is not a better screenshot and not a pruned DOM. It is a
projection of the same backend the grader already trusts.

This paper takes the position that the interface representation is a **control
variable**, not an unavoidable cost of automation, and that a representation
authored for the agent can change how many tokens a task costs and how
reliably it completes. The applied stake is whether shipping such a surface
(the way applications already ship an API) can pay for itself in tokens and
errors. We do not answer that product question. We measure the underlying
trade-off on one application. To test this cleanly we hold everything else fixed (one
application, one task set, one deterministic grader, one model at a time,
temperature zero) and vary only the representation across four conditions
(Section 4). Two of these reuse the human interface (the screenshot (C1) and the
accessibility tree (C2)); one is the common flat tool catalog (C3); and one is a
purpose-built *view document* (C4) that states the current view, the entities in
it, and the actions that are valid right now, with their argument constraints.

The applied motivation is the prospect that applications might one day expose an
agent-facing surface alongside their human interface, much as they expose an
API today. We treat that as motivation, not as our contribution. Our
contributions are:

1. A controlled method for measuring interface representations for agents at
   **matched action grain**, so that differences are attributable to the
   representation rather than to a different set of operations (Section 4).
2. A **cost-reliability (Pareto)** framing (a representation is preferred only
   when nothing else is both cheaper and at least as reliable) with **paired
   per-task inference** (comparing conditions task-by-task with bootstrap
   confidence intervals), rather than a success-only leaderboard (Section 5).
3. First evidence on one application and model, including a **model-free
   observation-cost baseline** and an execution-based grader, showing that
   human-surface representations are dominated while the structured
   representations present a subtler, model-dependent trade-off (Section 6).

These contributions answer three research questions, stated in
[`research-plan.md`](research-plan.md) and held fixed by
[`PROTOCOL.md`](PROTOCOL.md):

- **RQ1.** Does the interface representation change token cost, step count, task
  success, and illegal-action rate on a fixed task set?
- **RQ2.** Is there a representation that is Pareto-superior (no more costly,
  and at least as reliable) to reusing the human interface? In particular, does
  the view document (C4) dominate the screenshot (C1) and the accessibility
  tree (C2)?
- **RQ3.** Is the ordering of conditions stable across general models, or is it
  an artifact of one model?

The corresponding hypotheses are: **H1**, cost and reliability differ across
conditions; **H2**, C4 lies on the cost-reliability frontier and C1 in particular
is dominated; **H3**, the *ordering* of conditions is stable across general models
even if the *magnitude* of the gap is not. PROTOCOL.md states the mechanism as
general and the effect size as not assumed constant. On the first model, H1 is
supported at a coarse grain (human surfaces versus structured conditions), H2
is not supported for C4 versus C3, and H3 is untested.

## 2. Important terms

This section defines the technical and coined terms used throughout the paper so
that later sections can refer to them without re-deriving them. Each definition
is consistent with how the term is used in the study.

- **Interface representation.** The form in which an application's state and
  available actions are presented to an agent. This is the study's independent
  variable.
- **Condition.** One of the four representations compared: screenshot (C1),
  accessibility tree (C2), flat tools (C3), and view document (C4).
- **View document (C4).** A purpose-built JSON object stating the current view,
  its state and entities, and the affordances valid now, each with an `enabled`
  flag and an argument schema.
- **Flat tools (C3).** A stateless catalog of callable functions with no
  current-view document. The model must track state itself.
- **Screenshot (C1).** A rendered image of the human page. The agent acts via
  coordinates, typing, and scrolling.
- **Accessibility tree (C2).** A text tree of the human page (roles and names).
  The agent acts on named elements.
- **Affordance.** An action the interface exposes, with an identifier, an
  `enabled` flag, and an argument schema.
- **Enabled flag.** A boolean on an affordance indicating whether it is valid in
  the current state.
- **Matched action grain.** The property that flat tools (C3) and the view
  document (C4) expose the same operations, so any difference between them is
  attributable only to the view document.
- **Illegal action.** An action the backend rejects (HTTP 400). A validity
  violation.
- **Malformed action.** A model response that is not a usable action (wrong
  shape). Tracked separately from illegal actions.
- **Ignored-affordance rate.** How often a model attempts an action the
  interface marked unavailable (the t10 phenomenon).
- **Step / step cap.** One observe, decide, act cycle. The cap (20) bounds a
  run.
- **Execution-based grader.** A deterministic checker over backend state. Never a
  model judge.
- **Cost-reliability (Pareto) frontier.** The trade-off of token cost versus
  success. A point is on the frontier if nothing is both cheaper and at least as
  reliable.
- **Paired per-task inference / bootstrap CI.** Comparing conditions
  task-by-task with resampled 95% confidence intervals.
- **Observation cost.** The tokens an observation adds to context per step
  (text-tokenized for C2/C3/C4; image-tiled for C1).
- **Oracle control.** A deterministic perfect-agent baseline that validates the
  measurement pipeline.
- **Surface-backend consistency invariant.** The tested guarantee that the
  view document never advertises an action the backend would reject.
- **Refusal task.** A task whose correct behavior is to decline. Reported
  separately from success tasks.

## 3. Related work

This section positions the study against five strands of prior work. The claims
below were checked against primary sources (papers and official documentation)
listed in the References. Where a source could not be confirmed we do not assert
a detail. The longer lab notebook, including the same table, is
[`research-plan.md`](research-plan.md) ("Novelty and positioning").

Prior work overwhelmingly asks *which agent or model is better* at operating a
computer, holding the interface's representation fixed as a property of the
benchmark. This study inverts that design: it holds the application, the task
set, the grader, and the model fixed, and treats the **interface representation
itself as the independent variable**.

**Reusing the human interface.** DOM and accessibility-tree agents (Mind2Web;
WebArena) operate the human page from HTML or an accessibility tree. The tree is
often so large that it must be filtered: Mind2Web's MindAct ranks DOM elements
with a small language model first. Screenshot and pixel computer-use systems
(Claude computer use; UI-TARS; SeeClick) perceive raw screenshots and emit
coordinates or other low-level actions. Grounding is the central difficulty, and
screenshots cost on the order of 1k to 2k tokens each in the accounts those
papers and docs report. These two families are our C2 and C1. They inherit a
representation designed for human perception. Our question is not how to
ground pixels better, but whether a non-pixel, agent-authored representation
is Pareto-superior for ordinary general models. Specialized pixel-native models
are deliberately deferred to a final check (`PROTOCOL.md`).

**Optimizing the human representation.** UIFormer ("From User Interface to Agent
Interface") and Prune4Web prune or restructure the human UI tree to cut tokens.
UIFormer reports that UI representation is 80 to 99 percent of agent token cost
and reports about 49 to 56 percent token reduction. This is the closest adjacent
line: it improves C2 rather than replacing it. It *compresses a human-derived
tree* and keeps that tree faithful to the human DOM. C4 is authored from backend
state, not derived from the human page, and we measure it as a controlled arm
rather than as a plug-in optimizer.

**Agent-facing protocols.** A2UI is a declarative JSON protocol in the opposite
direction: an agent generates UI for a human renderer. The Model Context
Protocol (MCP) standardizes tools, resources, and prompts (JSON-RPC, JSON
Schema tool inputs) for exposing capabilities to models. Our C4 is
application to agent, not agent to human (A2UI), and is richer than MCP's
tools and resources: it is a per-view state-plus-affordance document whose
`enabled` flags encode a priori action validity, matched in grain to a
flat-tools control (C3) so the added value of the document can be isolated. We
use C4 as a measurement probe, not a proposed standard. None of these protocols
is a de facto standard.

**Benchmarks.** WebArena, VisualWebArena, Mind2Web, WebShop, AndroidWorld, and
MiniWoB++ measure agent or model *capability* (task success, sometimes step or
element accuracy) via execution- or state-based grading, with the observation
modality fixed by the benchmark. We reuse the execution-grading idea but not
the goal. Our fixed variable is the model and our varied variable is the
interface. We additionally report a model-free, tokenizer-based observation-cost
baseline as a deterministic lower bound, which capability benchmarks do not
provide.

**Table R1.** How this study differs from each strand (verified sources only).

| Prior-work strand | Representative work | What it does | How this study differs |
| --- | --- | --- | --- |
| DOM / accessibility-tree web agents | Mind2Web; WebArena | Operate the human page from HTML or an accessibility tree; the tree is often filtered. | These are our C2. We treat that tree as one condition among four under a fixed model and grader. |
| Screenshot / pixel computer-use | Claude computer use; UI-TARS; SeeClick | Perceive screenshots and emit coordinates or low-level actions. | These are our C1. Specialized pixel-native models are deferred. The question is representation, not better grounding. |
| Optimizing the human tree | UIFormer; Prune4Web | Compress the human-derived DOM or accessibility tree. | Closest in spirit. C4 is authored from backend state, not derived from the human page. |
| Agent-UI protocols | A2UI; MCP | A2UI is agent to human. MCP is a capability catalog (close to C3). | C4 is application to agent, per-view, and constraint-carrying, matched to C3. Not a proposed standard. |
| GUI / web-agent benchmarks | WebArena; VisualWebArena; Mind2Web; WebShop; AndroidWorld; MiniWoB++ | Vary the agent, fix the interface, grade by execution. | We fix the agent and vary the interface, and add a model-free observation-cost baseline. |

**What this is not (limits of the novelty claim).** "Representation matters for
agents" is already known: Mind2Web filters the DOM because it is too large;
SeeClick is motivated by HTML being lengthy and occasionally inaccessible;
UIFormer measures UI representation at 80 to 99 percent of agent token cost. The
contribution here is the *controlled measurement* and the specific
agent-authored surface, not the observation that representation has an effect.
Execution-based grading is not new (WebArena, VisualWebArena, WebShop,
AndroidWorld). Token-efficient UI representation is not new (UIFormer,
Prune4Web). An agent-facing surface is already "in the air" (A2UI, MCP).
Constrained or valid-action masking is treated here as a known idea in
reinforcement learning and tool use; only the planned ablation that separates
it from compactness would be ours, and that ablation has not been run.
TODO (citation to find, not asserted): a verified primary source for action
masking or constrained decoding. No arXiv id is attached until one is checked.
Paper 2 (Agent Experience / AX) is largely synthesis: the individual metrics
already exist. Scope (one synthetic store, ten tasks, one general model, a
hand-authored C4) further bounds any novelty claim (Section 9).

## 4. Study design

**Application.** MiniShop is a small store with a catalogue, product pages, a
cart, and checkout. It is deliberately simple and its backend state is the single
source of truth for grading. The human HTML UI includes realistic chrome (promo
copy, search, decorative filters, related and help links) so that C1 and C2
observe a page built for people, not a stripped agent shell. Sold-out sizes are
visible but disabled on the human page, so a screenshot or tree agent can still
attempt them. The agent JSON API (`POST /agent/act`) is the only action channel
for C3 and C4. C1 and C2 drive the human pages with Playwright and must not call
that JSON API to act (`PROTOCOL.md`; `dualsurface/minishop/`).

**Identification.** The design is a controlled A/B/C/D of *representation*. If we
varied the application, the tasks, the grader, or the model at the same time as
the interface, we could not say the interface caused the difference. PROTOCOL.md
therefore holds the first group fixed and varies only the observation and
action channel.

**Table I1.** What is held fixed versus what is varied (pilot).

| Held fixed | Varied |
| --- | --- |
| Application: MiniShop (one backend, one grader) | How the agent *sees* the store (image, tree, tools, view document) |
| Task set (`tasks.json`, t01 to t10) | How the agent *acts* (pixel clicks vs named elements vs the shared C3/C4 action set) |
| Execution-based grader over the order record | Presence of the C4 view document (C4 vs C3 only) |
| One model per comparison; temperature 0; step cap 20 | |
| History: task text, prior actions, current observation | |

C1 and C2 reuse the human page, so their action vocabulary (coordinates, named
elements) cannot match C3/C4. That is a real confound when comparing human
surfaces to structured surfaces, and we state it as such. The comparison that
isolates the *document* is C3 versus C4.

**Why matched action grain between C3 and C4 matters.** C3 and C4 expose the
same operations (`open_product`, `set_size`, `add_to_cart`, `go_catalog`,
`go_checkout`, `set_address`, `pay`). C3 omits the view document; C4 adds it
(current-view identity, per-action `enabled` flags, argument JSON Schemas). If
C4 had a smaller or easier action set, a win for C4 could be "fewer buttons,"
not "a better representation." Matched grain blocks that alternative
explanation. What it does *not* yet separate is C4's two mechanisms,
compactness versus constraint-pruning. Those remain confounded until the
planned ablation (Section 6.5) is run. Models are never mixed across conditions
in one comparison (`PROTOCOL.md`).

**Conditions.** The same store is presented to the same model in four ways:

| ID | Condition | Observation | Actions |
| --- | --- | --- | --- |
| C1 | Screenshot | Rendered image of the human page | Click coordinates, type, scroll |
| C2 | Accessibility / DOM | Text tree of the human page | Click/fill named elements |
| C3 | Flat tools | Function catalog only; no current-view document | Call those functions |
| C4 | View document | JSON: view, state, entities, affordances | Invoke an enabled affordance with typed arguments |

**Tasks and grader.** Ten frozen tasks in
`dualsurface/minishop/data/tasks.json` (seven expected to succeed, three
expected to be refused) are graded by a deterministic, execution-based checker
over the backend order record, never by another model. Temperature is zero, the
step cap is twenty, and the agent's history is limited to the task, its prior
actions, and the current observation. Success tasks require a matching product,
size, and shipping address. Refusal tasks require that a forbidden order is *not*
placed: t03 (Harbor Blue Tee size M, sold out), t05 (pay on an empty cart), t07
(Signal Cap size S, sold out). A do-nothing agent can pass a refusal task by
inaction, so refusal outcomes are reported separately from success tasks and
must not inflate the headline success rate.

**Table T1.** Frozen MiniShop task set.

| ID | Expect | Instruction (abridged) |
| --- | --- | --- |
| t01 | success | Navy Crew Tee, size M, to 18 Cedar Ave, Portland |
| t02 | success | Harbor Blue Tee, size L, to 18 Cedar Ave, Portland |
| t03 | refusal | Harbor Blue Tee, size M (sold out) |
| t04 | success | Studio Mug, to 9 Pine Street, Austin |
| t05 | refusal | Pay with an empty cart |
| t06 | success | Ash Hoodie, size S, to 4 Market Road, Seattle |
| t07 | refusal | Signal Cap, size S (sold out) |
| t08 | success | Field Notebook, to 100 King St, Boston |
| t09 | success | Day Bottle and Crew Socks, to 18 Cedar Ave, Portland |
| t10 | success | Navy Crew Tee, size L, to 77 Oak Lane, Denver |

**The C4 view document.** PROTOCOL.md requires `view`, `state`, `entities`, and
`affordances[]` with `id`, `enabled`, and `input` JSON Schema. No layout or
Markdown projection in the pilot. The document is a hand-written function of
backend state (`minishop/surface.py::build_surface`), which makes it an *upper
bound* on how good an agent surface can be: it is faithful by construction.
Affordances include `open_product` (product id enum), `set_size` (in-stock size
enum, enabled only on the product view), `add_to_cart` (enabled only when a
valid size is selected on a product view), `go_catalog`, `go_checkout`,
`set_address` (enabled only on checkout), and `pay` (enabled only on checkout
with a non-empty cart and a non-empty address). A consistency invariant,
enforced by tests (`tests/test_surface_consistency.py`), guarantees that the
document never advertises an action the backend would reject and that its size
enumerations match stock exactly, so a favorable C4 result cannot be an
artifact of a surface that disagrees with the application. The t10 regression
pins this invariant at the exact state where `set_address` is disabled on the
product view and the backend rejects it.

## 5. Metrics and analysis

**Dependent variables.** Per run: task success (binary; for refusal tasks,
correctly declining); input and output tokens summed over steps (including image
tokens on the screenshot (C1) where the provider itemizes them); step count;
illegal actions (backend rejections); and a `malformed_actions` count
(responses that are not a usable action), tracked separately so that model
formatting failures are not silently absorbed.

**Token accounting.** Total input tokens decompose per step into a roughly
constant overhead (system prompt, task, prior actions) plus the current
observation, whose size varies by condition:

```
input_tokens(run) ≈ sum over steps of
    [ (system + task + prior actions)   # fixed overhead
      + current_observation ]           # varies by condition
```

Total cost is therefore approximately the per-step observation cost times the
number of steps, which makes explicit that a representation can win either by
being lighter per step or by needing fewer steps. Below we make precise how the
observation term is counted for each condition, because the *text* conditions
and the *spatial* (image) condition are counted in fundamentally different ways.

*Text conditions (C2, C3, C4), tokenizer-based.* The observation is serialized
text (an accessibility tree, a tool-result status object, or a JSON view
document), so its token count is exactly the length of that serialized content
under the model's tokenizer (we use `o200k_base` for the deterministic
baseline). Cost therefore scales with *how much content the representation
serializes*. The per-step decomposition is the same fixed overhead as above plus
the condition-specific part: **flat tools (C3) additionally pays the full tool
schema on every call** (the harness sends the function definitions with each
request), and **the view document (C4) pays for that document** (view, state,
entities, and per-affordance `enabled` flags and argument schemas). The
accessibility tree (C2) pays for the verbose human tree. Reconstructing the
canonical path deterministically, the median per-step input splits
(`o200k_base`) are:

| condition | system | task+prior | tool schema | observation | per-step total |
| --- | --- | --- | --- | --- | --- |
| C1 (screenshot, est.) | 186 | 62 | n/a | 1105 (image) | 1353 |
| C2 (a11y tree, measured) | 188 | 62 | n/a | ~650 (tree) | ~900 |
| C3 (flat tools) | 159 | 62 | 490 | 25 | 736 |
| C4 (view document) | 188 | 62 | n/a | 422 | 672 |

The C3 row shows the tool schema (490 tokens) dwarfing its tiny status
observation (25 tokens); the C4 row shows the document (422 tokens) as its whole
condition-specific cost. C2's tree is *measured* from run traces because it
requires a live browser to render; the other three are reconstructed
deterministically with no model call.

*Spatial/image condition (C1), tiling-based, not tokenizer-based.* A screenshot
is not tokenized as text. Vision models charge image tokens by a **tiling**
model that is a function of the image's *resolution*, not its content. For the
OpenAI gpt-4o family the rule is: downscale the image to fit within a
2048×2048 box, then scale its shortest side to ~768px, then cover the result in
512×512 tiles, and charge

```
image_tokens ≈ base + per_tile × tiles
```

with high-detail `base = 85` and `per_tile = 170` (low detail is a flat 85
regardless of resolution). Two implications are central to this study:

1. **Image-token cost is a function of resolution/viewport, not of visual
   complexity or information content.** A blank page and a busy page rendered
   at the same viewport produce the identical tile count and therefore the
   identical cost. A screenshot cannot get *cheaper* by showing less, only by
   being sent at a lower resolution or in low detail, which is the opposite of
   the text conditions, where a leaner representation is directly cheaper.
   Because of the 768px shortest-side rescale, high-detail cost also
   **plateaus**: at our 1280×800 viewport it is 6 tiles (about 1105 tokens),
   and wider 16:9 viewports (1536×864, 1920×1080) still cost 6 tiles.

2. **Provider reporting differs, so C1's cost must be read from total input
   tokens.** OpenAI *itemizes* image tokens in a dedicated usage field, whereas
   Vertex/Gemini *folds* them into `prompt_tokens`. This is why our observed
   `gemini-2.5-flash` C1 runs report `image_tokens = 0` yet an input of ~46k
   tokens per task: the image is fully billed, just not itemized. The harness
   reads a dedicated `image_tokens` field when present and otherwise leaves it
   null (`harness/openai_compat.py::extract_usage`); comparisons anchor on total
   input tokens and treat the itemized image count as secondary.

These tiling constants are **provider- and model-specific** (Anthropic and
Google use different resolution rules and per-tile costs), so we present the
gpt-4o numbers as a concrete, labeled estimate and do not claim a single
universal image-token formula. `harness/obs_cost.py` computes the estimate
across a resolution sweep and the per-condition composition above
deterministically; `harness/make_figures.py` renders them as
`image_tokens_vs_resolution.png` (the resolution curve) and
`token_composition_by_condition.png` (the stacked composition).

**Analysis.** We report a per-`(model, condition)` table and a cost-reliability
Pareto frontier (median input tokens vs success rate). Because the same tasks
run under every condition, we compute **paired per-task** differences between
C4 and C3 with bootstrap 95% confidence intervals resampled over tasks,
reporting success and refusal tasks separately.

**Latency.** *(forthcoming)* Latency is a planned metric and is not yet
instrumented. It is expected to weight *round trips* (step count) differently
from token cost, and could therefore move the C3-versus-C4 comparison; we will
add per-call timing and report median time-to-completion per condition.

### Procedures

This subsection states the exact, repeatable procedures behind the numbers. It
does not re-derive the study design (Section 4) or the token accounting above; it
records *how a run executes, how each metric is computed, how the data is
analyzed, and how to reproduce all of it.*

**Experimental procedure (one run).** A "run" is one (condition, task, repeat)
triple. The harness holds everything in Section 4 fixed (the MiniShop backend
and its execution grader, the ten-task set (seven success, three refusal),
temperature 0, a step cap of 20, and a history limited to the task text, the
prior actions, and the current observation) and varies only the representation
across the four conditions screenshot (C1), accessibility tree (C2), flat
tools (C3), and view document (C4). Within a run the agent loops: observe the
current representation, emit one action, apply it against the backend, and
observe again, until the task completes or the step cap is reached. A full
sweep is the Cartesian product 4 conditions × 10 tasks × R repeats (here
R = 5, so 200 runs); each condition is launched as its own repeats invocation so
a crash in one condition cannot abort the others. A deterministic **oracle**
agent that replays the correct policy is run first as a control and end-to-end
pipeline check (it reaches 100% on C3 and C4), separating apparatus correctness
from model behavior. Every run is written to its own JSONL trace file (a run
header, one row per step with the action and provider usage, and a final result
row with the per-run rollups), so runs are independent artifacts that the
analysis layer reads after the fact.

**Measurement procedure (per metric).** *Success* is the deterministic grader's
verdict over the backend order record: for success tasks the order must match
the task specification; for refusal tasks no forbidden order may be placed.
The grader is never another model. *Input and output tokens* are the provider's
reported usage summed over the run's steps; for the screenshot (C1), image
tokens are read from total input tokens because Vertex folds them into
`prompt_tokens` (Section 5). The per-condition observation cost is counted two
different ways, as Section 5 specifies: the text conditions (C2, C3, C4) are
counted by tokenizer on the serialized observation, while the screenshot (C1) is
counted by the resolution-driven image-tiling model. *Steps* is the number of
model calls until success or the cap. *Illegal actions* are backend
rejections; *malformed actions* are non-object model responses (a JSON array or
prose) that are not a usable action. The two error signals are counted separately
(a malformed response is recorded as such rather than silently coerced to a
no-op) so that a model's formatting failures are never absorbed into its
illegal-action rate.

**Analysis procedure.** The analysis layer reads the final result row of every
trace and collapses runs into per-`(model, condition)` cells, never pooling
across models. For each cell it reports the success rate, median steps, median
input/output/image tokens, and the illegal- and malformed-action rates per step.
Uncertainty is a percentile bootstrap: the success rate and the median input
tokens carry 95% CIs resampled (fixed seed) over the cell's task-repeat units.
The cost-reliability frontier marks each cell as on- or off-frontier (a cell
is dominated if another is no more costly and at least as reliable). Because the
same tasks run under every condition, the C4-versus-C3 comparison is **paired per
task**: average each task's outcome over its repeats under each condition, take
the C4 minus C3 difference, and bootstrap a 95% CI over tasks, reported
separately for success and refusal tasks so a refusal passed by inaction cannot
inflate the headline.

**Reproducibility checklist.** Every number above is regenerated from the
repository with no hidden state, in this order:

1. `python -m harness.scripted`: the non-model sanity check. A scripted policy
   must complete every success task on C3 and C4 and be refused on the refusal
   tasks before any model is run.
2. `python -m harness.obs_cost`: the model-free observation-cost baseline and the
   per-condition token composition (Section 6.1), `o200k_base` tokenizer, no API
   call.
3. `python -m harness.model_loop --oracle --conditions C3,C4`: the deterministic
   pipeline control (Section 6.2).
4. `python -m harness.model_loop --repeats 5` (per condition): the model sweep
   that writes the 200 per-run traces (Section 6.3).
5. `python -m harness.report --figures`: aggregates the traces into the tables,
   bootstrap CIs, the paired comparison, and the Pareto/paired figures.
6. `python papers/agent-native-ui/build.py`: renders this manuscript (`paper.md`
   to `paper.html`/`paper.pdf`).

The environment (Python dependencies, the Playwright Chromium used for the C1/C2
browser render and for `papers/agent-native-ui/build.py`, and the model registry
in `harness/models.py`) is pinned under `.cursor/`, so the sequence above runs
identically on a fresh checkout.

## 6. Results

We report the results in three layers, from the model-free lower bound to the
model run itself. Section 6.1 is a deterministic observation-cost baseline that
needs no model. Section 6.2 is the oracle control that validates the pipeline.
Section 6.3 is the first model run (`gemini-2.5-flash`, N=5), read one metric
at a time (success, token cost, steps, illegal/malformed actions), then broken
out per task, then analyzed as a paired C4-versus-C3 comparison, and finally
summarized as a per-condition error analysis. Everything here is one model on
one synthetic application with ten tasks, so we read the coarse orderings and
treat the fine C3-versus-C4 margin as provisional.

### 6.1 A model-free observation-cost baseline

Before any model is run, we measure deterministically how many tokens each
condition's observation costs per step, replaying each task's canonical path
and counting tokens with a fixed tokenizer. Median per-step observation cost is
approximately 1105 tokens for the screenshot (C1) estimate, 512 for flat tools
(C3) (which re-sends the tool schema each step), and 453 for the view document
(C4). Text representations are thus about 2.4 times cheaper per look than a
screenshot, and the view document is slightly cheaper per step than the flat
tool catalog. This is the observation term only, along the minimal path. It does
not include step-count effects, which the model run adds.

### 6.2 Pipeline control (oracle)

A deterministic "oracle" agent that replays the correct policy validates the full
measurement pipeline end to end and provides a best-case reference: both flat
tools (C3) and the view document (C4) reach 100% success. This isolates apparatus
correctness from model behavior, so any success deficit in the model run below is
attributable to the model, not to the harness or grader. Two honesty caveats on
oracle *tokens*: they are locally tokenized (`o200k_base`, tagged
`"source": "local_tokenizer"`), not provider-billed; and C3's billed tool schema
is omitted from the oracle input count because the loop sends schemas via the
`tools` argument. `harness/obs_cost.py` is where that schema is counted. C1 and
C2 are out of scope for the oracle (they need pixel or element oracles).

### 6.3 First model run: `gemini-2.5-flash` (N = 5)

We run one general model, `gemini-2.5-flash` (via Vertex, temperature 0, step cap
20), across all four conditions on all ten tasks, five times each (200 runs in
total). Table 1 reports the per-condition aggregate. The subsections that follow
read it one metric at a time.

**Figures (paths, not new numbers).** The human pages C1 and C2 observe are
`docs/minishop/catalog.png`, `docs/minishop/product-blue-soldout-m.png`,
`docs/minishop/checkout.png`, and `docs/minishop/confirmation.png`. Cost-reliability
and paired C4-versus-C3 plots are produced by `python -m harness.report --figures`
into `dualsurface/minishop/report/` (gitignored), including
`gemini_repeats_pareto.png` and `gemini_c3_c4_paired.png` when those traces are
present. Token-accounting figures from `harness/make_figures.py` are
`image_tokens_vs_resolution.png` and `token_composition_by_condition.png`.
None of these files is a second measurement. They render Section 6.1 and
Table 1.

**Table 1.** Per-condition results, `gemini-2.5-flash`, N=5 (95% CIs
bootstrapped over the 50 task-repeat units per cell).

| Condition | Success (95% CI) | Median input tokens (95% CI) | Median steps | Illegal/step | Malformed/step |
| --- | --- | --- | --- | --- | --- |
| screenshot (C1) | 30% [18, 42] | ~46,338 [46,324, 46,368] | 20 | 0.000 | 0.000 |
| accessibility tree (C2) | 72% [60, 84] | ~6,770 [5,835, 9,714] | 7 | 0.198 | 0.116 |
| flat tools (C3) | 100% [100, 100] | ~3,134 [3,118, 3,154] | 7 | 0.000 | 0.000 |
| view document (C4) | 92% [84, 98] | ~4,455 [4,413, 4,491] | 6 | 0.016 | 0.000 |

This is one cell in a planned model × application grid: one general model, one
synthetic store. Coarse orderings (C1 dominated; C2 noisy; C3 and C4 both
clear the human surface) are the robust reading. The fine C3-versus-C4 margin
is provisional (Section 7).

**Run-level spend (same sweep, not a new run).** Across 200 runs the traces sum
to about 2.82M input tokens and 35k output tokens, about $0.93 at the
gemini-2.5-flash rates recorded in the research plan ($0.30 per 1M input,
$2.50 per 1M output). By condition: C1 2.11M in / 19.9k out; C2 385k / 9.4k;
C3 138k / 1.7k; C4 193k / 4.1k. C1 alone is about 73% of the bill. Screenshots
remain the dominant cost even before asking whether they succeed.

#### Success

The two human-surface conditions are clearly dominated on success. The screenshot
(C1) passes only 30% of runs [18, 42] and none of the seven success tasks (its
passes are all refusal tasks). The accessibility tree (C2) reaches 72% [60, 84]
but is the least trustworthy number in the table, because its failures mix
backend rejections and malformed responses (below). The two structured
conditions clear the human surface comfortably: flat tools (C3) is perfect
(100% [100, 100]) and the view document (C4) is near-perfect (92% [84, 98]), its
only deficit isolated to task t10 (analyzed below). Read cautiously: with five
repeats over ten tasks these intervals are wide, and the C3-over-C4 success gap
is a single task.

#### Token cost

Input-token cost separates the conditions by an order of magnitude, and the
mechanism is the per-step observation decomposition of Section 5 (per-step
observation cost times steps plus fixed overhead). We do not repeat that
accounting here. The screenshot (C1) is by far the most expensive at a median
~46,338 input tokens per task, roughly 10 times the view document (C4) and about
15 times flat tools (C3); C1 also accounts for most of the run's billed tokens.
Because Vertex folds image tokens into `prompt_tokens`, that cost is read from
total input tokens, not from the itemized `image_tokens` field (which reads 0).
Among the text conditions, flat tools (C3) is cheapest (~3,134), the view
document (C4) is next (~4,455), and the accessibility tree (C2) is most expensive
and most variable (~6,770 [5,835, 9,714]) because tree size tracks page content.
Notably, the model-run ordering of C3 below C4 *reverses* the minimal-path
baseline of Section 6.1 (where C4 was cheaper per step): once real step counts are
in play, the C4 document grows as the cart fills, so its mid-session documents
outweigh C3's compact status objects.

#### Steps

Step count is where the view document (C4) helps. C4 uses the fewest median
steps (6) and flat tools (C3) one more (7); paired per-task analysis (below)
confirms the −1.17-step difference is significant. The screenshot (C1) sits at
the step cap (median 20) because it never completes a success task and simply
exhausts the budget. The accessibility tree (C2) has a median of 7 but a long
tail: it too hits the cap on the multi-item task t09.

#### Illegal and malformed actions

We track two distinct error signals: illegal actions (the backend rejects an
attempted action) and malformed actions (the model emits a non-object response,
a JSON array or prose, that is not a usable action). The screenshot (C1) and
flat tools (C3) are clean on both (0.000 each). The view document (C4) has a
small illegal rate (0.016/step), concentrated entirely on t10. The accessibility
tree (C2) is the outlier on both axes (0.198 illegal/step and 0.116
malformed/step), so its 72% success masks a genuinely noisy interaction: the
human tree invites named clicks and fills on elements the backend then rejects,
and the model periodically returns responses the loop cannot parse. Keeping the
malformed count separate (rather than silently coercing it to a no-op) is
what makes C2's error composition honest.

C1's illegal rate of 0.000 is not evidence that screenshots stay inside valid
actions. A raw coordinate click rarely trips the backend's `illegal` flag, so
C1's failure mode is in success, steps, and tokens (step-capped on every
success task), not in that flag. C4's 0.016 illegal/step is the opposite
signal: the backend *did* reject an action the document had already marked
`enabled: false` (t10, below).

#### Per-task breakdown

Table 2 breaks the run down per task so the patterns behind the aggregates are
visible. Each cell packs the three per-task medians for that condition:
**success rate · median steps · median input tokens**, computed over the five
repeats (refusal tasks are marked *r*).

**Table 2.** Per-task readout, `gemini-2.5-flash`, N=5. Cell = success rate ·
median steps · median input tokens.

| Task | | screenshot (C1) | accessibility tree (C2) | flat tools (C3) | view document (C4) |
| --- | --- | --- | --- | --- | --- |
| t01 | | 0% · 20 · 46,368 | 20% · 12 · 11,702 | 100% · 7 · 3,154 | 100% · 6 · 4,498 |
| t02 | | 0% · 20 · 46,368 | 100% · 11 · 10,809 | 100% · 7 · 3,154 | 100% · 6 · 4,486 |
| t03 | *r* | 100% · 2 · 4,184 | 100% · 2 · 1,997 | 100% · 2 · 1,081 | 100% · 2 · 1,597 |
| t04 | | 0% · 20 · 46,268 | 0% · 6 · 5,835 | 100% · 7 · 3,118 | 100% · 6 · 4,423 |
| t05 | *r* | 100% · 20 · 46,018 | 100% · 3 · 2,605 | 100% · 2 · 713 | 100% · 2 · 1,528 |
| t06 | | 0% · 20 · 46,328 | 100% · 10 · 9,714 | 100% · 7 · 3,144 | 100% · 6 · 4,491 |
| t07 | *r* | 100% · 20 · 46,348 | 100% · 2 · 1,990 | 100% · 2 · 1,079 | 100% · 1 · 905 |
| t08 | | 0% · 20 · 46,324 | 100% · 7 · 6,690 | 100% · 7 · 3,124 | 100% · 6 · 4,413 |
| t09 | | 0% · 20 · 46,428 | 0% · 20 · 21,658 | 100% · 12 · 5,833 | 100% · 10 · 7,867 |
| t10 | | 0% · 20 · 46,368 | 100% · 7 · 6,770 | 100% · 7 · 3,154 | 20% · 6 · 4,544 |

Four patterns stand out. **The screenshot (C1) hits the step cap (20) on every
task it does not refuse** and fails all seven success tasks; its only passes are
the refusal tasks (t03 by an early refusal, t05 and t07 by exhausting the
budget without placing the forbidden order), and its cost is a nearly flat
~46k tokens because image cost is set by viewport, not content. **The
accessibility tree (C2) is erratic**: it fails t01 (20%), t04 (0%), and the
two-item t09 (0%, step-capped at 20 with the heaviest token load of any
text-condition cell, ~21.7k). **Flat tools (C3) is uniformly clean** (100% on
every task at ~3k tokens and ~7 steps). **The view document (C4)'s deficit is
isolated to t10** (20%); on every other task it matches C3's success while using
one fewer step (6 vs 7, and 10 vs 12 on t09) and consistently more input tokens.

#### Paired C4-versus-C3 analysis

Because the same tasks run under every condition, we compare the view document
(C4) against flat tools (C3) paired per task: for each task we average the outcome
over its five repeats, take the C4 minus C3 difference, and bootstrap a 95% CI
over tasks (fixed seed), reporting the seven success tasks and three refusal
tasks separately. Table 3 gives all three metrics.

**Table 3.** Paired C4 minus C3 per-task differences, `gemini-2.5-flash`.
Positive means C4 is higher.

| Task set | n | Metric | Mean diff (C4 − C3) | 95% CI | Excludes 0? |
| --- | --- | --- | --- | --- | --- |
| success | 7 | success | −0.114 | [−0.343, 0.000] | no |
| success | 7 | input tokens | +1,404 | [+1,317, +1,549] | **yes** |
| success | 7 | steps | −1.17 | [−1.51, −1.00] | **yes** |
| refusal | 3 | success | 0.000 | [0.000, 0.000] | no |
| refusal | 3 | input tokens | +386 | [−174, +815] | no |
| refusal | 3 | steps | −0.33 | [−1.00, 0.00] | no |

On the success tasks the view document **significantly reduces steps** (−1.17
per task; CI excludes zero, which is the point of a current-view/affordance
document) but **significantly increases input tokens** (+1,404 per task; CI
excludes zero, and every one of the seven success tasks is positive) and does
**not** significantly change success (the CI [−0.343, 0.000] includes zero; the
entire point estimate is the t10 deficit). On the axes we measured, flat tools
(C3) is therefore Pareto-preferred here (cheaper and at least as reliable), so
H2's specific claim that C4 dominates is not supported for this model and
application. On the refusal tasks nothing separates the two conditions: both
refuse correctly on all three, and the token and step differences are small with
CIs that include zero. C4 keeps the fewest steps throughout, but on this small
application that step saving does not offset its per-step token cost.

**Pareto reading of this cell.** A point is dominated if another point is no
more costly and at least as reliable. C3 is cheaper than C4 (input-token CI on
the paired difference excludes zero) and at least as reliable (success CI
includes zero, point estimate favors C3). C1 and C2 sit below and to the right
of the C3/C4 cluster: more expensive, less reliable. H2's claim that C4 dominates
is not supported in this cell. The open question is whether later cells (another
model, an ablation, latency, a harder app) move C4 onto the frontier.

#### What the t10 failure means, plainly

Task t10 asks the agent to buy an item and ship it to an address. The valid
order of operations is: open the product, add it to the cart, go to checkout,
and *then* enter the shipping address. An address cannot be entered before
checkout is reached. On this task the model tried to enter the address too
early, while still on the product page. Because setting an address is only valid
at checkout, the view document (C4) had explicitly labeled that action unavailable
(`enabled: false`) at that step, and the backend refused it. The key point is
what kind of failure this is. It is not a bug in the interface: the document
was correct and agreed with the backend (an invariant we enforce with a test).
It is the model choosing to ignore a rule the interface clearly stated. This is
central to the idea of the view document (C4): its value is that it tells the
agent what is allowed right now, so a model that reads and respects those labels
avoids the mistake, while a model that ignores them (as this one did) gains
nothing from the extra information. It also gives a concrete quantity to measure
across models: how often a model attempts an action the interface marked
unavailable (an "ignored-affordance" rate). The failure is reproducible: C4 fails
t10 on four of five repeats in the main sweep (all via the identical early
`set_address`), and a diagnostic t10-only re-run reproduced it on five of five.

### 6.4 Second model (RQ3). *(forthcoming)*

Whether "flat tools (C3) is Pareto-preferred" generalizes beyond one model is
open. A second general model (for example a mid-tier Claude or Grok) will test
in particular whether other models obey the `enabled` flag on the t10 path,
that is, whether the ignored-affordance rate above is a property of this model
or of the task.

### 6.5 Constraint-pruning ablation. *(forthcoming)*

To explain the view document (C4)'s token overhead and separate *compactness*
from *constraint-carrying*, we will strip the `enabled` flags and argument
enumerations from the C4 document (retaining view and entities) and measure
whether the step savings survive without the constraint information.

## 7. Discussion

This section separates what the *present cell* implies from what *later cells*
must show before H2 or H3 can be claimed.

### 7.1 What this cell shows

The cell is `gemini-2.5-flash` × MiniShop, N=5, ten tasks. On that cell:

- **RQ1 is supported at a coarse grain.** Representation changes success,
  tokens, steps, and illegal or malformed rates. C1 is about 10 times C4 and
  about 15 times C3 in median input tokens, succeeds 30% [18, 42], and hits the
  step cap on every success task. C2 is 72% [60, 84] with the highest illegal
  and malformed rates. C3 and C4 both clear the human surface.
- **RQ2, C1 and C2.** The human-surface conditions are dominated by the
  structured conditions on this cell. That part of H2 holds here.
- **RQ2, C4 versus C3.** H2's specific claim that C4 dominates is *not* supported.
  C3 is Pareto-preferred on tokens and success. C4's documented mechanism
  (fewer steps, −1.17 per success task, CI excludes 0) is present and not large
  enough to offset +1,404 input tokens per success task.
- **t10 is model behavior.** The C4 document advertised `set_address` as
  `enabled: false` on the product view; the backend rejected the same call; a
  test pins the agreement. The model ignored the flag on 4 of 5 main-sweep
  repeats and 5 of 5 diagnostic repeats. A surface that is truthful does not
  help a model that does not read `enabled`.

The provisional headline (C3 preferred to C4 on tokens and success) is the
*least favorable* setting for a purpose-built surface: tiny state, short tasks,
and a model that ignores constraints. C3's memory burden is light. C4 still
pays to send a growing document.

### 7.2 What later cells must show

These are predictions, not results. No number below is measured yet.

1. **Second general model, N=5 (RQ3 / H3).** If another general model *obeys*
   `enabled: false` on t10, C4's success should rise toward C3's on this app,
   and the ignored-affordance rate should fall. If it still misses the flag,
   the t10 failure is not unique to `gemini-2.5-flash`. Either outcome is
   informative. The cell must still be reported as model × condition, never
   pooled. If the model lacks vision, drop C1 and state that limit
   (`PROTOCOL.md`).
2. **C4 ablation.** Strip `enabled` flags and argument enums, keep view and
   entities. If C4 remains more expensive than C3, the token overhead is
   document growth (compactness), not the constraint payload. If step savings
   disappear, the step win was constraint-carrying. Until this run exists,
   compactness and constraints stay confounded.
3. **Latency.** Token Pareto can disagree with time Pareto. C4 uses fewer
   round trips. A timed re-run could move the C3-versus-C4 verdict without
   changing Table 1's token ranks.
4. **A second, more complex application.** MiniShop is C4's least favorable
   case. A store with more views, more state, and more ways to act illegally
   is where C3's runtime tracking tax is hypothesized to grow. Without that
   cell, "C3 wins on simple apps" must not be read as "do not ship C4."

We therefore treat C4's fewer steps and near-zero illegal-action rate as
*mechanism present, not yet decisive* on cost. The crossover is expected where
models respect constraints, where round trips are priced, or where the
application is no longer tiny. That is a hypothesis for later cells, not a
finding of this one.

## 8. Adopting the view document (C4): paths and complexity for existing and future applications

The study measures a hand-authored view document (C4) as an upper bound, which
naturally raises the practical question of what it would take for a real
application to expose such a surface. This section addresses that question
directly. It is not an evaluation (the numbers in Section 6 speak only to the
hand-authored case) but a structured account of the adoption paths available
and their relative complexity, so that a reader can judge where the trade-off in
Section 7 (a per-step token cost now versus a perpetual runtime state-tracking
tax) is likely to be worth paying.

**Core principle: a faithful projection, not new business logic.** The view
document (C4) is a *faithful projection of backend state*. The backend remains
the single source of truth, and the document is a re-serialization of what the
backend already knows: which view the agent is on, the entities in it, and the
actions that are valid right now with their argument constraints. The
surface-versus-backend consistency invariant we enforce with tests (Section 4)
is the formal statement of this: the document may never advertise an action the
backend would reject. The consequence for adoption is the central, and
encouraging, observation of this section: **almost all of the information a C4
document carries is validity logic the application already has.** A human
interface already disables the "Add to cart" button until a size is chosen,
already validates the address field, already hides the "Pay" button until the
cart is non-empty and the address is set. Those enable-conditions, form
validations, and in-stock checks are the same predicates a C4 document serializes
into its `enabled` flags and argument schemas. Adoption is therefore largely a
*serialization* problem (expose logic that already exists in a
machine-readable shape) rather than a request to author new business rules.
This reframing is what makes the paths below tractable.

### 8.1 A spectrum of adoption paths

Applications can produce a C4 surface in several ways, which differ sharply in
who pays the authoring cost, how much of the application they cover, and how
faithful the result is. We describe five, from the highest-leverage (available
to applications built with agent surfaces in mind) to the most general
(available to any application, at a cost). Each carries an explicit complexity
rating on three axes: *effort* (what a developer must do), *coverage* (how much
of a real application it reaches), and *fidelity* (how faithfully the surface
tracks backend truth).

**1. Framework-emitted (future applications).** A UI framework in which the
developer declares views, state, and actions once, and the framework emits
*both* the human render and the view document (C4) from that single
declaration. Because the enable-conditions and validation are already written
for the human UI, the framework can project them into the agent document with no
additional developer work per view. *Effort: low at the margin (a one-time
framework investment, then near-zero per application). Coverage: high.
Fidelity: high (the two surfaces are generated from one declaration, so they
cannot drift).* This is the highest-leverage path but presupposes framework
support that does not yet exist widely.

**2. Derived from a structured backend.** Many applications already hold their
capabilities in machine-readable specifications: a GraphQL schema, form and
validation schemas, or a server-driven UI description. Where such a spec exists,
C4 can be *projected* from it: the types become entities, the mutations become
affordances, the validation rules become argument constraints and `enabled`
flags. *Effort: low to medium (write and maintain the projection; reuse existing
specs). Coverage: medium to high, bounded by how much of the app is actually
spec-driven. Fidelity: high where the spec is authoritative, lower where the UI
adds validity logic the spec does not capture.*

**3. Hand-authored per view (what this study does).** A developer writes the
view document by hand for each view, as a function of backend state. This is
faithful by construction and is exactly the arm we measure, but it does not
scale: every view is bespoke work, so it suits a small number of high-value
applications or flows rather than a whole ecosystem. The pilot gives a concrete
data point for the per-view cost. In MiniShop, the C4 projection
(`minishop/surface.py`, `build_surface`, about 140 lines) is roughly 3 to 4 times
the size of the flat-tools (C3) definition (`minishop/tools.py`, about 40
lines). That multiple is the honest cost of the document, but it is
*mirroring* logic the human templates already encode (the same size/stock and
view checks that gate the human buttons), not inventing new rules, which is why
even the hand-authored path is closer to transcription than to design. *Effort:
medium per application. Coverage: whatever is authored. Fidelity: high
(authored directly against backend state and pinned by the consistency
test).*

**4. Compiled from the human surface (existing and legacy applications).** For an
application that already ships a human UI and cannot be rebuilt, a compiler can
read the rendered surface (the DOM, ARIA roles, and `disabled` attributes) and
emit a view document from it. The attractive property is that it costs the
application *nothing*: no new endpoint, no re-declaration, no backend change.
The cost is fidelity. A compiled surface inherits whatever the human page
happens to expose, so it can be *lossy* (state the DOM does not render is
invisible to it) and it can *disagree* with the backend (a button enabled in the
DOM that the backend would nonetheless reject). A compiled document must
therefore be validated against the backend before it is trusted, exactly as our
consistency invariant validates the hand-authored one. *Effort: near-zero for
the application (the work is in the compiler). Coverage: broad (it applies to any
app with a human UI). Fidelity: lossy, and must be checked.*

**5. Model-extracted (a model reads the screen).** The most general path: an LLM
observes the human surface (a screenshot or the accessibility tree) and *emits*
the view document itself. It applies to any application with no cooperation
whatsoever, which is its whole appeal. But it inverts the economics of C4. The
document's purpose is to pay *once* so the agent does not re-derive state at
runtime; extracting it with a model moves that cost back to runtime and pays it
on every step, and it reintroduces exactly the hallucination risk (an advertised
action the backend rejects) that a faithful projection removes. It is best
understood as a fallback for surfaces reachable no other way. *Effort:
near-zero for the application. Coverage: universal. Fidelity: lowest, subject to
model error, and cost recurs at runtime.*

### 8.2 Cost framing: build-time versus runtime

The five paths above trade a single quantity against another. The view document
(C4) pays its cost *once*, at build or framework time (paths 1 to 3) or at
compile time (path 4); thereafter every agent interaction reads a surface that
already states what is true and what is allowed. Flat tools (C3), by contrast,
pays a *perpetual runtime tax*: because it ships no current-view document, the
model must re-derive the application's state from its own history on every step,
for the life of the deployment. Adoption effort is thus a one-time (or
amortized) investment weighed against a recurring per-interaction cost. Two
things move that balance toward adoption. First, scale: a framework- or
spec-derived surface amortizes its cost across every application and every run, so
the per-interaction saving compounds. Second, complexity: the runtime
state-tracking tax that C3 imposes grows with the number of views, the amount of
state, and the number of ways an action can be invalid, which is precisely the
regime (Section 7) where we expect C4's advantage to emerge. On the simple
application measured here the tax is small, which is why C3 is competitive;
the trade is expected to improve for C4 as applications grow more complex.

### 8.3 A procedure for adding C4 to an existing application

For a developer adding a view document to an application today (the
hand-authored or spec-derived paths), the work reduces to a short, repeatable
procedure:

1. **Enumerate the views.** List the distinct states the UI can be in (catalog,
   product, cart, checkout, confirmation, and so on), the same screens the
   human UI already has.
2. **For each view, expose three things:** the current *state* (the fields the
   view depends on), the relevant *entities* (the objects shown), and the
   available *actions*, each with its *enable-condition* and *argument
   constraints*. Crucially, reuse the human UI's existing disable and validation
   logic here: the predicate that greys out a button is the predicate that sets
   `enabled: false`, and the form validator that rejects an input is the argument
   schema.
3. **Serve the document** at an endpoint or resource (for instance as an MCP
   resource) so an agent can read the current view on each step.
4. **Keep the backend as the enforcing source of truth.** The document
   advertises validity; the backend still checks it. The surface is a
   projection, never the authority.
5. **Add a surface-versus-backend consistency check** (as in Section 4) so the
   document can never advertise an action the backend would reject. This is the
   test that makes the projection trustworthy and prevents the two surfaces from
   drifting apart over time.

### 8.4 Complexity summary

Table 4 summarizes the five paths on the three axes above and states when each is
appropriate.

**Table 4.** Adoption paths for the view document (C4).

| Adoption path | App effort | Coverage | Fidelity | When to use |
| --- | --- | --- | --- | --- |
| Framework-emitted | Low at scale (one-time framework cost) | High | High (single declaration, no drift) | New applications; ecosystems adopting an agent-aware UI framework |
| Derived from a structured backend | Low to medium (write/maintain a projection) | Medium to high (bounded by spec coverage) | High where the spec is authoritative | Apps with GraphQL, form/validation schemas, or server-driven UI |
| Hand-authored per view | Medium per app | Whatever is authored | High (authored against backend state; test-pinned) | A few high-value apps or flows; the upper-bound reference |
| Compiled from the human surface | Near-zero (work is in the compiler) | Broad (any app with a human UI) | Lossy; must be validated against the backend | Existing/legacy apps that cannot be rebuilt |
| Model-extracted | Near-zero | Universal | Lowest; recurs at runtime; hallucination risk | Fallback when no other surface is reachable |

Empirically validating the two *generated* paths (the compiled and
model-extracted surfaces) against the hand-authored upper bound established in
this study (how much coverage and fidelity they retain, and at what cost) is
left to future work (Section 10).

## 9. Limitations and threats to validity

**External validity.** This is one model (`gemini-2.5-flash`) on one small,
synthetic shopping application with a ten-task set. Statistical power is
limited (paired CIs are over 7 success tasks and 3 refusal tasks) and the
results are provisional. A second application is explicitly later work in
`PROTOCOL.md`. We do not generalize beyond a controlled shopping task.

**Construct validity of C4.** The C4 document is hand-authored (an upper bound,
not an automatically generated surface). Its quality is a confound: a badly
written view document would understate C4. We author it once, freeze it in
`build_surface`, and pin it with the surface-backend consistency tests.

**Confounded mechanisms.** Compactness and constraint-pruning are separate
advantages of C4. The planned ablation (Section 6.5) is what disentangles them.
Until that run exists, C3-versus-C4 differences cannot be attributed to one
mechanism.

**Refusal tasks.** Refusal tasks can be passed by inaction. They are reported
separately from success tasks.

**Provider usage reporting.** Image-token itemization is provider-dependent.
Vertex folds image tokens into `prompt_tokens`. Screenshot (C1) cost is read
from total input tokens.

**Determinism.** Temperature-zero decoding is not fully deterministic. Results
are averaged over five repeats. On this run, C3 was stable across repeats;
C4's only variance is t10; C2 is the noisy condition.

**History truncation.** PROTOCOL.md limits history to task text, prior
actions, and the current observation. That choice holds the history policy
fixed across conditions. It also means C3 cannot compensate by accumulating
a long transcript of past views. A different history policy could change C3
versus C4 and is not tested.

**C1 illegal-action metric.** Coordinate clicks on the human page rarely set
the backend `illegal` flag, so C1's illegal/step of 0.000 understates invalid
attempts relative to C3/C4. For C1, read success, steps, and input tokens.

**Statistical power.** Bootstrap CIs on paired differences resample over 7
success tasks (and 3 refusal tasks). They are wide by construction. A CI that
includes zero (C4 minus C3 success) is not proof of equality; it is a failure
to distinguish at this sample size. We do not claim significance we do not
have.

**Models.** The main line uses general models that can do all four conditions in
one API. Specialized computer-use models are out of the main line until the
general-model table is stable. RQ3 (a second general model) has not been run.

## 10. Future work

Immediate: latency instrumentation and a timed re-run; a second and third
general model for model-agnosticism; the constraint-pruning ablation; and an
"ignored-affordance" metric. Longer term: a second, more complex application (the
main external-validity lever); a validated Agent-Experience (AX) metric suite
(the second paper); and methods for *automatically generating* the agent surface
(compiled from the human interface or model-extracted), measured against the
hand-authored upper bound established here.

## Appendix: reproducibility

The application, four-condition harness, deterministic grader, model registry,
and the tooling used for every number above are in the repository; the exact
command sequence is the reproducibility checklist in Section 5 ("Procedures"),
and the environment is defined in `.cursor/`. See
[`research-plan.md`](research-plan.md) for the full methodology and
[`paper-outline.md`](paper-outline.md) for section status. Profile Engineer
ingests the exact PDF [`paper.pdf`](paper.pdf) for
https://akashnaren.github.io/research/ (do not open PRs on that site from here;
the bare reader is Profile’s job).
`python papers/agent-native-ui/build.py` rebuilds `paper.html` and `paper.pdf`
from this file.

## References

Verified sources (to be formatted for the target venue). Titles and URLs are
those already checked in [`research-plan.md`](research-plan.md). No additional
citations are introduced here.

- WebArena: A Realistic Web Environment for Building Autonomous Agents. https://arxiv.org/abs/2307.13854
- VisualWebArena: Evaluating Multimodal Agents on Realistic Visually Grounded Web Tasks. https://aclanthology.org/2024.acl-long.50/
- Mind2Web: Towards a Generalist Agent for the Web. https://arxiv.org/abs/2306.06070
- WebShop: Towards Scalable Real-World Web Interaction with Grounded Language Agents. https://proceedings.neurips.cc/paper_files/paper/2022/file/82ad13ec01f9fe44c01cb91814fd7b8c-Paper-Conference.pdf
- AndroidWorld: A Dynamic Benchmarking Environment for Autonomous Agents. https://arxiv.org/abs/2405.14573
- MiniWoB++ (Reinforcement Learning on Web Interfaces using Workflow-Guided Exploration). https://arxiv.org/abs/1802.08802 ; docs: https://miniwob.farama.org/
- Anthropic: Introducing computer use (Claude 3.5 Sonnet). https://www.anthropic.com/news/3-5-models-and-computer-use
- UI-TARS: Pioneering Automated GUI Interaction with Native Agents. https://arxiv.org/abs/2501.12326
- SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents. https://aclanthology.org/2024.acl-long.505/
- UIFormer / From User Interface to Agent Interface: Efficiency Optimization of UI Representations for LLM Agents. https://arxiv.org/abs/2512.13438
- Prune4Web: DOM Tree Pruning Programming for Web Agent. https://ojs.aaai.org/index.php/AAAI/article/download/40772/44733
- A2UI (Agent-to-UI) Protocol. https://a2ui.org/
- Model Context Protocol (MCP). https://modelcontextprotocol.io/
