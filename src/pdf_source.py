"""Prepare a report copy whose PDF navigation survives outside this checkout."""

from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
source = (DOCS / "index.html").read_text(encoding="utf-8")
link = '<a href="dashboard.html">Dashboard</a>'
assert source.count(link) == 1, "report dashboard link changed"
source = source.replace(
    link,
    '<a href="https://markup-carve.github.io/pandoc-format-fidelity/dashboard.html">Dashboard</a>',
)
(DOCS / "_pdf-index.html").write_text(source, encoding="utf-8")
