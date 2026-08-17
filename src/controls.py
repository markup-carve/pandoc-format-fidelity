"""The two controls the report quotes but no lane produces.

Neither answers "how good is this format" - they answer "is the writer lane's
comparison trustworthy at all", which is why they run separately and are not part
of the grid:

  determinism  the writer lane calls two outputs different to mean "the format
               expressed the feature". That only holds if the writer is
               reproducible, so every writer is asked to emit the same document
               twice, through the same server path the lane uses.
  wrap         --wrap=preserve is on for every writer. Without it a wrapping
               writer folds a SoftBreak into a space and the probe reads as
               "cannot express" for a distinction the format handles fine. This
               counts how many writers that flag moves.

Run it with a pandoc server already listening (see the Makefile).
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import BINARY, PANDOC, RESOURCE, WRITE_OPTS, zip_normalize
from probes import API, PROBES

URL = os.environ.get("PANDOC_SERVER", "http://localhost:3033/")
# What the report currently states, against the pinned pandoc 3.10.2. A different
# pandoc may well move these; the point is that it cannot do so quietly - change
# the number here and in the report together.
EXPECT_MOVED = 45
EXPECT_UNCHECKABLE = {"pdf"}
FILES = {"i.png": base64.b64encode(
    open("fixtures/i.png", "rb").read()).decode()}
# One probe with enough shape - a table - to exercise a writer end to end.
SAMPLE = PROBES["table"]["rich"]


def doc(blocks):
    return json.dumps({"pandoc-api-version": API, "meta": {}, "blocks": blocks})


def via_server(blocks, fmt):
    """The writer lane's exact request, so the control covers the same path."""
    body = json.dumps({"text": doc(blocks), "from": "json", "to": fmt,
                       "standalone": False, "wrap": "preserve",
                       "files": FILES}).encode()
    req = urllib.request.Request(URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = r.read()
    except Exception:
        return None
    return zip_normalize(out) if fmt in BINARY else out


def via_cli(blocks, fmt, opts):
    p = subprocess.run([PANDOC, "-f", "json", "-t", fmt, *opts],
                       input=doc(blocks).encode(), capture_output=True)
    if p.returncode != 0:
        return None
    return zip_normalize(p.stdout) if fmt in BINARY else p.stdout


def determinism(fmt):
    a, b = via_server(SAMPLE, fmt), via_server(SAMPLE, fmt)
    if a is None or b is None:
        return fmt, "error"
    return fmt, "identical" if a == b else "differs"


def wrap(fmt):
    """The softbreak probe with --wrap=preserve and with pandoc's default."""
    p = PROBES["softbreak"]
    out = {}
    for label, opts in (("preserve", WRITE_OPTS), ("default", RESOURCE)):
        rich, deg = via_cli(p["rich"], fmt, opts), via_cli(p["degraded"], fmt, opts)
        out[label] = ("error" if rich is None or deg is None
                      else "diff" if rich != deg else "same")
    return fmt, out


writers = subprocess.run([PANDOC, "--list-output-formats"],
                         capture_output=True, text=True).stdout.split()
with ThreadPoolExecutor(max_workers=8) as ex:
    det = dict(ex.map(determinism, writers))
    wr = dict(ex.map(wrap, writers))

differs = sorted(f for f, v in det.items() if v == "differs")
errored = sorted(f for f, v in det.items() if v == "error")
moved = sorted(f for f, v in wr.items()
               if v["preserve"] == "diff" and v["default"] == "same")

print("determinism: %d of %d writers re-emit identical bytes"
      % (sum(1 for v in det.values() if v == "identical"), len(det)))
print("  not reproducible: %s" % (", ".join(differs) or "none"))
print("  could not be checked (writer errors): %s" % (", ".join(errored) or "none"))
print("wrap: --wrap=preserve moves %d writers on the softbreak probe" % len(moved))
print("  %s" % ", ".join(moved))

# The report quotes all three findings, so any drift has to be loud.
problems = []
if differs:
    problems.append("writer lane comparison is unsound: %s not reproducible" % differs)
if set(errored) != EXPECT_UNCHECKABLE:
    problems.append("writers that error changed: expected %s, got %s"
                    % (sorted(EXPECT_UNCHECKABLE), errored))
if len(moved) != EXPECT_MOVED:
    problems.append("--wrap=preserve now moves %d writers, the report says %d"
                    % (len(moved), EXPECT_MOVED))
if problems:
    sys.exit("\n".join(problems) + "\nupdate the report and src/controls.py together")
