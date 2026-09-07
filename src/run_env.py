"""Stamp a results set with what produced it.

Every number under results/ is measured against one pandoc build on one day.
Until this file existed, none of that was recorded: the grid said what pandoc
does without saying which pandoc, and a rerun six months later was
indistinguishable from the original. A dashboard that quotes a version has to
read it from the measurement, not from a heading someone typed.

Written before the lanes run, so a lane that dies still leaves a stamp saying
what was being measured when it did.
"""
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone

from common import PANDOC, ROOT
from probes import API, PROBES

OUT = ROOT / "results" / "run.json"
FETCH = ROOT / "scripts" / "fetch-pandoc.sh"


def sh(*cmd, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def pandoc_banner():
    out = sh(PANDOC, "--version")
    return out.splitlines()[0].strip() if out else None


def pinned_version():
    """The version scripts/fetch-pandoc.sh defaults to - the repo's baseline."""
    try:
        m = re.search(r'PANDOC_VERSION="[^"]*:-([^}"]+)\}"',
                      FETCH.read_text(encoding="utf-8"))
    except OSError:
        return None
    return m.group(1) if m else None


def git(*args):
    return sh("git", *args, cwd=str(ROOT))


def main():
    banner = pandoc_banner()
    version = banner.split()[1] if banner and len(banner.split()) > 1 else None
    pin = pinned_version()
    stamp = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pandoc": {
            "version": version,
            "banner": banner,
            # Which binary, without the machine's directory layout in it.
            "binary": os.path.basename(PANDOC),
            "pinned": pin,
            # False means the results measure something other than the baseline
            # the repo pins, which is legitimate (a nightly) and worth saying.
            "is_pin": bool(version and pin and version == pin),
            "api": API,
        },
        "probes": len(PROBES),
        "commit": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "python": platform.python_version(),
        "platform": "%s-%s" % (platform.system(), platform.machine()),
    }
    if banner is None:
        stamp["pandoc"]["error"] = "pandoc did not answer --version"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(stamp, indent=1) + "\n", encoding="utf-8")
    print("results/run.json: %s, %s" % (banner or "no pandoc", stamp["date"]))
    return 0 if banner else 1


if __name__ == "__main__":
    sys.exit(main())
