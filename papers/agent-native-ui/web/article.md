---
title: The Interface Is a Variable
dek: Four ways to show the same store to a language-model agent. On one model, screenshots lose. A purpose-built view document saves steps but not yet tokens.
byline: Author TBD
status: working-draft
canonical_source: papers/agent-native-ui/paper.md
ingest_for: https://akashnaren.github.io/research/
site_owner: Profile Engineer renders this on GitHub Pages. Do not open PRs on akashnaren.github.io from the research repo.
---

# The Interface Is a Variable

*Measuring the cost and reliability of purpose-built UI representations for LLM agents*

By Author TBD. Working draft. One model (`gemini-2.5-flash`), one synthetic store (MiniShop), ten tasks. Numbers are provisional.

The scholarly manuscript is [`../paper.md`](../paper.md). This page is the reader export for https://akashnaren.github.io/research/.

## The problem

An agent that operates software runs a loop: observe, decide, act, observe again. Every observation enters the model as input tokens. The application does not change across that loop. Only the *representation* the agent reads does.

Today that representation is almost always one built for people. Three inherited channels dominate, and each fails the agent differently.

**Screenshots.** The model must parse pixels and ground them into click coordinates. Grounding is a known failure mode (SeeClick, UI-TARS, Claude computer use). Image cost tracks viewport size, not how much the page says. On MiniShop, a model-free baseline already prices one screenshot look at about 1105 tokens.

**Accessibility or DOM trees.** The model reads a verbose tree built for assistive technology. Mind2Web filters that tree because it is too large. UIFormer measures UI representation at 80 to 99 percent of agent token cost. The tree also names elements the backend will reject.

**Flat tools.** The model gets function schemas and a short status object, with no current-view document (close to MCP). Cheap per call once the schema is paid, but the model must remember which view it is on and which actions are legal. Light work on a tiny store. Expected to grow with complexity.

None of these three was designed to answer, cheaply and unambiguously, *what is true now and what may be done next.*

An **agent-native** alternative is a JSON *view document* authored from backend state: current view, entities, and affordances with `enabled` flags and argument schemas. Not a better screenshot. Not a pruned DOM. A projection of the same backend the grader already trusts.

The product question (should apps ship this the way they ship an API?) is motivation, not the contribution. The contribution is a measurement: hold the store, the tasks, and the grader fixed, vary only the representation, and read a cost-reliability frontier.

## Four conditions, one store

| ID | What the agent sees | How it acts |
| --- | --- | --- |
| C1 | Screenshot of the human page | Click coordinates, type, scroll |
| C2 | Accessibility tree of that page | Click or fill named elements |
| C3 | Flat function catalog, no current view | Call those functions |
| C4 | JSON view document | Invoke an enabled affordance with typed arguments |

C3 and C4 expose the **same operations at the same grain** (`open_product`, `set_size`, `add_to_cart`, `go_catalog`, `go_checkout`, `set_address`, `pay`). C4 only adds the document. If C4 had fewer or easier actions, a win could be "fewer buttons," not "a better representation." Matched grain blocks that. Compactness versus constraint-pruning is still confounded until an ablation is run.

**Held fixed:** MiniShop, ten frozen tasks, execution-based grader, one model per comparison, temperature 0, step cap 20, history = task + prior actions + current observation.

**Varied:** the observation and action channel.

Human pages C1 and C2 actually see:

- `docs/minishop/catalog.png`
- `docs/minishop/product-blue-soldout-m.png`
- `docs/minishop/checkout.png`
- `docs/minishop/confirmation.png`

## What prior work already shows

Verified sources only (full titles and URLs in the manuscript References). No new arXiv ids.

Benchmarks (WebArena, VisualWebArena, Mind2Web, WebShop, AndroidWorld, MiniWoB++) vary the agent and fix the interface. We do the opposite.

Screenshot and pixel systems (Claude computer use, UI-TARS, SeeClick) are our C1. DOM and accessibility agents (Mind2Web, WebArena) are our C2. UIFormer and Prune4Web compress a human-derived tree. Closest in spirit, still not an agent-authored surface.

A2UI is agent-to-human. MCP is a capability catalog (close to C3). C4 is application-to-agent, per-view, constraint-carrying. It is a measurement probe, not a proposed standard.

"Representation matters" is already known. Execution grading is already known. Token-efficient UI trees are already known. The claim here is the controlled A/B/C/D, not those facts.

TODO (citation to find, not asserted): a verified primary source for action masking or constrained decoding.

## Results: one model, N=5

`gemini-2.5-flash` via Vertex, temperature 0, step cap 20, ten tasks, five repeats (200 runs). Bootstrap 95% CIs over the 50 task-repeat units per cell.

Generated plots (gitignored, from `python -m harness.report --figures`): `dualsurface/minishop/report/gemini_repeats_pareto.png`, `dualsurface/minishop/report/gemini_c3_c4_paired.png`.

| Condition | Success (95% CI) | Median input tokens (95% CI) | Median steps | Illegal/step | Malformed/step |
| --- | --- | --- | --- | --- | --- |
| screenshot (C1) | 30% [18, 42] | ~46,338 [46,324, 46,368] | 20 | 0.000 | 0.000 |
| accessibility tree (C2) | 72% [60, 84] | ~6,770 [5,835, 9,714] | 7 | 0.198 | 0.116 |
| flat tools (C3) | 100% [100, 100] | ~3,134 [3,118, 3,154] | 7 | 0.000 | 0.000 |
| view document (C4) | 92% [84, 98] | ~4,455 [4,413, 4,491] | 6 | 0.016 | 0.000 |

**Success.** C1 passes 30% and *none* of the seven success tasks (its passes are refusal tasks). C2 reaches 72% but mixes backend rejections with malformed JSON. C3 is 100%. C4 is 92%, with the entire gap on task t10.

**Tokens.** C1 costs about 10 times C4 and about 15 times C3. Vertex folds image tokens into `prompt_tokens`, so C1's `image_tokens` field reads 0; cost is in total input. Across the 200 runs: about 2.82M input and 35k output tokens, about $0.93 at the recorded Flash rates. C1 is about 73% of that bill (2.11M input). C3 is cheapest among text conditions; C4 is next; C2 is most expensive and most variable.

**Steps.** C4 uses the fewest median steps (6). C3 uses 7. C1 sits at the cap (20) because it never completes a success task.

**Illegal and malformed.** C2 is the outlier: 0.198 illegal/step and 0.116 malformed/step. C1's illegal rate of 0.000 is not virtue: coordinate clicks rarely trip the backend flag. C4's 0.016 illegal/step is concentrated on t10.

A scripted non-model policy completes all expected-success tasks on C3 and C4. A deterministic oracle agent also reaches 100% on both, so C4's model deficit is the model, not the harness.

## Paired C4 versus C3

Same tasks under both conditions. Average each task over five repeats, take C4 minus C3, bootstrap 95% CI over tasks.

| Task set | n | Metric | Mean diff (C4 minus C3) | 95% CI | Excludes 0? |
| --- | --- | --- | --- | --- | --- |
| success | 7 | success | −0.114 | [−0.343, 0.000] | no |
| success | 7 | input tokens | +1,404 | [+1,317, +1,549] | yes |
| success | 7 | steps | −1.17 | [−1.51, −1.00] | yes |
| refusal | 3 | success | 0.000 | [0.000, 0.000] | no |
| refusal | 3 | input tokens | +386 | [−174, +815] | no |
| refusal | 3 | steps | −0.33 | [−1.00, 0.00] | no |

C4 **saves steps** (CI excludes zero) and **costs more tokens** (CI excludes zero; all seven success tasks are positive). It does **not** significantly change success (CI includes zero). On this cell, C3 is Pareto-preferred: cheaper and at least as reliable. The hypothesis that C4 dominates is not supported here.

## Task t10: the model ignored `enabled: false`

t10: buy a Navy Crew Tee in size L, ship to 77 Oak Lane, Denver. Valid order: open product, add to cart, go to checkout, *then* set the address.

On C4 the model issued `set_address` while still on the **product** view. The document had `enabled: false` on that affordance. The backend returned HTTP 400 `illegal`. Surface and backend agree; a regression test pins it. This is model behavior, not a harness bug.

Reproduced: 4 of 5 repeats in the main sweep, 5 of 5 on a t10-only re-run, same illegal step. A truthful document does not help a model that does not read `enabled`. That quantity (ignored-affordance rate) is what a second model must measure.

## What this cell implies, and what the next cells must show

This is one cell in a planned grid: one general model, one synthetic store.

It shows that representation moves success, tokens, steps, and error rates (RQ1, coarse). Human surfaces are dominated here. C4's mechanism (fewer steps) is present and not large enough to beat C3 on tokens. MiniShop is the *least favorable* setting for C4: tiny state, short tasks, a model that ignores flags.

Later cells, not yet run:

1. **Second general model, N=5.** If it obeys `enabled: false` on t10, C4 success should rise toward C3. If it still misses, the miss is not unique to Flash. Never pool models.
2. **C4 ablation.** Strip flags and enums, keep view and entities. Separates compactness from constraint-carrying.
3. **Latency.** Fewer round trips could flip the verdict without changing token ranks.
4. **A harder application.** Where C3's memory tax is hypothesized to grow. "C3 wins on MiniShop" is not "do not ship C4."

## Limitations

One model, one synthetic store, ten tasks. Paired CIs resample over 7 success tasks and 3 refusal tasks; they are wide. A CI that includes zero is not proof of equality. C4 is hand-authored (an upper bound). Image tokens are provider-dependent. Latency is not measured. Refusal tasks can pass by inaction (reported separately). Temperature 0 is not full determinism. C1's illegal metric understates invalid clicks. Compactness and constraints remain confounded. Specialized computer-use models are out of the main line.

## Figures (paths)

In git:

- `docs/minishop/catalog.png`
- `docs/minishop/product-blue-soldout-m.png`
- `docs/minishop/checkout.png`
- `docs/minishop/confirmation.png`

Generated locally, gitignored:

- `dualsurface/minishop/report/gemini_repeats_pareto.png`
- `dualsurface/minishop/report/gemini_c3_c4_paired.png`
- `image_tokens_vs_resolution.png` and `token_composition_by_condition.png` from `harness/make_figures.py`

## Further reading

Manuscript: [`../paper.md`](../paper.md). Protocol: [`../PROTOCOL.md`](../PROTOCOL.md). Notes: [`../RESEARCH_NOTES.md`](../RESEARCH_NOTES.md).
