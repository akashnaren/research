# Agent surface interfaces

Pilot study: four ways of presenting the same store to a language model, measuring tokens, steps, success, and illegal actions.

See [PROTOCOL.md](PROTOCOL.md) for the frozen experimental design.

## Model policy

Main experiments use general, accessible models (default `gpt-4o-mini`; reported table `gpt-4o`) that support vision and structured output in one API. Specialized computer-use models are reserved for a final comparison.

Use **one** model for C1–C4 in a comparison. Do not mix checkpoints. Temperature is 0, step cap is 20, and history is task + prior actions + current observation only.

## MiniShop

```bash
cd dualsurface/minishop
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # needed for C1/C2 only
```

Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Do not commit `.env`.

### Server

```bash
uvicorn minishop.server:app --reload --port 8765
```

Human UI: `http://127.0.0.1:8765/`  
Agent API: `POST /agent/session`, `GET /agent/surface`, `GET /agent/tools`, `POST /agent/act`, `GET /agent/state`, `GET /agent/tasks`, `GET /agent/grade`.

`POST /agent/act` with `enforce_surface: true` is C4; `false` is C3. Illegal actions return HTTP 400 `{"illegal": true, "error": "..."}`.

### Scripted tests (no model)

A non-model policy must complete every expected-success task on C3 and C4, and end on a rejected action for the refusal tasks:

```bash
python -m harness.scripted
pytest -q
```

### Model loop

The store must already be running. Traces are JSONL under `traces/` (gitignored), including provider usage tokens per step and image tokens on C1 when the API reports them.

```bash
python -m harness.model_loop --conditions C3,C4
python -m harness.model_loop --conditions C1,C2,C3,C4
python -m harness.model_loop --conditions C4 --tasks t01,t02 --model gpt-4o
```

`--model` (single OpenAI model id) is the default fallback path and behaves exactly as before.

To run one or more general models sourced from GCP Vertex AI Model Garden, use `--models` with a
comma-separated list of aliases from `harness/models.py`, or a named sweep (`mid`, `better`, `gcp`):

```bash
# gcloud auth application-default login
# GOOGLE_CLOUD_PROJECT=..., VERTEX_LOCATION=global in .env
python -m harness.model_loop --models gemini-flash,sonnet,grok-fast --conditions C3,C4
python -m harness.model_loop --models mid --conditions C1,C2,C3,C4
python -m harness.model_loop --models better --conditions C3,C4
python -m harness.model_loop --models gcp --conditions C3,C4
```

Every requested model runs across every requested condition; each model x condition combination
gets its own trace file and its own `model_alias`-tagged result row (never pooled, per PROTOCOL.md).
Vertex auth is Application Default Credentials (no API key); each Vertex model must also be enabled
in the project's Model Garden. Claude's computer-use tool, UI-TARS, Operator, and other GUI-pretrained
action models are intentionally not registered here -- see PROTOCOL.md "Models".

C1 clicks the human pages from a screenshot. C2 uses the accessibility tree of those same pages. Neither condition may call the JSON agent API to act.

### Analysis

`harness.report` aggregates the JSONL traces into a per-`(model, condition)` table (success rate, median steps, median input/output/image tokens, illegal actions per step) and a cost–reliability Pareto frontier. Results are reported per model, never pooled (see PROTOCOL.md "Models").

```bash
python -m harness.report --traces traces --out report            # table + CSV
python -m harness.report --traces traces --out report --figures  # also pareto.png, input_tokens.png (needs matplotlib)
```

`harness.obs_cost` is a model-free baseline: it replays each task's canonical path and counts the per-step observation tokens each condition imposes (C3/C4 exact and server-side; C1 an OpenAI gpt-4o high-detail image estimate; C2 needs a browser and is measured at run time). No API key and no cost.

```bash
python -m harness.obs_cost --out report   # per-task + per-condition table, writes report/obs_cost.csv
```

See [`docs/research-plan.md`](../../docs/research-plan.md) for the metrics, the token accounting, the plots, and the ordered experimental steps.
