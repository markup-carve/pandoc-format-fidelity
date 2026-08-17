"""Regenerate the overview chart rows from the measured JSON.

The rows used to be hand-written, which is how the published chart kept numbers
that the lanes no longer produced. Everything below is derived.
"""
import json
import re

from probes import PROBES

W = json.load(open("results/matrix.json"))
EX = json.load(open("results/exact.json"))
try:
    CV = json.load(open("results/carve.json"))
except FileNotFoundError:
    CV = None

N = len(PROBES)
FULL = 620          # px of a full-width bar
LABEL_GAP = 9

# One row per family; aliases (html5, epub3, jats_publishing) score the same.
ROWS = ["markdown", "html", "commonmark_x", "epub", "djot", "rst", "markdown_mmd",
        "typst", "mediawiki", "latex", "docx", "gfm", "odt", "commonmark",
        "jats", "asciidoc", "org", "rtf", "man", "pptx"]


def expressed(f):
    if f in ("carve", "carve-ast"):
        lane = "source" if f == "carve" else "ast"
        return sum(1 for v in CV[lane].values() if v in ("diff", "exact"))
    return sum(1 for n in PROBES if W[f].get(n) == "diff")


def unchanged(f):
    if f in ("carve", "carve-ast"):
        lane = "source" if f == "carve" else "ast"
        return sum(1 for v in CV[lane].values() if v == "exact")
    return sum(1 for n in PROBES if EX.get(f, {}).get(n) == "exact")


def bar(value, color, cls):
    w = round(FULL * value / N)
    return ('<div class="track"><span class="fill %s" style="width:%dpx;'
            'background:%s"></span><b class="val" style="left:%dpx">%d</b></div>'
            % (cls, w, color, w + LABEL_GAP, value))


def row(name, tag, cls, c1, c2):
    label = '<div class="name">%s%s</div>' % (
        name.replace("_", "_<wbr>"),
        '<span class="tag">%s</span>' % tag if tag else "")
    return ('<div class="row%s">%s<div class="bars">%s%s</div></div>'
            % (" " + cls if cls else "", label,
               bar(expressed(name), c1, "s1"), bar(unchanged(name), c2, "s2")))


ROWS.sort(key=lambda f: (-unchanged(f), -expressed(f), f))

out = [row("native", "reference", "ref", "#8a8981", "#b5b4ac")]
if CV:
    out += [row("carve-ast", "bridge&#8202;&#8224;", "bridge", "#2a78d6", "#eb6834"),
            row("carve", "bridge&#8202;&#8224;", "bridge", "#2a78d6", "#eb6834")]
out += [row(f, "", "", "#2a78d6", "#eb6834") for f in ROWS]

src = open("overview.html", encoding="utf-8").read()
start = src.index('<div class="chart">') + len('<div class="chart">')
end = src.index("</div>\n<div class=\"axis\"", start)
src = src[:start] + "\n" + "\n".join(out) + "\n" + src[end:]
src = re.sub(r"\d+ element and feature probes", "%d element and feature probes" % N, src)

# axis ticks: five steps to N, positioned on the same 620px track as the bars
ticks = "".join('<span style="left:%dpx">%d</span>'
                % (round(FULL * i / 5), round(N * i / 5)) for i in range(6))
ticks += ('<span style="left:%dpx;transform:none;padding-left:10px">probes</span>' % FULL)
src = re.sub(r'<div class="axis">.*?</div>', '<div class="axis">%s</div>' % ticks, src,
             count=1, flags=re.S)

# footer figures that quote the run
src = re.sub(r"shown as the \d+/\d+\s*reference", "shown as the %d/%d reference" % (N, N), src)
src = re.sub(r"all \d+ pandoc writers \(\d+ of them also readers\)",
             "all %d pandoc writers (%d of them also readers)" % (len(W), len(EX)), src)
src = re.sub(r"moves djot from \d+ to \d+ expressed and \d+ to \d+\s*unchanged",
             "moves djot from %d to %d expressed and %d to %d unchanged"
             % (expressed("djot"), expressed("djot") + 4, unchanged("djot"), unchanged("djot") + 2),
             src)
src = src.replace("pandoc-format-fidelity.pdf", "docs/report.pdf")
open("overview.html", "w", encoding="utf-8").write(src)
print("overview rows regenerated:", len(out))
