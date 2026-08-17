import json
from probes import PROBES

W = json.load(open("results/matrix.json"))
RT = json.load(open("results/roundtrip.json"))
EX = json.load(open("results/exact.json"))
MT = json.load(open("results/meta.json"))
try:
    CV = json.load(open("results/carve.json"))
except FileNotFoundError:      # the Carve lane is opt-in; the grid works without it
    CV = None

# Carve enters the matrix as two lanes of the pandoc-carve bridge.
CARVE = {"carve": "source", "carve-ast": "ast"} if CV else {}
for fmt, lane in CARVE.items():
    W[fmt] = {n: ("diff" if v in ("diff", "exact") else v) for n, v in CV[lane].items()}
    RT[fmt] = dict(CV["rt"][lane])
    EX[fmt] = {n: ("exact" if v == "exact" else "lossy") for n, v in CV[lane].items()}
    MT[fmt] = dict(CV["meta"][lane])

GROUPS = ["inline", "block", "list", "table", "attrs", "raw"]
BY = {}
for n, p in PROBES.items():
    BY.setdefault(p["group"], []).append(n)
TOT = {g: len(BY[g]) for g in GROUPS}
N = len(PROBES)
MKEYS = ["title", "subtitle", "author", "date", "abstract", "keywords",
         "lang", "custom", "nested", "flag"]

def wscore(f):
    return sum(1 for n in PROBES if W[f].get(n) == "diff")

def gscore(f, g):
    return sum(1 for n in BY[g] if W[f].get(n) == "diff")

def escore(f):
    return sum(1 for n in PROBES if EX.get(f, {}).get(n) == "exact")


def cscore(f):
    """kept the content but restyled it - see the canonical-equivalence list"""
    return sum(1 for n in PROBES if EX.get(f, {}).get(n) == "canonical")

def rscore(f):
    return sum(1 for n in PROBES if RT.get(f, {}).get(n) == "diff")

def mscore(f):
    v = MT.get(f)
    if not v or "_err" in v:
        return None
    return sum(1 for k in MKEYS if v[k] == "exact") + 0.5 * sum(1 for k in MKEYS if v[k] == "partial")

def bar(v, mx, cls="ok"):
    pct = 0 if not mx else round(100 * v / mx)
    txt = ("%g" % v) if isinstance(v, float) else str(v)
    return ('<span class="cell-bar %s" style="--p:%d%%"><i></i>'
            '<b>%s</b></span>' % (cls, pct, txt))

def table1():
    rows = sorted(W, key=lambda f: (-wscore(f), f))
    out = ['<table class="grid"><thead><tr><th class="l">writer</th>'
           '<th>total<span>/%d</span></th>' % N]
    for g in GROUPS:
        out.append('<th>%s<span>/%d</span></th>' % (g, TOT[g]))
    out.append('<th class="l">reader?</th></tr></thead><tbody>')
    for f in rows:
        rd = "yes" if f in RT else "-"
        tr = '<tr class="hi">' if f in CARVE else "<tr>"
        out.append('%s<td class="l fmt">%s</td><td>%s</td>' % (tr, f, bar(wscore(f), N)))
        for g in GROUPS:
            v = gscore(f, g)
            cls = "ok" if v == TOT[g] else ("mid" if v >= TOT[g] / 2 else "low")
            out.append('<td>%s</td>' % bar(v, TOT[g], cls))
        out.append('<td class="l dim">%s</td></tr>' % rd)
    out.append("</tbody></table>")
    return "".join(out)

def table2():
    fs = sorted(EX, key=lambda f: -escore(f))
    out = ['<table class="grid"><thead><tr><th class="l">format</th>'
           '<th>writer<span>/%d</span></th><th>round&#8209;trip<span>/%d</span></th>'
           '<th>exact<span>/%d</span></th><th>canon.<span>/%d</span></th>'
           '<th>metadata<span>/10</span></th>'
           '<th class="l">reader drops</th></tr></thead><tbody>' % (N, N, N, N)]
    for f in fs:
        m = mscore(f)
        mc = "-" if m is None else bar(m, 10, "ok" if m >= 8 else ("mid" if m >= 3 else "low"))
        lost = [n for n in PROBES if W[f].get(n) == "diff" and RT[f].get(n) == "same"]
        e = escore(f)
        tr = '<tr class="hi">' if f in CARVE else "<tr>"
        c = cscore(f)
        out.append('%s<td class="l fmt">%s</td><td>%s</td><td>%s</td><td>%s</td>'
                   '<td>%s</td><td>%s</td><td class="l dim small">%s</td></tr>'
                   % (tr, f, bar(wscore(f), N), bar(rscore(f), N, "mid"),
                      bar(e, N, "ok" if e > 35 else ("mid" if e > 20 else "low")),
                      bar(c, N, "mid") if c else '<span class="dim">-</span>',
                      mc, ", ".join(lost) if lost else "-"))
    out.append("</tbody></table>")
    return "".join(out)

DOT = {"exact": '<b class="dot ok" title="exact"></b>',
       "diff": '<b class="dot mid" title="expressed, but not recovered exactly"></b>',
       "same": '<b class="dot low" title="cannot be expressed"></b>'}

def table3():
    wf = [f for f in W if f not in ("json", "xml", "native") and f not in CARVE]
    ef = [f for f in EX if f != "native" and f not in CARVE]
    rows = []
    for n, p in PROBES.items():
        a = sum(1 for f in wf if W[f].get(n) == "diff")
        b = sum(1 for f in ef if EX[f].get(n) == "exact")
        rows.append((b, a, n, p["group"]))
    rows.sort()
    out = ['<table class="grid"><thead><tr><th class="l">element / feature</th>'
           '<th class="l">group</th><th>writers<span>/%d</span></th>'
           '<th>exact round&#8209;trip<span>/%d</span></th>'
           '<th>carve</th><th>carve&#8209;ast</th></tr></thead><tbody>'
           % (len(wf), len(ef))]
    for b, a, n, g in rows:
        cls = "low" if b <= 5 else ("mid" if b <= 15 else "ok")
        out.append('<tr><td class="l fmt">%s</td><td class="l dim">%s</td>'
                   '<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                   % (n, g, bar(a, len(wf), "mid"), bar(b, len(ef), cls),
                      DOT[CV["source"][n]], DOT[CV["ast"][n]]))
    out.append("</tbody></table>")
    return "".join(out)

def tcarve():
    fs = ["carve-ast", "carve", "html5", "markdown", "commonmark_x", "djot", "gfm"]
    out = ['<table class="grid"><thead><tr><th class="l">format</th>'
           '<th>expressed<span>/%d</span></th><th>exact<span>/%d</span></th>'
           '<th>meta<span>/10</span></th>' % (N, N)]
    for g in GROUPS:
        out.append('<th>%s<span>/%d</span></th>' % (g, TOT[g]))
    out.append("</tr></thead><tbody>")
    for f in fs:
        m = mscore(f)
        e = escore(f) if f in EX else 0
        tr = '<tr class="hi">' if f in CARVE else "<tr>"
        out.append('%s<td class="l fmt">%s</td><td>%s</td><td>%s</td><td>%s</td>'
                   % (tr, f, bar(wscore(f), N),
                      bar(e, N, "ok" if e > 45 else "mid"),
                      "-" if m is None else bar(m, 10, "ok" if m >= 8 else "mid")))
        for g in GROUPS:
            v = gscore(f, g)
            cls = "ok" if v == TOT[g] else ("mid" if v >= TOT[g] / 2 else "low")
            out.append("<td>%s</td>" % bar(v, TOT[g], cls))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)

def table4():
    out = ['<table class="grid"><thead><tr><th class="l">meta key</th>']
    fs = [f for f in MT if mscore(f) is not None]
    fs.sort(key=lambda f: -mscore(f))
    for f in fs:
        out.append('<th class="vert"><span>%s</span></th>' % f)
    out.append("</tr></thead><tbody>")
    sym = {"exact": ('<b class="dot ok" title="exact"></b>'),
           "partial": ('<b class="dot mid" title="partial"></b>'),
           "lost": ('<b class="dot low" title="lost"></b>')}
    for k in MKEYS:
        out.append('<tr><td class="l fmt">%s</td>' % k)
        for f in fs:
            out.append("<td>%s</td>" % sym[MT[f][k]])
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)

html = open("resources/template.html", encoding="utf-8").read()
for key, fn in [("T1", table1), ("T2", table2), ("T3", table3), ("T4", table4),
                ("TCARVE", tcarve)]:
    html = html.replace("{{%s}}" % key, fn())
# The Carve lanes were added to W and EX above, so they come back out: these are
# counts of pandoc's own writers and readers. Every count quoted in the prose goes
# through here - a hand-typed one drifts silently on the next rerun.
stats = {
    "NWRITE": str(len(W) - len(CARVE)),
    "NREAD": "51",
    "NPROBE": str(N),
    "NBOTH": str(len(EX) - len(CARVE)),
}
for k, v in stats.items():
    html = html.replace("{{%s}}" % k, v)
left = [k for k in ("T1", "T2", "T3", "T4", "TCARVE", *stats) if "{{%s}}" % k in html]
if left:
    raise SystemExit("unsubstituted placeholders: %s" % ", ".join(left))
open("docs/index.html", "w", encoding="utf-8").write(html)
print("wrote docs/index.html", len(html), "bytes")
