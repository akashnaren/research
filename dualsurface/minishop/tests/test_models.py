import pytest

from harness.models import resolve_aliases


def test_resolve_single_alias():
    specs = resolve_aliases("gemini-flash")
    assert [s.alias for s in specs] == ["gemini-flash"]
    assert specs[0].provider == "vertex"
    assert specs[0].api_model == "google/gemini-2.5-flash"


def test_resolve_comma_separated_aliases():
    specs = resolve_aliases("gemini-flash,sonnet,grok-fast")
    assert [s.alias for s in specs] == ["gemini-flash", "sonnet", "grok-fast"]
    assert all(s.provider == "vertex" for s in specs)


def test_resolve_mid_sweep():
    specs = resolve_aliases("mid")
    assert [s.alias for s in specs] == ["gemini-flash", "sonnet", "grok-fast"]


def test_resolve_better_sweep():
    specs = resolve_aliases("better")
    assert [s.alias for s in specs] == ["gemini-pro", "sonnet-5", "grok"]


def test_resolve_gcp_sweep():
    specs = resolve_aliases("gcp")
    assert [s.alias for s in specs] == [
        "gemini-flash",
        "gemini-pro",
        "sonnet",
        "sonnet-5",
        "grok-fast",
        "grok",
    ]


def test_resolve_deduplicates_preserving_order():
    specs = resolve_aliases("sonnet,gemini-flash,sonnet")
    assert [s.alias for s in specs] == ["sonnet", "gemini-flash"]


def test_resolve_unknown_alias_raises():
    with pytest.raises(ValueError):
        resolve_aliases("not-a-real-model")


def test_no_computer_use_models_registered():
    # Only check the identifying fields (alias, api_model), not free-text
    # notes -- notes legitimately describe that computer-use is *not* used.
    from harness.models import MODELS

    banned_substrings = ("computer-use", "computer_use", "operator", "ui-tars", "ui_tars")
    for spec in MODELS.values():
        haystack = f"{spec.alias} {spec.api_model}".lower()
        for banned in banned_substrings:
            assert banned not in haystack, f"{spec.alias} looks like a computer-use/action model"
