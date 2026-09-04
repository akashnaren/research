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
