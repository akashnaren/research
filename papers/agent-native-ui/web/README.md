# Web ingest (Paper 1)

Profile Engineer ingest source of truth is the exact PDF:

[`../paper.pdf`](../paper.pdf)

Path: `papers/agent-native-ui/paper.pdf`

The github.io reader (https://akashnaren.github.io/research/) is a bare
reader of that PDF. Profile owns that site. Do not open pull requests on
`akashnaren.github.io` from this repository.

Editable scholarly source: [`../paper.md`](../paper.md). Rebuild HTML and PDF:

```bash
python papers/agent-native-ui/build.py
```

[`article.md`](article.md) is a pointer only. Do not ingest it as the paper.
