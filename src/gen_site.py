"""Build the static website from the recorded measurements."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import scoreboard
import severity
from probes import PROBES
from verdicts import LANES, NOT_A_VERDICT

ROOT = Path(__file__).resolve().parent.parent


def load(directory, name, optional=False):
    path = directory / name
    if not path.exists():
        if optional:
            return None
        raise ValueError(f"missing required input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate(grid, keys, name):
    for fmt, row in grid.items():
        actual = set(row) - NOT_A_VERDICT
        if actual != set(keys):
            raise ValueError(f"{name}: {fmt} keys disagree with expected probes: "
                             f"missing {sorted(set(keys) - actual)}, extra {sorted(actual - set(keys))}")


def clean_bridge(data):
    if data is None:
        return {"measured": False}
    data = dict(data)
    if "bridge" in data:
        data["bridge"] = Path(data["bridge"]).name
    return {"measured": True, **data}


def document(directory):
    run = load(directory, "run.json")
    lanes = {}
    for key in ("matrix", "roundtrip", "exact", "meta"):
        spec = LANES[key]
        grid = load(directory, spec["file"])
        columns = scoreboard.MKEYS if key == "meta" else list(PROBES)
        rank, errors = dict(spec["rank"]), {}
        # A failed metadata conversion records only its error; it measured no key.
        if key == "meta":
            errors = {fmt: row["_err"] for fmt, row in grid.items() if "_err" in row}
            grid = {fmt: ({k: "err" for k in columns} if fmt in errors else row)
                    for fmt, row in grid.items()}
            if errors:
                rank.setdefault("err", -1)
        validate(grid, columns, spec["file"])
        lanes[key] = {"title": spec["title"], "rank": rank,
                      "order": sorted(rank, key=rank.get),
                      "columns": columns, "grid": grid, "errors": errors}
    ast = load(directory, "probes.json")
    validate({"probes": ast["probes"]}, PROBES, "probes.json")
    rows = scoreboard.rows(directory)
    for fmt, row in rows.items():
        segments = dict.fromkeys(["exact", "canonical", "survives", "expressed", "lost"], 0)
        for probe in PROBES:
            ex = lanes["exact"]["grid"].get(fmt, {}).get(probe)
            rt = lanes["roundtrip"]["grid"].get(fmt, {}).get(probe)
            wr = lanes["matrix"]["grid"][fmt][probe]
            bucket = ex if ex in ("exact", "canonical") else (
                "survives" if rt == "diff" else "expressed" if wr == "diff" else "lost")
            segments[bucket] += 1
        row["segments"] = segments
    carve = clean_bridge(load(directory, "carve.json", True))
    if carve["measured"]:
        grid = {key: carve[key] for key in ("source", "ast")}
        validate(grid, PROBES, "carve.json")
        for key, rt in carve.get("rt", {}).items():
            validate({key: rt}, PROBES, "carve.json roundtrip")
        lanes["carve"] = {"title": "Carve bridge", "grid": grid,
                          "columns": list(PROBES), "rank": {"err": 0, "same": 1, "canonical": 2, "exact": 3},
                          "order": ["err", "same", "canonical", "exact"]}
    carve_rt = clean_bridge(load(directory, "carve-rt.json", True))
    if carve_rt["measured"]:
        carve_rt["rank"] = LANES["carve_rt"]["rank"]
        carve_rt["order"] = sorted(carve_rt["rank"], key=carve_rt["rank"].get)
        validate(carve_rt["lanes"], carve_rt["fixtures"], "carve-rt.json")
    history_path = directory / "history.jsonl"
    history = [json.loads(line) for line in history_path.read_text().splitlines() if line.strip()] if history_path.exists() else []
    delta = load(directory, "delta.json", True)
    return {"run": run, "totals": scoreboard.aggregate(rows), "rows": rows,
            "probes": [{"name": name, "class": severity.SEVERITY[name],
                        "weight": severity.weight(name), **ast["probes"][name]} for name in PROBES],
            "lanes": lanes, "meta": lanes["meta"]["grid"], "carve": carve,
            "carve_rt": carve_rt, "history": history,
            "delta": {"status": delta["status"], "counts": delta["tally"],
                      "changes": delta["changes"], "breaches": delta.get("breaches", [])} if delta else {"status": "unmeasured", "counts": {}, "changes": []},
            "downloads": sorted(p.name for p in directory.iterdir() if p.suffix == ".json" or p.name == "history.jsonl")}


def build(results=ROOT / "results", output=ROOT / "dist"):
    results, output = Path(results), Path(output)
    data = document(results)
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "site", output)
    (output / "data").mkdir()
    (output / "data/site.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for name in data["downloads"]:
        shutil.copy2(results / name, output / "data" / name)
    for source, target in [("index.html", "report.html"), ("report.pdf", "report.pdf"),
                           ("overview.png", "overview.png"), ("dashboard.html", "dashboard.html")]:
        if (ROOT / "docs" / source).exists():
            shutil.copy2(ROOT / "docs" / source, output / target)
    html = (output / "index.html").read_text()
    for asset in ("app.js", "style.css"):
        digest = hashlib.sha256((output / asset).read_bytes()).hexdigest()[:12]
        html = html.replace(f'"{asset}"', f'"{asset}?v={digest}"')
    (output / "index.html").write_text(html, encoding="utf-8")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        build(args.results, args.output)
    except (ValueError, OSError, KeyError) as error:
        print(f"gen_site: {error}", file=sys.stderr)
        sys.exit(1)
