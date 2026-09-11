# Results and figures (Paper 1)

Pointers only. Numbers in `paper.md` Section 6 are from the
`gemini-2.5-flash` N=5 sweep already recorded in `research-plan.md`. This file
does not add results.

## Generated (gitignored; regenerate locally)

From `dualsurface/minishop/`:

```bash
python -m harness.obs_cost --out report
python -m harness.model_loop --oracle --conditions C3,C4
python -m harness.report --traces traces --out report --figures
```

Expected artifacts (not in git):

- `dualsurface/minishop/traces/` : JSONL per run
- `dualsurface/minishop/report/summary.md` and CSV
- Pareto and paired figures named in the research plan
  (`gemini_repeats_pareto.png`, `gemini_c3_c4_paired.png`) when `--figures` is
  used
- Token-accounting figures from `harness/make_figures.py`
  (`image_tokens_vs_resolution.png`, `token_composition_by_condition.png`)

## Fixture screenshots (in git)

Human MiniShop pages used as C1/C2 observation examples:

- `docs/minishop/catalog.png`
- `docs/minishop/product-blue-soldout-m.png`
- `docs/minishop/checkout.png`
- `docs/minishop/confirmation.png`
