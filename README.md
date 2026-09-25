# Research

Personal research repository. Each paper has a folder under `papers/`.
MiniShop and its harness (Paper 1) live in `dualsurface/minishop/`, not in the paper folder.

## Papers

| Paper | Path | Status |
| --- | --- | --- |
| 1. Agent-native UI (MiniShop C1-C4) | [`papers/agent-native-ui/`](papers/agent-native-ui/) | Working draft, frozen protocol, and first results |
| 2. ARC-AGI-1 hallucination | [`papers/arc-agi-1-hallucination/`](papers/arc-agi-1-hallucination/) | Planned. Empty. |
| 3. Gap-aware entity resolution | [`papers/gap-aware-entity-resolution/`](papers/gap-aware-entity-resolution/) | Planned. Empty. |

Paper 1 draft: [`papers/agent-native-ui/paper.md`](papers/agent-native-ui/paper.md).
Protocol: [`papers/agent-native-ui/PROTOCOL.md`](papers/agent-native-ui/PROTOCOL.md).
Notes: [`papers/agent-native-ui/RESEARCH_NOTES.md`](papers/agent-native-ui/RESEARCH_NOTES.md).
PDF: [`papers/agent-native-ui/paper.pdf`](papers/agent-native-ui/paper.pdf). The site reads this file.
Do not open pull requests on `akashnaren.github.io` from this repo.

## MiniShop (Paper 1 experiment)

```bash
cd dualsurface/minishop
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn minishop.server:app --reload --port 8765
python -m harness.scripted
pytest -q
```

C1/C2 need Playwright Chromium and a running server. The model loop writes JSONL
traces to `dualsurface/minishop/traces/` (gitignored):

```bash
playwright install chromium
python -m harness.model_loop --conditions C3,C4
python -m harness.model_loop --conditions C1,C2,C3,C4
```

Copy `dualsurface/minishop/.env.example` to `.env` for `OPENAI_API_KEY`.
Do not commit secrets. Use one general model for all conditions
(`MODEL=gpt-4o-mini` by default; `gpt-4o` for a reported OpenAI table). The
numbers in the Paper 1 draft are `gemini-2.5-flash` via Vertex.

Other general models come from GCP Vertex AI Model Garden: mid-tier Gemini,
Claude Sonnet without a computer-use tool, Grok, and optional stronger
variants. Run `gcloud auth application-default login`, set
`GOOGLE_CLOUD_PROJECT` and `VERTEX_LOCATION` in `.env`, and pass `--models`
(an alias list or a sweep name) instead of `--model`:

```bash
python -m harness.model_loop --models gemini-flash,sonnet,grok-fast --conditions C3,C4
python -m harness.model_loop --models mid    # sweep: gemini-flash, sonnet, grok-fast
python -m harness.model_loop --models better # sweep: gemini-pro, sonnet-5, grok
python -m harness.model_loop --models gcp    # all six Vertex aliases
```

See `dualsurface/minishop/harness/models.py` and
`dualsurface/minishop/README.md`. `--model` (OpenAI) is still the default.

Build the Paper 1 HTML and PDF:

```bash
python papers/agent-native-ui/build.py
```

Needs the MiniShop venv (Playwright Chromium and the `markdown` package).
