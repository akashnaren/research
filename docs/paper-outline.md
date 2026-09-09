# Paper outline (Paper 1): agent-facing interfaces

This is the working skeleton for the first paper. It maps what the repository
already contains onto real paper sections, marks the status of each, and states
what each section still needs. It is a scaffold, not the paper; it defers to
[`PROTOCOL.md`](../PROTOCOL.md) for the frozen design and to
[`research-plan.md`](research-plan.md) for the detailed methodology and the
verified novelty analysis, rather than duplicating them.

Status tags:
- **[HAVE]** — content exists in the repo and can be written up now.
- **[PROVISIONAL]** — we have a result, but it is single-model / single-pass and must not be over-claimed.
- **[NEEDS DATA]** — requires a run or measurement we have not done yet.
- **[TODO]** — writing only; no new data needed.

Working title (placeholder): *The Interface Is a Variable: Measuring the Cost
and Reliability of Purpose-Built UI Representations for LLM Agents.*

---

## Abstract — [TODO]
One paragraph: agents mostly reuse interfaces built for humans; we treat the
interface representation as a controlled variable on a fixed task and grader,
compare four representations (screenshot, accessibility tree, flat tools, a
purpose-built view document), and report a cost–reliability frontier. Headline:
human-surface representations are dominated; among structured representations the
trade-off is subtle and model-dependent. Write last, once the second model and
latency numbers are in.

## 1. Introduction — [TODO, source material HAVE]
- The agent loop (observe → decide → act); every observation is input tokens.
- The interface is a control variable, not a fixed cost of automation.
- The applied motivation (apps may ship an agent surface as they ship an API),
  stated as motivation, not as the contribution.
- Contributions: (i) a controlled measurement method for interface
  representations at matched action grain; (ii) a cost–reliability (Pareto)
  framing with paired per-task inference; (iii) first evidence on one app/model,
  including a model-free observation-cost baseline and an execution grader.
- Source: `research-plan.md` §1–2.

## 2. Related work — [HAVE]
Draw directly from `research-plan.md` "Novelty and positioning" (verified
sources): DOM/accessibility-tree agents and screenshot/computer-use models
(these are our C1/C2 baselines); UI-representation optimization (UIFormer,
Prune4Web — they *compress a human-derived tree*, we *author a surface*);
agent-UI protocols (A2UI is the reverse direction; MCP is a capability catalog
≈ our C3, not a stateful view layer); GUI/web-agent benchmarks (WebArena,
VisualWebArena, Mind2Web, WebShop, AndroidWorld, MiniWoB++ — they vary the
agent and fix the interface; we do the opposite).

## 3. Study design — [HAVE]
- Application: MiniShop; the four conditions C1–C4 (define each precisely);
  the C3/C4 same-grain constraint as the identification move.
- Task set (10 tasks; 7 success + 3 refusal); the execution-based, non-model
  grader; temperature 0; step cap 20; fixed history.
- The C4 view document format (view, state, entities, affordances with
  `enabled` + argument JSON Schema) and that it is hand-authored from backend
  state (an upper bound), with the surface–backend consistency invariant
  (`tests/test_surface_consistency.py`) that keeps it honest.
- Source: `PROTOCOL.md`, `research-plan.md` §2–3, and §9 "Deployment and
  generalization" for how such a surface could be produced at scale (framing).

## 4. Metrics and analysis — [HAVE], latency [NEEDS DATA]
- Dependent variables: success, input/output tokens (image tokens on C1), steps,
  illegal actions, and the honest `malformed_actions` metric.
- The token-accounting decomposition (per-step observation cost × steps + overhead).
- Analysis: per-(model, condition) table; cost–reliability Pareto; **paired
  per-task** C4-vs-C3 differences with bootstrap 95% CIs.
- **Latency [NEEDS DATA]:** not yet instrumented. Add per-call wall-clock timing
  and report median time-to-completion per condition; note it weights round
  trips (fewer steps) differently from token cost, so it can move the C3/C4
  verdict. Tooling: `harness/report.py`, `harness/obs_cost.py`.

## 5. Results

### 5.1 Model-free observation-cost baseline — [HAVE]
Per-step observation tokens (o200k_base): C1 ~1105, C3 ~512, C4 ~453. Text
representations are ~2.4× cheaper per look than a screenshot; C4 slightly cheaper
than C3 per step (C3 resends the tool schema). `harness/obs_cost.py`.

### 5.2 Pipeline control (oracle) — [HAVE]
Deterministic perfect-agent control validates the pipeline; both C3/C4 reach
100%. Establishes best-case behavior and the trace→report→Pareto path.

### 5.3 First model run: gemini-2.5-flash, N=5 — [PROVISIONAL]
The CI table (C1 30% / C2 72% / C3 100% / C4 92%), the input-token gap, the
illegal/malformed rates, and the paired C4-vs-C3 result (C4 saves steps
significantly, costs +1404 input tokens/task significantly, no significant
success gain → C3 Pareto-preferred here). The t10 finding: C4's only success
deficit is the model ignoring an `enabled:false` flag — genuine model behavior,
not a surface bug. Artifacts: Pareto + paired figures.

### 5.4 Second model (RQ3) — [NEEDS DATA]
Repeat with `sonnet` and/or `grok-fast` to test whether "C3 ≥ C4" is
model-specific; especially whether other models obey the `enabled` flag on t10.

### 5.5 Constraint-pruning ablation — [NEEDS DATA]
Strip `enabled` flags + argument enums from the C4 document (keep view+entities)
to separate *compactness* from *constraint-carrying*, and to explain C4's token
overhead.

## 6. Discussion — [PROVISIONAL]
- On the simplest app with a model that ignores constraints, the view document's
  overhead is not yet worth it; flat tools are Pareto-preferred on tokens/success.
- Why this is the least favorable setting for C4 (small state, short tasks) and
  where the crossover is hypothesized (complex apps; constraint-respecting models;
  latency-weighted cost; safety-sensitive settings where illegal actions matter).
- The "advisory affordance" finding: a truthful `enabled` flag was ignored — a
  measurable AX signal (proposed "ignored-affordance" rate) and a bridge to Paper 2.

## 7. Threats to validity / limitations — [HAVE]
One model, one synthetic app, 10-task power, temperature-0 residual
nondeterminism, hand-authored C4 (upper bound), provider-dependent image-token
reporting, latency not yet measured, refusal tasks passable by inaction (reported
separately). Source: `research-plan.md` §8.

## 8. Future work — [TODO]
Second/third models; ablation; latency + ignored-affordance metrics; a second,
more complex application; the AX metric suite (Paper 2); automatic generation of
the agent surface (compiled/model-extracted) measured against the hand-authored
upper bound.

## Appendix: reproducibility — [HAVE]
Commands (`harness.scripted`, `harness.model_loop [--oracle] [--repeats]`,
`harness.report`, `harness.obs_cost`), the environment (`.cursor/`), the model
registry (`harness/models.py`), and the test suite.

---

## Roadmap: where to go from here (priority order)

1. **Latency instrumentation + timed re-run** — directly answers whether C4's
   fewer round trips offset its token cost. Small harness change; one paid sweep.
   Fills §4 latency and may change §5.3/§6.
2. **Second general model (RQ3)** — `sonnet` or `grok-fast` (needs Vertex Model
   Garden enablement). Tests whether the C3-preferred result generalizes. Fills §5.4.
3. **Constraint-pruning ablation** — explains *why* C4 is token-heavy and whether
   the step savings survive without the constraints. Fills §5.5.
4. **"Ignored-affordance" metric** — count when the model picks a `disabled`
   affordance; makes the t10 phenomenon measurable across models. Feeds §6 / Paper 2.
5. **Second application** — the real external-validity lever; the current single
   synthetic store is C4's least favorable case.

Each item slots into a specific section above, so the paper fills in as runs land.
