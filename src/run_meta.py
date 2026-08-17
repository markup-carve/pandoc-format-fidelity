"""Metadata lane: which of ten metadata shapes survive a standalone round trip."""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from probes import API

from common import PANDOC, WRITE_OPTS
FMTS = sys.argv[1].split(",") if len(sys.argv) > 1 else []

def mi(s):
    return {"t": "MetaInlines", "c": [{"t": "Str", "c": s}]}

META = {
    "title": mi("Tee"),
    "subtitle": mi("Sub"),
    "author": {"t": "MetaList", "c": [mi("Ann"), mi("Bob")]},
    "date": mi("2020-01-02"),
    "abstract": {"t": "MetaBlocks",
                 "c": [{"t": "Para", "c": [{"t": "Str", "c": "Abs"}]}]},
    "keywords": {"t": "MetaList", "c": [mi("kw1"), mi("kw2")]},
    "lang": mi("de"),
    "custom": mi("Cust"),
    "nested": {"t": "MetaMap", "c": {"inner": mi("Deep")}},
    "flag": {"t": "MetaBool", "c": True},
}
BLOCKS = [{"t": "Para", "c": [{"t": "Str", "c": "body"}]}]

def flat(v):
    """render a Meta value to comparable plain text"""
    return json.dumps(v, sort_keys=True)

def work(f):
    doc = json.dumps({"pandoc-api-version": API, "meta": META,
                      "blocks": BLOCKS}).encode()
    a = subprocess.run([PANDOC, "-f", "json", "-t", f, "-s", "-o", "-"] + WRITE_OPTS,
                       input=doc, capture_output=True)
    if a.returncode != 0:
        return (f, {"_err": a.stderr[:120].decode("utf8", "replace")})
    b = subprocess.run([PANDOC, "-f", f, "-t", "json"], input=a.stdout, capture_output=True)
    if b.returncode != 0:
        return (f, {"_err": b.stderr[:120].decode("utf8", "replace")})
    got = json.loads(b.stdout)["meta"]
    out = {}
    for k in META:
        if k not in got:
            out[k] = "lost"
        else:
            out[k] = "exact" if flat(got[k]) == flat(META[k]) else "partial"
    return (f, out)

res = {}
with ThreadPoolExecutor(max_workers=8) as ex:
    for f, v in ex.map(work, FMTS):
        res[f] = v
print(json.dumps(res))
