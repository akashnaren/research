"""Render paper.md into paper.html, paper.pdf, and web/article.md.

Markdown is the editable source; this produces the human-readable outputs.
HTML is generated with the `markdown` package; the PDF is printed from that
HTML using the Playwright Chromium already installed for the C1/C2 conditions,
so no LaTeX/pandoc toolchain is required.

`web/article.md` is the ingest export for Profile Engineer
(https://akashnaren.github.io/research/). Do not open PRs on that site from here.

Usage (from repo root, with the venv active):
    python papers/agent-native-ui/build.py
"""

from __future__ import annotations

from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SRC = HERE / "paper.md"
HTML_OUT = HERE / "paper.html"
PDF_OUT = HERE / "paper.pdf"
ARTICLE_OUT = HERE / "web" / "article.md"

ARTICLE_FRONTMATTER = """---
title: The Interface Is a Variable
subtitle: Measuring the cost and reliability of purpose-built UI representations for LLM agents
status: working-draft
canonical_source: papers/agent-native-ui/paper.md
ingest_for: https://akashnaren.github.io/research/
site_owner: Profile Engineer owns the GitHub Pages site. Do not open PRs on akashnaren.github.io from this repository.
---

# The Interface Is a Variable

*Working draft for a later Medium-like reader on https://akashnaren.github.io/research/. The scholarly source of truth is [`paper.md`](../paper.md). Numbers below are one model (`gemini-2.5-flash`) on one synthetic store. They are provisional.*

"""

CSS = """
@page { size: A4; margin: 22mm 20mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 11.5pt; line-height: 1.55; color: #1a1a1a;
  max-width: 820px; margin: 0 auto; padding: 24px;
}
h1 { font-size: 20pt; line-height: 1.25; margin: 0 0 4px; }
h2 { font-size: 15pt; margin: 1.4em 0 0.4em; border-bottom: 1px solid #ddd; padding-bottom: 3px; }
h3 { font-size: 12.5pt; margin: 1.1em 0 0.3em; }
p, li { text-align: left; }
em { color: #333; }
code { font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.9em;
  background: #f3f3f3; padding: 1px 4px; border-radius: 3px; }
pre { background: #f6f8fa; padding: 10px 12px; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { margin: 1em 0; padding: 8px 14px; background: #fff8e1;
  border-left: 4px solid #e0b400; color: #5a4a00; font-size: 0.95em; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 10.5pt; }
th, td { border: 1px solid #ccc; padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: #f0f0f0; }
a { color: #0b5cad; text-decoration: none; }
h2, h3 { page-break-after: avoid; }
table, pre, blockquote { page-break-inside: avoid; }
"""


def build_html() -> str:
    text = SRC.read_text()
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
    )
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{SRC.stem}</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


def export_article() -> None:
    """Write a GitHub Pages ingest copy. Profile Engineer owns the live site."""
    body = SRC.read_text()
    if body.startswith("# "):
        body = body.split("\n", 1)[1]
    lines = body.lstrip().splitlines()
    if lines and lines[0].startswith("*Working draft"):
        lines = lines[1:]
        if lines and lines[0].strip() == "":
            lines = lines[1:]
    body = "\n".join(lines)
    for src, dst in (
        ("](paper-outline.md)", "](../paper-outline.md)"),
        ("](research-plan.md)", "](../research-plan.md)"),
        ("](PROTOCOL.md)", "](../PROTOCOL.md)"),
        ("](web/article.md)", "](article.md)"),
    ):
        body = body.replace(src, dst)
    ARTICLE_OUT.parent.mkdir(parents=True, exist_ok=True)
    ARTICLE_OUT.write_text(ARTICLE_FRONTMATTER + body)
    print(f"wrote {ARTICLE_OUT}")


def main() -> None:
    export_article()
    html = build_html()
    HTML_OUT.write_text(html)
    print(f"wrote {HTML_OUT}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(HTML_OUT.as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(PDF_OUT),
            format="A4",
            print_background=True,
            margin={"top": "22mm", "bottom": "22mm", "left": "20mm", "right": "20mm"},
        )
        browser.close()
    print(f"wrote {PDF_OUT}")


if __name__ == "__main__":
    main()
