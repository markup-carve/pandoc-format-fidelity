# pandoc-format-fidelity

How much of a document survives a pandoc conversion, measured rather than guessed.

Each probe is a pair of pandoc ASTs differing in exactly one feature, run through
every writer pandoc ships and read back by every reader. The output is a grid saying,
per format and per feature, whether the format can express it at all and whether it
comes home unchanged.

![Per format: how many probes the writer can express, and how many read back unchanged](docs/overview.png)

Report: [`docs/index.html`](docs/index.html) · [`docs/report.pdf`](docs/report.pdf)

## The method

Each probe is a **pair** of ASTs - a `rich` one that uses a feature and a `degraded`
one that does not - and the question is what pandoc does with the two of them:

| lane | question | verdicts |
|---|---|---|
| writer (`src/run_matrix.py`) | is `write(rich)` byte-identical to `write(degraded)`? | `diff` = expressed, `same` = cannot express |
| round-trip (`src/run_roundtrip.py`) | is `read(write(rich))` the same AST as `read(write(degraded))`? | `diff` = survives, `same` = lost |
| exact (`src/run_exact.py`) | does `read(write(rich))` equal `rich`? | `exact` / `canonical` / `lossy` |
| metadata (`src/run_meta.py`) | which of ten metadata shapes survive standalone? | `exact` / `partial` / `lost` |

**The first two lanes never compare anything against the input.** Both sides go
through the same writer with the same options, so whatever canonical styling that
writer applies lands on both and cancels. A `same` verdict means pandoc emitted
literally the same bytes for two different ASTs. Input formatting cannot produce that.

**The exact lane is the one where canonicalization matters**, so it reports three
verdicts instead of two. `canonical` means the content came back but the writer
restyled it. What gets folded is listed in `common.canonical()` and is deliberately
short:

- `AlignLeft` == `AlignDefault` - a default-aligned column renders left
- a measured `ColWidth` == `ColWidthDefault` - the number is the writer's arithmetic
- raw `tex` == raw `latex` - alias for one target
- header ids invented by `--auto_identifiers` are dropped

Counting those as loss overstates pandoc's markdown by eleven probes. Counting
them as exact would hide real precision loss, like a column width rounded to the grid.
Hence a column each.

Two settings are load-bearing and were both bugs before they were settings:

- `--wrap=preserve` on every writer. Without it a wrapping writer turns a `SoftBreak`
  into a space and the probe reads as "cannot express" a distinction the format
  handles fine.
- `--resource-path=fixtures` on every writer, and the same image handed to
  `pandoc server` in the request. An image pandoc cannot resolve makes epub leave the
  src untouched, which round-trips to a **false** `exact`; when it resolves, epub
  embeds it and rewrites the src to `media/file0.png`, which is the honest answer.

## Running it

```
make          # fetch the pinned pandoc, run every lane, rebuild the report
make lanes    # just the measurements
make report   # just the HTML from existing results/
make check    # sanity checks
make controls # the two controls the report quotes (see src/controls.py)
```

`make controls` is not part of the grid. It checks that the writer lane's comparison
means what the report claims: every writer is asked to emit the same document twice
(75 of 76 are byte-identical; `pdf` errors, so it cannot be checked), and the
`--wrap=preserve` effect is counted on the `softbreak` probe.

Requires python3, node (only for the Carve lanes) and curl. The pinned pandoc is
fetched into `vendor/` by `scripts/fetch-pandoc.sh`; nothing is installed globally.
Results are committed under `results/`, so a rerun shows up as a reviewable diff.

To measure a different pandoc:

```
PANDOC_VERSION=3.11 ./scripts/fetch-pandoc.sh && make lanes report
PANDOC=/path/to/pandoc make lanes report      # e.g. a nightly build
```

## Which formats are in the round-trip lanes

Formats pandoc can both write and read, minus (see `src/formats.py`):

- `biblatex`, `bibtex`, `csljson` - bibliography databases, so a probe about tables
  says nothing about them
- `json`, `xml` - pandoc's own AST serializations, lossless by construction, and
  `native` already sits in the chart as the reference row

## Carve

`carve` and `carve-ast` are **not** pandoc formats. They are the two lanes of the
[pandoc-carve](https://github.com/markup-carve/pandoc-carve) bridge, put through the
identical probes, and they are **opt-in** - `make` alone produces a pandoc-only grid:

```
make carve CARVE_BRIDGE=../pandoc-carve/dist/index.js
```

## Caveats

- A `diff` in the writer lane means the format distinguishes the two documents, not
  that it distinguishes them *well*. Escaping to raw HTML counts.
- Some cells are genuine pandoc round-trip errors rather than losses. Three are
  isolated: `muse` writes a header id its own reader rejects, and `typst` emits a
  heading its own reader rejects. `opml` is the bulk of them - its reader rejects 64
  of the 66 probes, because it serializes a heading outline and not a document.
- `pdf` reads 0 everywhere because the writer needs an external TeX engine that is not
  installed here, so every pdf conversion errors. That row measures this machine, not
  the format.
- The probe set covers single features in isolation. Interactions between them are
  not measured.
