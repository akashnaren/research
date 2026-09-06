"""Registry of general, non computer-use models for the MiniShop model loop.

Per PROTOCOL.md "Models": the main line uses one general model at a time,
run separately per condition (never pooled/mixed across conditions). This
registry adds Google Cloud Vertex AI as a source of additional general
models -- mid-tier Gemini, Claude Sonnet (no computer-use tool), and Grok --
plus optional stronger variants, and keeps the OpenAI path as a fallback.

Model ids were confirmed against:
- https://cloud.google.com/vertex-ai/generative-ai/docs/start/openai
  (Gemini via the Vertex OpenAI-compatible endpoint, publisher prefix
  "google/", e.g. "google/gemini-2.5-flash"; the docs' own examples have
  started showing "google/gemini-3.5-flash" as 2.5 models are retired --
  if `gemini-2.5-flash` 404s in your project, try the 3.5 id below.)
- https://platform.claude.com/docs/en/build-with-claude/claude-on-vertex-ai
  (Claude on Vertex: "claude-sonnet-4-5@20250929", "claude-sonnet-5"; we use
  the unversioned "anthropic/claude-sonnet-4-5" / "anthropic/claude-sonnet-5"
  publisher-prefixed ids for the OpenAI-compatible endpoint.)
- https://cloud.google.com/vertex-ai/generative-ai/docs/partner-models/grok
  and https://docs.litellm.ai/docs/providers/vertex_partner
  (Grok on Vertex Model Garden: "grok-4.1-fast-non-reasoning", "grok-4.6";
  publisher prefix "xai/").

IMPORTANT: every model below is a *general* model. This file intentionally
does not register Claude's computer-use tool, UI-TARS, Operator, or any
other GUI-pretrained action model -- those are out of scope for the main
line per PROTOCOL.md and must not be added here.

Model Garden note: each Vertex model below must be individually enabled in
your GCP project's Model Garden (and quota granted) before it can be called;
`harness/vertex.py` will surface the provider's error if it is not.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    provider: str  # "vertex" or "openai"
    api_model: str
    vision: bool = True
    tools: bool = True
    json_object: bool = True
    tier: str = "mid"
    notes: str = ""


MODELS: dict[str, ModelSpec] = {
    "gemini-flash": ModelSpec(
        alias="gemini-flash",
        provider="vertex",
        api_model="google/gemini-2.5-flash",
        vision=True,
        tools=True,
        json_object=True,
        tier="mid",
        notes=(
            "Mid-tier Gemini. If retired in your project, try "
            "google/gemini-3.5-flash (Vertex OpenAI-compat docs' current example id)."
        ),
    ),
    "gemini-pro": ModelSpec(
        alias="gemini-pro",
        provider="vertex",
        api_model="google/gemini-2.5-pro",
        vision=True,
        tools=True,
        json_object=True,
        tier="better",
        notes="Stronger Gemini variant.",
    ),
    "sonnet": ModelSpec(
        alias="sonnet",
        provider="vertex",
        api_model="anthropic/claude-sonnet-4-5",
        vision=True,
        tools=True,
        json_object=False,
        tier="mid",
        notes=(
            "Claude Sonnet, no computer-use tool. Anthropic's OpenAI-compat "
            "path on Vertex may not honor response_format=json_object "
            "reliably; the loop falls back to prompt-only JSON for this spec."
        ),
    ),
    "sonnet-5": ModelSpec(
        alias="sonnet-5",
        provider="vertex",
        api_model="anthropic/claude-sonnet-5",
        vision=True,
        tools=True,
        json_object=False,
        tier="better",
        notes="Newer Claude Sonnet variant, no computer-use tool.",
    ),
    "grok-fast": ModelSpec(
        alias="grok-fast",
        provider="vertex",
        api_model="xai/grok-4.1-fast-non-reasoning",
        vision=True,
        tools=True,
        json_object=True,
        tier="mid",
        notes="Cost-effective, low-latency Grok (non-reasoning).",
    ),
    "grok": ModelSpec(
        alias="grok",
        provider="vertex",
        api_model="xai/grok-4.6",
        vision=True,
        tools=True,
        json_object=True,
        tier="better",
        notes="xAI's flagship Grok variant on Vertex Model Garden.",
    ),
    "gpt-4o-mini": ModelSpec(
        alias="gpt-4o-mini",
        provider="openai",
        api_model="gpt-4o-mini",
        vision=True,
        tools=True,
        json_object=True,
        tier="mid",
        notes="OpenAI fallback if a GCP model can't be enabled in Model Garden.",
    ),
    "gpt-4o": ModelSpec(
        alias="gpt-4o",
        provider="openai",
        api_model="gpt-4o",
        vision=True,
        tools=True,
        json_object=True,
        tier="better",
        notes="OpenAI fallback if a GCP model can't be enabled in Model Garden.",
    ),
}


SWEEPS: dict[str, list[str]] = {
    "mid": ["gemini-flash", "sonnet", "grok-fast"],
    "better": ["gemini-pro", "sonnet-5", "grok"],
    "gcp": ["gemini-flash", "gemini-pro", "sonnet", "sonnet-5", "grok-fast", "grok"],
}


def resolve_aliases(raw: str) -> list[ModelSpec]:
    """Resolve a comma-separated alias list, or a single sweep name, to specs.

    Order is preserved and duplicates are dropped. Raises ValueError on an
    unknown alias or sweep name.
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("no model aliases or sweep name given")

    if "," not in raw and raw in SWEEPS:
        names = SWEEPS[raw]
    else:
        names = [item.strip() for item in raw.split(",") if item.strip()]

    specs: list[ModelSpec] = []
    seen: set[str] = set()
    for name in names:
        if name not in MODELS:
            known = ", ".join(sorted(MODELS)) + " (or sweeps: " + ", ".join(sorted(SWEEPS)) + ")"
            raise ValueError(f"unknown model alias {name!r}. Known: {known}")
        if name in seen:
            continue
        seen.add(name)
        specs.append(MODELS[name])
    return specs
