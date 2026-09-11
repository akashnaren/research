# Web export (Paper 1)

Profile Engineer renders [`article.md`](article.md) on
https://akashnaren.github.io/research/.

This file is the Medium-like reader export (title, dek, byline placeholder,
sections, figure paths). The scholarly source of truth is
[`../paper.md`](../paper.md).

Do not open pull requests on `akashnaren.github.io` from this repository.
Profile owns that site.

HTML and PDF of the manuscript are built separately:

```bash
python papers/agent-native-ui/build.py
```

That command does not overwrite `article.md`.
