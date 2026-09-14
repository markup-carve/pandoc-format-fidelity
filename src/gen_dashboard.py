"""Build docs/dashboard.html: one dated reading of the results directory.

The report answers "what does pandoc do". The dashboard answers "what did this
run do, and how does it differ from the last one" - which needs three things
the report never carried: the pandoc that produced the numbers, the date, and
the movement since a baseline.

Reads results/ only. No pandoc, no network, so it can be rebuilt from a
checkout at any point and still be honest about what it is describing: if
results/run.json says the numbers came from a nightly, the page says so.
"""
import html
import json
import pathlib

import scoreboard
import severity
from verdicts import LANES

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
TEMPLATE = ROOT / "resources" / "dashboard.html"
THEME = ROOT / "resources" / "theme.css"
THRESHOLDS = ROOT / "thresholds.json"
OUT = ROOT / "docs" / "dashboard.html"

CLASS_COLS = ["content", "structure", "presentation"]

# A release that changes one writer's defaults moves hundreds of cells. Past
# this the table stops being readable; results/delta.json keeps all of them.
MAX_DELTA_ROWS = 200


def esc(x):
    return html.escape(str(x), quote=False)


def read_json(path, default=None):
    p = pathlib.Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def read_history(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    out = []
    for i, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            # A half-written line is worth saying out loud rather than
            # silently shortening the trend.
            out.append({"date": "unreadable line %d" % i})
    return out


def bar(v, mx, cls="ok"):
    if v is None:
        return '<span class="dim">-</span>'
    pct = 0 if not mx else round(100 * v / mx)
    txt = ("%g" % v) if isinstance(v, float) else str(v)
    return ('<span class="cell-bar %s" style="--p:%d%%"><i></i><b>%s</b></span>'
            % (cls, pct, txt))


def band(v, mx, good=0.8, fair=0.5):
    if not mx:
        return "ok"
    r = v / mx
    return "ok" if r >= good else ("mid" if r >= fair else "low")


def table_scores(board):
    rws = board["rows"]
    n = board["probes"]
    readable = {f: r for f, r in rws.items() if r["readable"]}
    order = sorted(readable, key=lambda f: (-readable[f]["semantic_content"]["pct"], f))

    out = ['<table class="grid"><thead><tr><th class="l">format</th>'
           '<th>expressed<span>/%d</span></th>'
           '<th>round&#8209;trip<span>/%d</span></th>'
           '<th>exact<span>/%d</span></th><th>canon.<span>/%d</span></th>'
           '<th>meta<span>/10</span></th>'
           '<th>semantic</th>' % (n, n, n, n)]
    t = board["severity"]
    for c in CLASS_COLS:
        out.append('<th>%s<span>/%d</span></th>' % (c, t[c]["probes"]))
    out.append("</tr></thead><tbody>")

    for f in order:
        r = readable[f]
        sem = r["semantic_content"]
        out.append('<tr><td class="l fmt">%s</td>' % esc(f))
        out.append("<td>%s</td>" % bar(r["expressed"], n, band(r["expressed"], n)))
        out.append("<td>%s</td>" % bar(r["roundtrip"], n, "mid"))
        out.append("<td>%s</td>" % bar(r["exact"], n, band(r["exact"], n, .6, .35)))
        out.append("<td>%s</td>" % (bar(r["canonical"], n, "mid") if r["canonical"]
                                    else '<span class="dim">-</span>'))
        out.append("<td>%s</td>" % bar(r["meta"], 10, band(r["meta"] or 0, 10)))
        out.append('<td>%s</td>' % bar(sem["pct"], 100, band(sem["pct"], 100, .75, .45)))
        for c in CLASS_COLS:
            k = sem["by"][c]
            out.append("<td>%s</td>" % bar(k["kept"], k["probes"],
                                           band(k["kept"], k["probes"], 1.0, .5)))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def table_delta(delta):
    if not delta:
        return ('<p class="empty">No delta recorded. Run '
                '<code>make delta BASELINE=&lt;dir&gt;</code> to compare this results '
                'set against another one.</p>')
    rows = [c for c in delta["changes"] if c["direction"] in ("worse", "better")]
    order = {"worse": 0, "better": 1}
    rows.sort(key=lambda c: (order[c["direction"]], -c["weight"], c["lane"],
                             c["format"], c["probe"]))
    head = ('<p class="small dim">%s against %s, profile <code>%s</code>.</p>'
            % (esc(side_label(delta["candidate"])),
               esc(side_label(delta["baseline"])),
               esc(delta["thresholds"].get("profile", "?"))))
    out = [head]
    # A table of nothing but headers reads as a broken page. When no cell
    # moved, say so - the structural note below still gets its line.
    if not rows:
        out.append('<p class="empty">Every cell held its verdict.</p>')
    hidden = max(0, len(rows) - MAX_DELTA_ROWS)
    if rows:
        out.append('<div class="scroll"><table class="grid"><thead><tr>'
                   '<th class="l">&nbsp;</th><th class="l">lane</th>'
                   '<th class="l">format</th><th class="l">probe</th>'
                   '<th class="l">from</th><th class="l">to</th>'
                   '<th class="l">severity</th></tr></thead><tbody>')
    for c in rows[:MAX_DELTA_ROWS]:
        worse = c["direction"] == "worse"
        out.append('<tr><td class="l"><span class="badge %s">%s</span></td>'
                   '<td class="l dim">%s</td><td class="l fmt">%s</td>'
                   '<td class="l fmt">%s</td><td class="l dim">%s</td>'
                   '<td class="l fmt"><b>%s</b></td>'
                   '<td class="l"><span class="sev %s">%s</span></td></tr>'
                   % ("bad" if worse else "ok", "worse" if worse else "better",
                      esc(c["lane"]), esc(c["format"]), esc(c["probe"]),
                      esc(c["from"]), esc(c["to"]),
                      esc(c["class"]), esc(c["class"])))
    if rows:
        out.append("</tbody></table></div>")
    if hidden:
        out.append('<p class="small dim">%d further row(s) not shown; '
                   '<code>results/delta.json</code> has the full list.</p>' % hidden)
    if delta["exempt"]:
        out.append('<p class="small dim">%d exempt cell(s), see '
                   '<code>thresholds.json</code>: %s</p>'
                   % (len(delta["exempt"]),
                      esc(", ".join(sorted({c["format"] for c in delta["exempt"]})))))
    if delta["structural"]:
        out.append('<p class="small dim">%d structural change(s) - a probe or format '
                   'appeared or disappeared, which is not scored as movement.</p>'
                   % len(delta["structural"]))
    return "".join(out)


def side_label(side):
    r = side.get("run") or {}
    p = r.get("pandoc") or {}
    return "pandoc %s of %s" % (p.get("version", "?"), r.get("date", "an unrecorded run"))


def sparkline(points, width=640, height=64):
    """A trend needs at least two readings; one point is a dot, not a line."""
    vals = [p for p in points if p is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = width / (len(points) - 1)
    xy = []
    for i, v in enumerate(points):
        if v is None:
            continue
        y = height - 6 - (height - 12) * (v - lo) / span
        xy.append("%.1f,%.1f" % (i * step, y))
    return ('<svg class="spark" viewBox="0 0 %d %d" preserveAspectRatio="none" '
            'role="img" aria-label="median semantic fidelity over %d runs">'
            '<polyline fill="none" stroke="currentColor" stroke-width="2" '
            'points="%s"/></svg>' % (width, height, len(vals), " ".join(xy)))


def table_history(history):
    if not history:
        return ('<p class="empty">No history yet. '
                '<code>src/delta.py --record results/history.jsonl</code> appends one '
                'line per run.</p>')
    out = []
    pts = [h.get("totals", {}).get("semantic_pct_median") for h in history]
    spark = sparkline(pts)
    if spark:
        out.append('<div style="color:var(--accent)">%s</div>' % spark)
    out.append('<div class="scroll"><table class="grid"><thead><tr>'
               '<th class="l">date</th><th class="l">pandoc</th>'
               '<th>expressed</th><th>exact</th><th>meta</th><th>semantic</th>'
               '<th>regressions</th><th class="l">status</th>'
               '</tr></thead><tbody>')
    for h in reversed(history):
        t = h.get("totals", {})
        d = h.get("delta", {})
        status = d.get("status", "-")
        cls = {"ok": "ok", "breach": "bad"}.get(status, "warn")
        out.append('<tr><td class="l fmt">%s</td><td class="l dim">%s%s</td>'
                   '<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                   '<td class="l"><span class="badge %s">%s</span></td></tr>'
                   % (esc(h.get("date", "?")), esc(h.get("pandoc", "?")),
                      "" if h.get("is_pin", True) else " (nightly)",
                      esc(t.get("expressed_median", "-")),
                      esc(t.get("exact_median", "-")),
                      esc(t.get("meta_median", "-")),
                      esc(t.get("semantic_pct_median", "-")),
                      esc(d.get("regressions", "-")), cls, esc(status)))
    out.append("</tbody></table></div>")
    return "".join(out)


def table_thresholds(doc):
    out = ['<table class="grid"><thead><tr><th class="l">profile</th>'
           '<th>max regressions</th><th>per lane</th><th>per class</th>'
           '<th>max weight</th><th class="l">what it is for</th>'
           '</tr></thead><tbody>']
    for name, prof in doc.get("profiles", {}).items():
        caps = prof.get("max_regressions", {})
        per_lane = ", ".join("%s %d" % (k, v) for k, v in sorted(caps.items())
                             if k in LANES) or "-"
        per_class = ", ".join("%s %d" % (k, v) for k, v in
                              sorted(prof.get("max_regressions_by_class", {}).items())) or "-"
        out.append('<tr><td class="l fmt">%s</td><td>%s</td>'
                   '<td class="l dim small">%s</td><td class="l dim small">%s</td>'
                   '<td>%s</td><td class="l dim small wrap">%s</td></tr>'
                   % (esc(name), esc(caps.get("total", "-")), esc(per_lane),
                      esc(per_class), esc(prof.get("max_regression_weight", "-")),
                      esc(prof.get("description", ""))))
    out.append("</tbody></table>")
    for rule in doc.get("allow", []):
        out.append('<p class="small dim">exempt: <code>%s</code> on the %s lane - %s</p>'
                   % (esc(rule.get("format", "*")), esc(rule.get("lane", "any")),
                      esc(rule.get("reason", "no reason given"))))
    return "".join(out)


CARVE_VERDICTS = ["exact", "equivalent", "respelled", "lossy", "unparsable", "err"]


def table_carve_rt(data):
    """The Carve lane reads the other way round: Carve source in, Carve out."""
    if not data:
        return ('<p class="empty">Not run. '
                '<code>make carve-rt CARVE_BRIDGE=&lt;path to dist/index.js&gt;</code> '
                'measures it; the lane is opt-in because it needs the bridge.</p>')
    lanes = data.get("lanes", {})
    total = len(data.get("fixtures", {}))
    order = ["bridge"] + [f for f in data.get("formats", []) if f in lanes]

    out = ['<p class="small dim">%d Carve fixtures &middot; renderer %s &middot; %s</p>'
           % (total, esc(data.get("renderer", "unreported")),
              esc(data.get("pandoc") or "pandoc unreported")),
           '<div class="scroll"><table class="grid"><thead><tr>'
           '<th class="l">export</th>']
    for v in CARVE_VERDICTS:
        out.append("<th>%s</th>" % v)
    out.append('<th>came back readable<span>/%d</span></th></tr></thead><tbody>' % total)

    for lane in order:
        row = lanes.get(lane, {})
        counts = {v: sum(1 for x in row.values() if x == v) for v in CARVE_VERDICTS}
        # exact, equivalent and respelled all render the same document; only
        # lossy and worse changed something a reader would see.
        kept = counts["exact"] + counts["equivalent"] + counts["respelled"]
        tr = '<tr class="hi">' if lane == "bridge" else "<tr>"
        out.append('%s<td class="l fmt">%s</td>' % (tr, esc(lane)))
        for v in CARVE_VERDICTS:
            cls = {"exact": "ok", "equivalent": "ok", "respelled": "mid"}.get(v, "low")
            out.append("<td>%s</td>"
                       % (bar(counts[v], total, cls) if counts[v]
                          else '<span class="dim">-</span>'))
        out.append("<td>%s</td></tr>" % bar(kept, total, band(kept, total)))
    out.append("</tbody></table></div>")

    changed = [(n, v) for n, v in sorted(lanes.get("bridge", {}).items())
               if v != "exact"]
    if changed:
        out.append('<p class="small dim">The bridge alone changes %d of them: %s.</p>'
                   % (len(changed),
                      ", ".join("<code>%s</code> (%s)" % (esc(n), esc(v))
                                for n, v in changed)))
    warnings = data.get("warnings", {})
    if warnings:
        out.append('<p class="small dim">The bridge says out loud what it dropped on '
                   '%s.</p>' % ", ".join("<code>%s</code>" % esc(n)
                                         for n in sorted(warnings)))
    return "".join(out)


def delta_status(delta, run):
    out = []
    pandoc = (run or {}).get("pandoc") or {}
    src = pandoc.get("source") or {}
    if src.get("stale_banner"):
        # The loudest thing on the page when it happens: every number below
        # describes a build whose identity is not settled.
        out.append('<span class="badge bad">build identity unsettled</span>')
        out.append('<span class="small dim">calls itself %s, came from a run '
                   'created %s</span>'
                   % (esc(src.get("names_itself", "?")), esc(src.get("date", "?"))))
    elif src:
        out.append('<span class="badge warn">from upstream run %s</span>'
                   % esc(src.get("run", "?")))
    if run and not pandoc.get("is_pin", True):
        out.append('<span class="badge warn">not the pinned pandoc</span>')
    if run and run.get("dirty"):
        out.append('<span class="badge warn">measured from a dirty checkout</span>')
    if not delta:
        out.append('<span class="badge warn">no delta recorded</span>')
        return "".join(out)
    t = delta["tally"]
    ok = delta["status"] == "ok"
    out.append('<span class="badge %s">%s</span>'
               % ("ok" if ok else "bad",
                  "within thresholds" if ok else "threshold breach"))
    out.append('<span class="badge %s">%d regressions</span>'
               % ("ok" if not t["regressions"] else "bad", t["regressions"]))
    if t["improvements"]:
        out.append('<span class="badge ok">%d improvements</span>' % t["improvements"])
    for b in delta["breaches"]:
        out.append('<span class="small dim">%s</span>' % esc(b))
    return "".join(out)


def main():
    # Before anything is written: a page built from an incomplete rubric would
    # publish scores with probes silently missing from the totals.
    problems = severity.check()
    if problems:
        raise SystemExit("severity: " + "; ".join(problems))
    board = scoreboard.read(RESULTS)
    run = board["run"]
    if run is None:
        raise SystemExit("results/run.json is missing - run `make stamp` (or `make "
                         "lanes`) so the dashboard can say which pandoc it describes")
    delta = read_json(RESULTS / "delta.json")
    carve_rt = read_json(RESULTS / "carve-rt.json")
    history = read_history(RESULTS / "history.jsonl")
    thresholds = read_json(THRESHOLDS, {})
    pandoc = run.get("pandoc") or {}

    fields = {
        "STYLE": THEME.read_text(encoding="utf-8"),
        "RUNDATE": run["date"][:10],
        "RUNTIME": run["date"],
        "PANDOCV": pandoc.get("version") or "unknown",
        "PINNOTE": "(the pin)" if pandoc.get("is_pin") else "(not the pin)",
        "COMMIT": (run.get("commit") or "an unrecorded commit")
                  + (" + uncommitted changes" if run.get("dirty") else ""),
        "PLATFORM": run.get("platform", "an unrecorded platform"),
        "NPROBE": str(board["probes"]),
        "NFORMATS": str(board["totals"]["readable"]),
        "SEMMEDIAN": str(board["totals"]["semantic_pct_median"]),
        "DELTASTATUS": delta_status(delta, run),
        "TDELTA": table_delta(delta),
        "TSCORE": table_scores(board),
        "TCARVERT": table_carve_rt(carve_rt),
        # Counted from the lane, never typed: the fixture set grows.
        "NCARVE": str(len((carve_rt or {}).get("fixtures", {})) or "the"),
        "NCARVEFMT": str(len((carve_rt or {}).get("formats", [])) or "the"),
        "THISTORY": table_history(history),
        "TTHRESH": table_thresholds(thresholds),
    }

    page = TEMPLATE.read_text(encoding="utf-8")
    for k, v in fields.items():
        page = page.replace("{{%s}}" % k, v)
    left = [k for k in fields if "{{%s}}" % k in page]
    if left:
        raise SystemExit("unsubstituted placeholders: %s" % ", ".join(left))
    OUT.write_text(page, encoding="utf-8")
    print("wrote docs/dashboard.html %d bytes (pandoc %s, %s)"
          % (len(page), fields["PANDOCV"], fields["RUNTIME"]))


if __name__ == "__main__":
    main()
