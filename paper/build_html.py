#!/usr/bin/env python3
"""Render paper.md into a self-contained, readable paper.html.

paper.md stays the editable source of truth; this produces a styled,
single-file HTML view that opens cleanly in a preview tab. Regenerate after
editing the Markdown:

    python paper/build_html.py

Requires the `markdown` package (pip install markdown).
"""

from __future__ import annotations

from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SRC = HERE / "paper.md"
OUT = HERE / "paper.html"

TITLE = "The Interface Is a Variable"

STYLE = """
:root { color-scheme: light dark; }
html { -webkit-text-size-adjust: 100%; }
body {
  font-family: Georgia, 'Iowan Old Style', 'Palatino Linotype', serif;
  line-height: 1.65;
  color: #1a1a1a;
  background: #faf9f7;
  margin: 0;
  padding: 3rem 1.25rem 6rem;
}
main {
  max-width: 780px;
  margin: 0 auto;
}
h1, h2, h3 {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  line-height: 1.25;
  color: #111;
}
h1 { font-size: 2rem; margin: 0 0 1.5rem; }
h2 {
  font-size: 1.4rem;
  margin: 2.6rem 0 0.9rem;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid #e2ddd4;
}
h3 { font-size: 1.12rem; margin: 1.8rem 0 0.6rem; }
p { margin: 0 0 1.05rem; }
a { color: #1558b0; text-decoration: none; }
a:hover { text-decoration: underline; }
em { color: #333; }
strong { color: #000; }
blockquote {
  margin: 1.4rem 0;
  padding: 0.6rem 1.1rem;
  background: #fff6e6;
  border-left: 4px solid #e0b34d;
  color: #5c4a1e;
  font-size: 0.94rem;
  border-radius: 0 6px 6px 0;
}
blockquote p { margin: 0.3rem 0; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 1.4rem 0;
  font-size: 0.92rem;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: #fff;
}
th, td { border: 1px solid #d9d3c8; padding: 0.5rem 0.7rem; text-align: left; vertical-align: top; }
thead th { background: #f0ebe1; }
tbody tr:nth-child(even) { background: #faf8f4; }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.88em;
  background: #efece6;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
}
pre { background: #f3f0ea; padding: 1rem; border-radius: 8px; overflow-x: auto; }
pre code { background: none; padding: 0; }
ul, ol { margin: 0 0 1.05rem; padding-left: 1.5rem; }
li { margin: 0.3rem 0; }
hr { border: none; border-top: 1px solid #e2ddd4; margin: 2.4rem 0; }
.byline { color: #666; font-style: italic; margin-top: -1rem; }
@media (prefers-color-scheme: dark) {
  body { background: #1b1b1d; color: #e6e3dd; }
  h1, h2, h3 { color: #f4f1ea; }
  h2 { border-bottom-color: #3a3833; }
  a { color: #7db1ff; }
  strong { color: #fff; }
  blockquote { background: #2a2410; border-left-color: #b98d2e; color: #e0cf9c; }
  table { background: #232326; }
  th, td { border-color: #3a3833; }
  thead th { background: #2c2b27; }
  tbody tr:nth-child(even) { background: #202023; }
  code, pre { background: #2a2a2d; }
}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{style}</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""


def build() -> Path:
    text = SRC.read_text(encoding="utf-8")
    html_body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "toc", "attr_list"],
    )
    OUT.write_text(
        TEMPLATE.format(title=TITLE, style=STYLE, body=html_body), encoding="utf-8"
    )
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"Wrote {out}")
