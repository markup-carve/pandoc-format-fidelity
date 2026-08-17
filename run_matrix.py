"""Writer lane: can the format say it at all?

    diff  writer(rich) != writer(degraded)  -- the format expresses it
    same  byte-identical output             -- the format cannot

Runs against `pandoc server`, so it covers every writer including the binary
ones. The server has no filesystem access: any media a probe references has to
be handed over in the request, or every media-embedding writer 500s.
"""
import base64, io, json, os, pathlib, sys, zipfile, urllib.request

# pandoc-server has no filesystem access: media referenced by a probe has to be
# supplied in the request, or every media-embedding writer 500s.
FILES = {"i.png": base64.b64encode(
    (pathlib.Path(__file__).parent / "fixtures" / "i.png").read_bytes()).decode()}
from concurrent.futures import ThreadPoolExecutor
from probes import PROBES, API

URL = os.environ.get("PANDOC_SERVER", "http://localhost:3033/")
WRITERS = sys.argv[1].split(",") if len(sys.argv) > 1 else []

def conv(blocks, to, meta=None):
    doc = {"pandoc-api-version": API, "meta": meta or {}, "blocks": blocks}
    body = json.dumps({"text": json.dumps(doc), "from": "json", "to": to,
                       "standalone": False, "wrap": "preserve",
                       "files": FILES}).encode()
    req = urllib.request.Request(URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = r.read()
    except Exception as e:
        return ("ERR", str(e)[:120])
    return ("OK", normalize(out, to))

def normalize(out, to):
    # binary writers come back base64-encoded
    if to in BINARY:
        raw = out
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            parts = []
            for n in sorted(z.namelist()):
                if n.endswith(("core.xml", "app.xml", "meta.xml")):
                    continue
                parts.append(n.encode() + b"|" + z.read(n))
            return b"".join(parts)
        except zipfile.BadZipFile:
            return raw
    return out

from common import BINARY  # noqa: E402

def work(args):
    w, name = args
    p = PROBES[name]
    sr, rich = conv(p["rich"], w)
    sd, deg = conv(p["degraded"], w)
    if sr == "ERR" or sd == "ERR":
        return (w, name, "err", rich if sr == "ERR" else deg)
    return (w, name, "diff" if rich != deg else "same", "")

jobs = [(w, n) for w in WRITERS for n in PROBES]
res = {}
with ThreadPoolExecutor(max_workers=8) as ex:
    for w, n, verdict, info in ex.map(work, jobs):
        res.setdefault(w, {})[n] = verdict
        if verdict == "err":
            res[w].setdefault("_errs", []).append(f"{n}: {info}")
print(json.dumps(res))
