"""One reading of a results directory, for everything that quotes numbers.

The report builds its tables straight from the lane files, which is fine for
one page. The dashboard, the history line and the delta all need the same
per-format summary, and three separate readings of the same JSON is how the
three start disagreeing. They all come through here.

Nothing in this file measures anything. It only counts what a lane already
decided, so it can run without pandoc.
"""
import json
import pathlib

import severity
from probes import PROBES
from verdicts import LANES

# The AST serializations and the Carve bridge lanes are not comparable rows in
# a "how much survives" chart: json/xml are lossless by construction, and the
# Carve rows come from a different measurement program (results/carve.json).
NOT_A_FORMAT = {"json", "xml"}

# A metadata key is not a probe, so severity has no opinion on it. Counting one
# as structure keeps the weighted totals from ignoring metadata entirely,
# without pretending a lost title is the same class of event as a lost table.
META_WEIGHT = 2

MKEYS = ["title", "subtitle", "author", "date", "abstract", "keywords",
         "lang", "custom", "nested", "flag"]


def load_lane(d, lane):
    p = pathlib.Path(d) / LANES[lane]["file"]
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_run(d):
    p = pathlib.Path(d) / "run.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def count(row, want):
    return sum(1 for n in PROBES if row.get(n) == want) if row else 0


def meta_score(row):
    """Metadata keys recovered, half credit for partial. None when the format
    could not be measured at all."""
    if not row or "_err" in row:
        return None
    return (sum(1 for k in MKEYS if row.get(k) == "exact")
            + 0.5 * sum(1 for k in MKEYS if row.get(k) == "partial"))


def rows(d):
    """Per-format summary for every writer in the results set."""
    W = load_lane(d, "matrix") or {}
    RT = load_lane(d, "roundtrip") or {}
    EX = load_lane(d, "exact") or {}
    MT = load_lane(d, "meta") or {}

    out = {}
    for fmt in sorted(W):
        if fmt in NOT_A_FORMAT:
            continue
        w, rt, ex = W.get(fmt, {}), RT.get(fmt, {}), EX.get(fmt, {})
        exact = {n for n in PROBES if ex.get(n) == "exact"}
        canon = {n for n in PROBES if ex.get(n) == "canonical"}
        out[fmt] = {
            "expressed": count(w, "diff"),
            "writer_err": count(w, "err"),
            "readable": fmt in EX,
            "roundtrip": count(rt, "diff") if fmt in RT else None,
            "exact": len(exact),
            "canonical": len(canon),
            "lossy": count(ex, "lossy") if fmt in EX else None,
            "exact_err": count(ex, "err") if fmt in EX else None,
            "meta": meta_score(MT.get(fmt)),
            # Weighted by what a reader loses, not by probe count. The first
            # is strict; the second forgives the writer's restyling, which is
            # what "did the content come home" actually asks.
            "semantic_exact": severity.score(exact) if fmt in EX else None,
            "semantic_content": severity.score(exact | canon) if fmt in EX else None,
        }
    return out


def aggregate(rws):
    """The handful of numbers a history line carries.

    Medians, not means: a couple of formats that cannot be measured on this
    machine (pdf needs a TeX engine) would drag a mean around and make the
    trend line report the machine instead of pandoc.
    """
    def median(xs):
        xs = sorted(x for x in xs if x is not None)
        if not xs:
            return None
        m = len(xs) // 2
        return xs[m] if len(xs) % 2 else round((xs[m - 1] + xs[m]) / 2, 1)

    readable = [r for r in rws.values() if r["readable"]]
    return {
        "formats": len(rws),
        "readable": len(readable),
        "expressed_median": median([r["expressed"] for r in rws.values()]),
        "exact_median": median([r["exact"] for r in readable]),
        "roundtrip_median": median([r["roundtrip"] for r in readable]),
        "meta_median": median([r["meta"] for r in readable]),
        "semantic_pct_median": median(
            [r["semantic_content"]["pct"] for r in readable]),
    }


def read(d):
    """Everything the dashboard and the history line need from one directory."""
    rws = rows(d)
    return {"dir": str(d), "run": load_run(d), "rows": rws,
            "totals": aggregate(rws), "probes": len(PROBES),
            "severity": severity.totals()}
