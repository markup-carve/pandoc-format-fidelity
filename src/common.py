"""Shared configuration and AST comparison helpers for every lane."""
import json
import os
import pathlib

# Repo root, one level up from src/. The lanes are run from the root by the
# Makefile, but this has to hold whatever the working directory is.
ROOT = pathlib.Path(__file__).resolve().parent.parent
PANDOC = os.environ.get("PANDOC", "./vendor/pandoc/bin/pandoc")

# Without this, a writer that wraps at 72 columns turns a SoftBreak into a
# space and the probe reads as "cannot express" when the format expresses it
# fine. jgm pointed this out on the pandoc discussion; it moved 46 writers.
WRAP = ["--wrap=preserve"]

# The image probes reference i.png. If pandoc cannot resolve it, the media
# writers either fail outright or -- worse -- leave the src untouched, which
# round-trips to a FALSE exact: epub embeds a resolvable image and rewrites the
# src to media/file0.png, so "exact" is only correct when the file is found.
# Absolute, so no lane depends on the working directory.
RESOURCE = ["--resource-path=%s" % (ROOT / "fixtures")]

# Everything a writer invocation needs.
WRITE_OPTS = WRAP + RESOURCE

# Formats whose output is a zip or otherwise not text.
BINARY = {"docx", "odt", "pptx", "epub", "epub2", "epub3", "xlsx", "chunkedhtml"}

# Raw-format names that mean the same target.
RAW_ALIAS = {"tex": "latex", "html4": "html", "html5": "html"}

# Wrappers the container formats add around a whole document.
WRAPCLS = {"cell", "section"}


def zip_normalize(raw):
    """Compare a zip container by its members, minus the ones that carry a
    timestamp. Used by the writer lane and by the determinism control, so the
    two cannot drift apart."""
    import io
    import zipfile
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return raw
    return b"".join(n.encode() + b"|" + z.read(n) for n in sorted(z.namelist())
                    if not n.endswith(("core.xml", "app.xml", "meta.xml")))


def plain_para(x):
    """Fold Plain into Para. The minimum needed to compare at all: readers
    choose between them on grounds that have nothing to do with the probe."""
    if isinstance(x, list):
        return [plain_para(i) for i in x]
    if not isinstance(x, dict):
        return x
    d = dict(x)
    if d.get("t") == "Plain":
        d["t"] = "Para"
    if "c" in d:
        d["c"] = plain_para(d["c"])
    return d


def canonical(x, drop_header_ids=True):
    """plain_para, plus the differences that are canonicalization by any
    reasonable reading. Everything folded here is listed in the README --
    the point of the lane is that the list is arguable, so it has to be visible.

      AlignLeft        == AlignDefault   (a default-aligned column renders left)
      ColWidth n       == ColWidthDefault (a measured width is the writer's
                                           arithmetic, not the source's data)
      raw `tex`        == raw `latex`     (alias for one target)
      Header id        dropped            (--auto_identifiers invents these)
    """
    if isinstance(x, list):
        return [canonical(i, drop_header_ids) for i in x]
    if not isinstance(x, dict):
        return x
    d = dict(x)
    t = d.get("t")
    if t == "Plain":
        d["t"] = "Para"
    if t == "AlignLeft":
        d["t"] = "AlignDefault"
    if t == "ColWidth":
        return {"t": "ColWidthDefault"}
    if t in ("RawBlock", "RawInline"):
        fmt, s = d["c"]
        d["c"] = [RAW_ALIAS.get(fmt, fmt), s]
        return d
    if t == "Header" and drop_header_ids:
        lvl, a, inl = d["c"]
        d["c"] = [lvl, ["", a[1], a[2]], canonical(inl, drop_header_ids)]
        return d
    if "c" in d:
        d["c"] = canonical(d["c"], drop_header_ids)
    return d


def unwrap(blocks):
    """Strip the container chrome ipynb/epub/fb2 add around a whole document."""
    changed = True
    while changed:
        changed = False
        out = []
        for b in blocks:
            if b.get("t") == "Header" and not b["c"][2]:
                changed = True
                continue
            if (b.get("t") == "Para" and len(b["c"]) == 1
                    and b["c"][0].get("t") == "Span" and not b["c"][0]["c"][1]):
                changed = True
                continue
            out.append(b)
        blocks = out
        if (len(blocks) == 1 and blocks[0].get("t") == "Div"
                and WRAPCLS & set(blocks[0]["c"][0][1])):
            blocks = blocks[0]["c"][1]
            changed = True
    return blocks


def key(x):
    return json.dumps(x, sort_keys=True)
