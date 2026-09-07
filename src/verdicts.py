"""The one place that says which verdicts a lane produces and how they rank.

Every lane writes a per-format, per-probe verdict string. Two things need those
strings ordered: the delta (did a cell get better or worse between two runs?)
and the dashboard (how far from ideal is a format?). Ordering them twice would
let the two drift, so they are ordered here.

A rank is an ordinal, not a score. Higher is more fidelity; the distance
between two ranks means nothing.

    err   ranks below every substantive verdict on purpose. A conversion that
          fails is not the same as a conversion that succeeds and drops the
          feature, and it is worse: nothing came out at all.
"""

LANES = {
    "matrix": {
        "file": "matrix.json",
        "title": "writer",
        "rank": {"err": 0, "same": 1, "diff": 2},
        "ideal": "diff",
    },
    "roundtrip": {
        "file": "roundtrip.json",
        "title": "round-trip",
        "rank": {"err": 0, "same": 1, "diff": 2},
        "ideal": "diff",
    },
    "exact": {
        "file": "exact.json",
        "title": "exact",
        "rank": {"err": 0, "lossy": 1, "canonical": 2, "exact": 3},
        "ideal": "exact",
    },
    "meta": {
        "file": "meta.json",
        "title": "metadata",
        "rank": {"lost": 0, "partial": 1, "exact": 2},
        "ideal": "exact",
    },
    # Opt-in (`make carve-rt`), and shaped differently: its rows are the
    # bridge and each export format, its columns the Carve fixtures. The
    # ranking has one more step than the pandoc exact lane because it can tell
    # a respelling from a loss - see src/run_carve_rt.mjs.
    "carve_rt": {
        "file": "carve-rt.json",
        "title": "carve round-trip",
        "rank": {"err": 0, "unparsable": 1, "lossy": 2, "respelled": 3,
                 "equivalent": 4, "exact": 5},
        "ideal": "exact",
        "nested": "lanes",
        "optional": True,
    },
}

# Keys a lane file carries that are not probe verdicts.
NOT_A_VERDICT = {"_errs", "_err"}


def rank(lane, verdict):
    """Ordinal for a verdict, or None when the lane has never produced it.

    None is not zero: an unknown verdict is a reason to look, and scoring it as
    the worst case would silently invent a regression.
    """
    return LANES[lane]["rank"].get(verdict)


def direction(lane, before, after):
    """'better', 'worse', 'same', or 'unknown' when either side is unrankable."""
    a, b = rank(lane, before), rank(lane, after)
    if a is None or b is None:
        return "unknown"
    if b > a:
        return "better"
    if b < a:
        return "worse"
    return "same"


def cells(data, lane):
    """(format, probe, verdict) for every real cell in a loaded lane file.

    A nested lane keeps its grid under one key and everything else in the file
    is provenance, so it is read from there rather than from the top level.
    """
    nest = LANES[lane].get("nested")
    if nest:
        data = data.get(nest, {})
    for fmt, row in data.items():
        if not isinstance(row, dict):
            continue
        for probe, verdict in row.items():
            if probe in NOT_A_VERDICT:
                continue
            yield fmt, probe, verdict
