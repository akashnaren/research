# Catalog-size observation-cost sweep (model-free)

Unit run 2026-09-16 on main `b7a4007` (RESEARCH_NOTES ranked unit 3). Zero
model / Vertex / OpenAI calls: the sweep replays the canonical task paths in
memory against synthetically padded catalogs and counts observation tokens
with the local `o200k_base` tokenizer. PROTOCOL, grader, prompts, tasks, and
the real catalog are unchanged.

## Question

`paper.md` Section 7.1 predicts that MiniShop's 8-product catalog flatters
both structured conditions, and Section 10 queues this measurement: how does
the per-look observation cost move as the catalog grows, and where does the
C4 view document overtake the C3 schema?

## Method

- `harness/obs_cost.py --catalog-sweep 8,50,500,5000`: the real 8 products are
  kept byte for byte and synthetic products (`pad-0000`...) are appended, so
  every frozen task and scripted policy replays unchanged at every size.
- Same statistic as the existing baseline: median over success tasks of each
  task's per-step observation tokens on the canonical path. The in-memory
  replay reproduces the HTTP baseline exactly at n=8 (pinned by
  `tests/test_obs_cost.py::test_in_memory_replay_matches_http_baseline_at_real_size`).
- C2 needs a rendered page and is out of this deterministic path (same as the
  existing baseline).

## Result

| catalog products | C1(est) obs/step | C3 obs/step | C4 obs/step | C3 one-time list_products payload |
| --- | --- | --- | --- | --- |
| 8 | 1105 | 512 | 453 | 369 |
| 50 | 1105 | 512 | 992 | 2847 |
| 500 | 1105 | 512 | 6767 | 29397 |
| 5000 | 1105 | 512 | 64517 | 294897 |

**Crossover: C4's median obs/step overtakes C3's at a catalog of 13
products** (binary search over the same statistic; at 12 products C4 <= C3,
at 13 products C4 > C3).

## Reading, honestly

- The n=8 row reproduces the recorded baseline (1105 / 512 / 453), so the
  sweep is anchored to the published numbers.
- C4's per-look advantage at n=8 is a small-catalog artifact of the current
  hand-authored document: it embeds the whole catalog on the catalog view and
  an enum of every product id inside `open_product`'s input schema on every
  view, so it grows roughly linearly with the catalog on every step. Thirteen
  products is all it takes to lose the per-look edge.
- C3's canonical-path cost is catalog-independent (schema 490 + tiny status
  replies; the schema has no per-product content). But the canonical paths
  never call `list_products`, because they are the C4-legal minimal paths. A
  real flat-tools run pays the `list_products` response at least once per
  task, and that payload grows linearly too (last column). So at scale
  neither condition survives as designed: C4 pays per step, C3 pays per
  lookup.
- C1's image estimate is constant by construction (resolution-driven), which
  restates the paper's point that image cost tracks the viewport, not
  content.
- Design implication for the paper's Section 7.1 claim: a scale-aware view
  document must grow with what is on the current screen (paginated entities,
  reference-style ids instead of a full enum), not with the size of the
  database. This sweep quantifies why. It does not change any recorded model
  result; the 8-product Tables 1 to 3 stand as published.

## Reproduce and proof

From `dualsurface/minishop/`:

```bash
python -m harness.obs_cost --catalog-sweep 8,50,500,5000 --out report
```

- Sweep run: exit 0, writes `report/obs_cost_catalog_sweep.csv` (gitignored;
  regenerate locally). Run log: table above is the verbatim output.
- `pytest -q`: 67 passed (includes 6 new sweep tests: catalog shape, HTTP
  parity at n=8, C4 monotone growth with C3/C1 constant, payload growth,
  crossover consistency at 13).
- `python -m harness.scripted`: all tasks PASS on C3 and C4 (exit 0).
- No model API calls were made at any point in this unit.
