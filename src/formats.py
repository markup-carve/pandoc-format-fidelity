"""The formats pandoc can both write and read, minus the ones a document probe
cannot say anything about. Printed as a comma-separated list for the Makefile."""
import subprocess

from common import PANDOC

# See the Makefile for why each of these is out.
EXCLUDE = {"biblatex", "bibtex", "csljson", "json", "xml"}


def listing(flag):
    out = subprocess.run([PANDOC, flag], capture_output=True, text=True)
    return set(out.stdout.split())


print(",".join(sorted((listing("--list-input-formats")
                       & listing("--list-output-formats")) - EXCLUDE)))
