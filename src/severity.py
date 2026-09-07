"""How much a reader loses when a probe does not survive.

The grid counts probes, and a count treats every probe alike: a format that
drops the width of a table column scores the same loss as one that drops a
footnote's text. Those are not the same failure, so this file weights them.

The question each probe is asked is not "how hard is this to support" but
**what is missing from the page when it is gone**:

    content       3  text or a referent is gone, and nothing left on the page
                     says so. A dropped footnote body, a link's URL, a raw
                     payload. The reader cannot reconstruct it.
    structure     2  every character survives, the document's shape does not.
                     A heading reads as a paragraph, a table as prose, a
                     definition list as bullets. Humans usually cope; anything
                     consuming the document does not.
    presentation  1  characters and shape both survive; styling, a hint, or a
                     measurement is gone. Emphasis, a column's alignment, a
                     link title.

Two judgement calls are worth stating, because they are the ones a reader is
most likely to disagree with:

  - `strikeout` and the scripts are structure, not presentation. The text
    survives, but what survives asserts something else: struck text reads as
    current, and `x^2` flattened to `x2` is a different number.
  - `table_caption`, `table_foot` and `figure` are content, because their
    degraded side has no caption or footer row at all. A `same` verdict there
    means those words were never written, not that they were restyled.

The severity of a probe is a property of the probe, so it lives next to no
particular lane. Every probe must appear below: `check()` fails otherwise, so
adding a probe forces the decision rather than defaulting it.
"""
from probes import PROBES

WEIGHT = {"content": 3, "structure": 2, "presentation": 1}
CLASSES = ["content", "structure", "presentation"]

SEVERITY = {
    # -- content: the words or the referent are gone -------------------------
    "math_inline": "content",          # a formula flattened to prose is not the formula
    "link": "content",                 # the URL has nowhere else to live
    "image": "content",
    "note": "content",                 # the footnote body, not the marker
    "cite": "content",
    "figure": "content",               # the degraded side carries no caption
    "table_caption": "content",
    "table_foot": "content",           # the footer row's cells, likewise
    "rawinline_html": "content",
    "rawinline_tex": "content",
    "rawblock_html": "content",
    "rawblock_tex": "content",

    # -- structure: every character survives, the shape does not -------------
    "strikeout": "structure",          # struck text that survives unstruck asserts the opposite
    "superscript": "structure",
    "subscript": "structure",
    "quoted_double": "structure",
    "quoted_single": "structure",
    "code_inline": "structure",
    "math_display": "structure",       # the formula survives, its display position does not
    "linebreak": "structure",
    "span_attrs": "structure",         # an id is a link target
    "div_attrs": "structure",
    "header": "structure",
    "header_level": "structure",
    "blockquote": "structure",
    "codeblock": "structure",
    "lineblock": "structure",
    "bulletlist": "structure",
    "orderedlist": "structure",
    "ol_start": "structure",           # renumbering shows the reader wrong numbers
    "list_nested": "structure",
    "deflist": "structure",
    "table": "structure",
    "table_head": "structure",
    "table_colspan": "structure",
    "table_rowspan": "structure",
    "table_block_cell": "structure",   # the cell's paragraph split
    "table_rowheadcols": "structure",
    "table_multibody": "structure",

    # -- presentation: styling, a hint, a measurement ------------------------
    "emph": "presentation",
    "strong": "presentation",
    "underline": "presentation",
    "smallcaps": "presentation",
    "softbreak": "presentation",       # source wrapping; nothing rendered moves
    "hrule": "presentation",           # carries no text and contains nothing
    "code_inline_attrs": "presentation",
    "link_title": "presentation",
    "link_attrs": "presentation",
    "image_title": "presentation",
    "image_size": "presentation",
    "header_attrs": "presentation",    # the id is on both sides; the delta is class and kv
    "codeblock_lang": "presentation",
    "codeblock_attrs": "presentation",
    "figure_attrs": "presentation",
    "ol_style_roman": "presentation",
    "ol_style_alpha": "presentation",
    "ol_delim_paren": "presentation",
    "ol_example": "presentation",
    "list_loose": "presentation",
    "table_align": "presentation",
    "table_colwidth": "presentation",
    "table_attrs": "presentation",
    "table_attrs_nocaption": "presentation",
    "table_cell_attrs": "presentation",
    "table_cell_align": "presentation",
    "table_row_attrs": "presentation",
}


def check():
    """Every probe classified, and nothing classified that is not a probe."""
    missing = sorted(set(PROBES) - set(SEVERITY))
    extra = sorted(set(SEVERITY) - set(PROBES))
    bad = sorted(n for n, s in SEVERITY.items() if s not in WEIGHT)
    problems = []
    if missing:
        problems.append("unclassified probes: " + ", ".join(missing))
    if extra:
        problems.append("classified but not a probe: " + ", ".join(extra))
    if bad:
        problems.append("unknown severity class: " + ", ".join(bad))
    return problems


def weight(probe):
    return WEIGHT[SEVERITY[probe]]


def totals():
    """Probe count and total weight per class, and overall."""
    out = {c: {"probes": 0, "weight": 0} for c in CLASSES}
    for n in PROBES:
        c = SEVERITY[n]
        out[c]["probes"] += 1
        out[c]["weight"] += WEIGHT[c]
    out["all"] = {"probes": len(PROBES),
                  "weight": sum(v["weight"] for v in out.values())}
    return out


def score(kept):
    """Weighted fidelity for a set of probe names that came back intact.

    Returns the kept weight, the total, the percentage, and the per-class
    breakdown - the breakdown is the point, since two formats can reach the
    same percentage by losing very different things.
    """
    t = totals()
    by = {c: {"kept": 0, "probes": t[c]["probes"],
              "weight": 0, "total": t[c]["weight"]} for c in CLASSES}
    for n in PROBES:
        if n in kept:
            c = SEVERITY[n]
            by[c]["kept"] += 1
            by[c]["weight"] += WEIGHT[c]
    got = sum(by[c]["weight"] for c in CLASSES)
    tot = t["all"]["weight"]
    return {"weight": got, "total": tot,
            "pct": round(100 * got / tot, 1) if tot else 0.0, "by": by}


if __name__ == "__main__":
    problems = check()
    if problems:
        raise SystemExit("severity: " + "; ".join(problems))
    t = totals()
    for c in CLASSES:
        print("%-13s %2d probes  weight %3d" % (c, t[c]["probes"], t[c]["weight"]))
    print("%-13s %2d probes  weight %3d" % ("all", t["all"]["probes"], t["all"]["weight"]))
