"""No developer's filesystem in tracked files.

The leak this guards against arrived through captured error text, not through
code: a lane ran pandoc by its resolved absolute path and stored the raw
exception message, which named the home directory the binary sat in. That
message reached results/ and from there the generated pages under docs/. The
measurements are regenerated regularly, so the guard has to sit over the
artifacts and not only over the sources.
"""

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Spelled in pieces so this file carries no literal host path of its own.
SEP = "/"
HOST_PATH = re.compile(
    r"%shome%s(?!runner(?:[%s\s\"']|$))[A-Za-z0-9._-]+"
    r"|%sUsers%s(?!runner(?:[%s\s\"']|$))[A-Za-z0-9._-]+"
    r"|%smedia%s[A-Za-z0-9._-]+%s[A-Za-z0-9._-]+"
    % (SEP, SEP, SEP, SEP, SEP, SEP, SEP, SEP, SEP)
)

# Files whose business is the pattern itself, or which legitimately spell a
# runner path in full. Add a path here only with a reason.
EXEMPT = {
    "tests/test_no_host_paths.py",  # the guard; its regex is the pattern
    # Spells a home-shaped directory on purpose, to prove a failing converter
    # is recorded without one.
    "tests/test_carve_roundtrip.py",
}


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [p for p in out.decode("utf8").split("\0") if p]


class TestNoHostPaths(unittest.TestCase):
    def test_tracked_files_carry_no_host_path(self):
        offenders = []
        for rel in tracked_files():
            if rel in EXEMPT:
                continue
            path = ROOT / rel
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf8", "replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                for hit in HOST_PATH.findall(line):
                    offenders.append("%s:%d: %s" % (rel, lineno, hit))
        self.assertEqual(
            [],
            offenders,
            "a developer's filesystem is committed; record the converter and "
            "the reason, never where the binary lives:\n  "
            + "\n  ".join(offenders),
        )

    def test_guard_accepts_ci_runner_paths(self):
        runner = SEP + "home" + SEP + "runner" + SEP + "work" + SEP + "repo"
        self.assertEqual([], HOST_PATH.findall(runner))
        self.assertEqual([], HOST_PATH.findall(SEP + "Users" + SEP + "runner"))

    def test_guard_catches_each_shape(self):
        for probe in (
            SEP + "home" + SEP + "someone" + SEP + "bin" + SEP + "pandoc",
            SEP + "Users" + SEP + "someone" + SEP + "bin",
            SEP + "media" + SEP + "someone" + SEP + "work",
        ):
            self.assertTrue(HOST_PATH.search(probe), probe)


if __name__ == "__main__":
    unittest.main()
