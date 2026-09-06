# Agent surface interfaces

Pilot study: four ways of presenting the same store to a language model, measuring tokens, steps, success, and illegal actions.

See [PROTOCOL.md](PROTOCOL.md) for the frozen experimental design.

## Model policy

Main experiments use general, accessible models (default `gpt-4o-mini`; reported table `gpt-4o`) that support vision and structured output in one API. Specialized computer-use models are reserved for a final comparison.

## MiniShop

```bash
cd dualsurface/minishop
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn minishop.server:app --reload --port 8765
```

```bash
python -m harness.scripted
pytest -q
```

C1/C2 need Playwright Chromium and a running server. The model loop writes JSONL traces to `dualsurface/minishop/traces/` (gitignored):

```bash
playwright install chromium
python -m harness.model_loop --conditions C3,C4
python -m harness.model_loop --conditions C1,C2,C3,C4
```

Copy `dualsurface/minishop/.env.example` to `.env` for `OPENAI_API_KEY`. Never commit secrets. Use one general model for all conditions (`MODEL=gpt-4o-mini` by default; `gpt-4o` for the reported table).

To source additional general models from GCP Vertex AI Model Garden (mid-tier Gemini, Claude Sonnet
without a computer-use tool, Grok, and optional stronger variants), authenticate with
`gcloud auth application-default login`, set `GOOGLE_CLOUD_PROJECT`/`VERTEX_LOCATION` in `.env`, and
use `--models` with an alias list or sweep name instead of `--model`:

```bash
python -m harness.model_loop --models gemini-flash,sonnet,grok-fast --conditions C3,C4
python -m harness.model_loop --models mid    # sweep: gemini-flash, sonnet, grok-fast
python -m harness.model_loop --models better # sweep: gemini-pro, sonnet-5, grok
python -m harness.model_loop --models gcp    # all six Vertex aliases
```

See `harness/models.py` for the model registry and `dualsurface/minishop/README.md` for details.
`--model` (OpenAI) remains the default fallback path and is unaffected.
