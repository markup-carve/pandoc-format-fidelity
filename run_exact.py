"""Exact lane: does the rich AST come back as itself?

This is the only lane that compares a result against the input, so it is the
only lane where canonicalization can lie. It reports three verdicts instead of
two, because "not identical" and "lost something" are different claims:

    exact      identical after folding Plain into Para, nothing else
    canonical  identical after also folding the differences listed in
               common.canonical() -- the format kept the content and restyled it
    lossy      something the input carried is not in the output

Collapsing `canonical` into `lossy` overstates loss by up to 10 of 66 probes
(pandoc's markdown is the worst case); collapsing it into `exact` would hide
real precision loss like a rounded column width. Hence three columns.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from common import PANDOC, WRITE_OPTS, canonical, key, plain_para, unwrap
from probes import PROBES, API

FMTS = sys.argv[1].split(",") if len(sys.argv) > 1 else []


def roundtrip(blocks, fmt):
    doc = json.dumps({"pandoc-api-version": API, "meta": {},
                      "blocks": blocks}).encode()
    out = subprocess.run([PANDOC, "-f", "json", "-t", fmt, "-o", "-"] + WRITE_OPTS,
                         input=doc, capture_output=True)
    if out.returncode != 0:
        return None
    back = subprocess.run([PANDOC, "-f", fmt, "-t", "json"],
                          input=out.stdout, capture_output=True)
    if back.returncode != 0:
        return None
    try:
        return json.loads(back.stdout)["blocks"]
    except Exception:  # noqa: BLE001 - reported as a cell value
        return None


def work(args):
    fmt, name = args
    got = roundtrip(PROBES[name]["rich"], fmt)
    if got is None:
        return (fmt, name, "err")
    got = unwrap(got)
    want = PROBES[name]["rich"]
    if key(plain_para(got)) == key(plain_para(want)):
        return (fmt, name, "exact")
    if key(canonical(got)) == key(canonical(want)):
        return (fmt, name, "canonical")
    return (fmt, name, "lossy")


res = {}
with ThreadPoolExecutor(max_workers=10) as ex:
    for fmt, name, verdict in ex.map(
            work, [(f, n) for f in FMTS for n in PROBES]):
        res.setdefault(fmt, {})[name] = verdict
print(json.dumps(res))
