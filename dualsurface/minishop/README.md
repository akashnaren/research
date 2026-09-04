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

C1 clicks the human pages from a screenshot. C2 uses the accessibility tree of those same pages. Neither condition may call the JSON agent API to act.
