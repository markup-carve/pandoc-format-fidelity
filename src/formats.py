"""The formats pandoc can both write and read, minus the ones a document probe
cannot say anything about. Printed as a comma-separated list for the Makefile.

With --dump it writes results/formats.json instead: the inventory the report
quotes (how many readers and writers this pandoc ships). Captured here, at
measurement time, so `make report` needs the results and not pandoc itself.
"""
import json
import subprocess
import sys

from common import PANDOC

# See the Makefile for why each of these is out.
EXCLUDE = {"biblatex", "bibtex", "csljson", "json", "xml"}


def listing(flag):
    out = subprocess.run([PANDOC, flag], capture_output=True, text=True)
    return set(out.stdout.split())


inputs, outputs = listing("--list-input-formats"), listing("--list-output-formats")
readable = sorted((inputs & outputs) - EXCLUDE)

if "--dump" in sys.argv:
    json.dump({"inputs": sorted(inputs), "outputs": sorted(outputs),
               "readable": readable},
              open("results/formats.json", "w", encoding="utf-8"), indent=1)
    print("results/formats.json: %d input, %d output formats"
          % (len(inputs), len(outputs)))
else:
    print(",".join(readable))
