"""Round-trip lane: is the distinction still there after reading the output back?

    diff  read(write(rich)) != read(write(degraded))  -- survives the round trip
    same  the two collapse to the same AST            -- lost

Differential, like the writer lane: the two sides are only ever compared with
each other, never with the input, so writer canonicalization cancels out.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from common import PANDOC, WRITE_OPTS, key
from probes import PROBES, API

FMTS = sys.argv[1].split(",") if len(sys.argv) > 1 else []


def roundtrip(blocks, fmt):
    doc = json.dumps({"pandoc-api-version": API, "meta": {},
                      "blocks": blocks}).encode()
    out = subprocess.run([PANDOC, "-f", "json", "-t", fmt, "-o", "-"] + WRITE_OPTS,
                         input=doc, capture_output=True)
    if out.returncode != 0:
        return ("ERR", out.stderr[:150].decode("utf8", "replace"))
    back = subprocess.run([PANDOC, "-f", fmt, "-t", "json"],
                          input=out.stdout, capture_output=True)
    if back.returncode != 0:
        return ("ERR", back.stderr[:150].decode("utf8", "replace"))
    try:
        return ("OK", key(json.loads(back.stdout)["blocks"]))
    except Exception as e:  # noqa: BLE001 - reported as a cell value
        return ("ERR", str(e)[:120])


def work(args):
    fmt, name = args
    probe = PROBES[name]
    sa, a = roundtrip(probe["rich"], fmt)
    sb, b = roundtrip(probe["degraded"], fmt)
    if sa == "ERR" or sb == "ERR":
        return (fmt, name, "err", a if sa == "ERR" else b)
    return (fmt, name, "diff" if a != b else "same", "")


res = {}
with ThreadPoolExecutor(max_workers=10) as ex:
    for fmt, name, verdict, info in ex.map(
            work, [(f, n) for f in FMTS for n in PROBES]):
        res.setdefault(fmt, {})[name] = verdict
        if verdict == "err":
            res[fmt].setdefault("_errs", {})[name] = info
print(json.dumps(res))
