"""Put src/ on the path so the tests run without a wrapper.

`make check` sets PYTHONPATH, but a bare
`python3 -m unittest discover -s tests -t .` is what anyone actually types, and
without this it fails with ModuleNotFoundError on the repo's own modules -
which reads as broken code rather than a missing environment variable.
"""
import pathlib
import sys

SRC = str(pathlib.Path(__file__).resolve().parent.parent / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
