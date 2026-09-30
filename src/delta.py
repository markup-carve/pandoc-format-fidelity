"""What moved between two results sets, and whether that is allowed.

The nightly watch used to end in `git diff --stat results/`, which says a file
changed by so many lines. That is not reviewable: a lane file is one long line
of JSON, so every change reads as the same one-line diff, and nothing in it
says whether pandoc got better or worse.

This reads both sides as verdicts instead of as text. Every cell that moved is
reported as `format · probe · from -> to`, classified against the ranking in
verdicts.py, and weighted by what a reader loses (severity.py). Thresholds in
thresholds.json then decide whether the run passes; the exit code is the gate.

    python3 src/delta.py --baseline results --candidate /tmp/nightly --profile nightly
    python3 src/delta.py --baseline results-committed --json results/delta.json

A regression is a cell that dropped rank. That is a claim about two runs, not
about pandoc: a cell can drop because a writer changed, because the probe set
changed, or because the machine cannot run a converter today. The exemption
list in thresholds.json is where the third kind is written down, with a
reason, rather than being quietly subtracted.

There are two threshold profiles, because the two comparisons this repo makes
are not the same question. Against the pinned pandoc nothing may move without
a human deciding it should; against pandoc's nightly, upstream restyles
writers routinely, so presentation-class movement is expected and content-class
movement never is.
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

import scoreboard
import severity
from probes import PROBES
from verdicts import LANES, cells, direction

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_THRESHOLDS = ROOT / "thresholds.json"


# Neither a metadata key nor a Carve fixture is a probe, so severity has no
# opinion on either. Both get the structure weight: enough that losing one
# counts against the run, not so much that it outvotes a lost footnote.
FLAT_WEIGHT = {"meta": ("metadata", scoreboard.META_WEIGHT),
               "carve_rt": ("carve", scoreboard.META_WEIGHT)}


def weight_of(lane, probe):
    if lane in FLAT_WEIGHT:
        return FLAT_WEIGHT[lane][1]
    return severity.weight(probe) if probe in PROBES else 0


def class_of(lane, probe):
    if lane in FLAT_WEIGHT:
        return FLAT_WEIGHT[lane][0]
    return severity.SEVERITY.get(probe, "unknown")


def matches(pat, value):
    return pat == "*" or pat == value


def exemption(rules, change):
    for r in rules:
        if (matches(r.get("lane", "*"), change["lane"])
                and matches(r.get("format", "*"), change["format"])
                and matches(r.get("probe", "*"), change["probe"])):
            return r
    return None


def compare(baseline_dir, candidate_dir, thresholds):
    allow = thresholds.get("allow", [])
    changes, exempt, structural = [], [], []

    for lane in LANES:
        a = scoreboard.load_lane(baseline_dir, lane)
        b = scoreboard.load_lane(candidate_dir, lane)
        # An opt-in lane nobody ran is not news. One side having it and the
        # other not is, because the comparison silently stops covering it.
        if a is None and b is None and LANES[lane].get("optional"):
            continue
        if a is None or b is None:
            if a is None and b is None:
                where, what = "from both sides", "absent"
            elif b is None:
                where, what = "from %s" % candidate_dir, "missing"
            else:
                where, what = "from %s" % baseline_dir, "new"
            structural.append({
                "lane": lane, "what": what,
                "detail": "%s is absent %s" % (LANES[lane]["file"], where)})
            continue
        old = {(f, p): v for f, p, v in cells(a, lane)}
        new = {(f, p): v for f, p, v in cells(b, lane)}

        for k in sorted(set(new) - set(old)):
            structural.append({"lane": lane, "what": "added",
                               "format": k[0], "probe": k[1], "to": new[k]})
        for k in sorted(set(old) - set(new)):
            structural.append({"lane": lane, "what": "removed",
                               "format": k[0], "probe": k[1], "from": old[k]})

        for k in sorted(set(old) & set(new)):
            if lane == "carve_rt":
                before = a.get("fixtures", {}).get(k[1], {}).get("source")
                after = b.get("fixtures", {}).get(k[1], {}).get("source")
                if before is not None and after is not None and before != after:
                    structural.append({"lane": lane, "what": "changed-input",
                                       "format": k[0], "probe": k[1],
                                       "from": old[k], "to": new[k]})
                    continue
            if old[k] == new[k]:
                continue
            fmt, probe = k
            change = {
                "lane": lane, "format": fmt, "probe": probe,
                "from": old[k], "to": new[k],
                "direction": direction(lane, old[k], new[k]),
                "class": class_of(lane, probe),
                "weight": weight_of(lane, probe),
            }
            rule = exemption(allow, change)
            if rule:
                change["exempt"] = rule.get("reason", "no reason given")
                exempt.append(change)
            else:
                changes.append(change)

    return changes, exempt, structural


def tally(changes):
    worse = [c for c in changes if c["direction"] == "worse"]
    better = [c for c in changes if c["direction"] == "better"]
    unknown = [c for c in changes if c["direction"] == "unknown"]
    per_lane = {}
    for c in worse:
        per_lane[c["lane"]] = per_lane.get(c["lane"], 0) + 1
    per_class = {}
    for c in worse:
        per_class[c["class"]] = per_class.get(c["class"], 0) + 1
    return {
        "regressions": len(worse),
        "improvements": len(better),
        "unknown": len(unknown),
        "regression_weight": sum(c["weight"] for c in worse),
        "regressions_by_lane": per_lane,
        "regressions_by_class": per_class,
    }


def coverage_gaps(structural):
    """Structural changes that mean the comparison stopped covering something.

    A cell that disappeared is not scored as a regression, because there is no
    "to" verdict to rank - but it is not nothing either. A lane file that failed
    to be written, a baseline directory that does not exist, or a format the
    candidate no longer measures all produce exactly this, and all three leave
    the gate comparing less than it thinks. Left unchecked they read as a clean
    run, which is the worst answer a gate can give.

    A required lane absent from EITHER side counts, `new` included. A baseline
    directory that does not exist - a typo in BASELINE, a job step that did not
    copy it - makes every lane look new, and reporting that as a clean run is
    the exact false green this guards. A genuinely new lane trips it once, and
    that is the right number of times to be told nothing compared it.

    An opt-in lane is exempt: not running it is a choice, not a loss.
    """
    gaps = []
    for s in structural:
        if LANES[s["lane"]].get("optional"):
            continue
        if s["what"] in ("missing", "absent", "new"):
            gaps.append("%s lane: %s" % (s["lane"], s["detail"]))
        elif s["what"] == "removed":
            gaps.append("%s lane: %s/%s is in the baseline and not in the candidate"
                        % (s["lane"], s["format"], s["probe"]))
    return gaps


def breaches(t, thresholds, structural=()):
    """Every threshold the tally exceeds, said in full - the first breach is
    rarely the only one, and a gate that stops at the first hides the rest."""
    out = []
    if thresholds.get("fail_on_missing_coverage", True):
        gaps = coverage_gaps(structural)
        # Named individually up to a point, then counted: a candidate missing
        # every lane produces one gap per cell, and a wall of them buries the
        # rest of the report.
        out += gaps[:5]
        if len(gaps) > 5:
            out.append("%s of coverage lost in total" % plural(len(gaps), "point"))
    caps = thresholds.get("max_regressions", {})
    if "total" in caps and t["regressions"] > caps["total"]:
        out.append("%s, at most %d allowed"
                   % (plural(t["regressions"], "regression"), caps["total"]))
    for lane, n in sorted(t["regressions_by_lane"].items()):
        if lane in caps and n > caps[lane]:
            out.append("%s lane: %s, at most %d allowed"
                       % (lane, plural(n, "regression"), caps[lane]))
    by_class = thresholds.get("max_regressions_by_class", {})
    for cls, n in sorted(t["regressions_by_class"].items()):
        if cls in by_class and n > by_class[cls]:
            out.append("%s-class: %s, at most %d allowed"
                       % (cls, plural(n, "regression"), by_class[cls]))
    cap = thresholds.get("max_regression_weight")
    if cap is not None and t["regression_weight"] > cap:
        out.append("regression weight %d, at most %d allowed"
                   % (t["regression_weight"], cap))
    if thresholds.get("fail_on_unknown_verdict") and t["unknown"]:
        out.append("%s moved to or from a verdict no lane declares"
                   % plural(t["unknown"], "cell"))
    return out


# A job summary is capped at 1 MB, and a pandoc release that changes one
# writer's defaults can move hundreds of cells. The table is a summary either
# way: past this many rows nobody reads it, and results/delta.json holds all of
# them for anything that wants the full list.
MAX_TABLE_ROWS = 200


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def line(c):
    return "  %-10s %-14s %-22s %s -> %s%s" % (
        c["lane"], c["format"], c["probe"], c["from"], c["to"],
        "   (%s)" % c["exempt"] if "exempt" in c else "")


def render_text(rep):
    b, c = rep["baseline"], rep["candidate"]
    out = ["pandoc-format-fidelity delta",
           "  baseline   %s" % stamp(b),
           "  candidate  %s" % stamp(c), ""]
    t = rep["tally"]
    out.append("%s, %s, weight %d"
               % (plural(t["regressions"], "regression"),
                  plural(t["improvements"], "improvement"),
                  t["regression_weight"]))
    for label, key in [("regressions", "worse"), ("improvements", "better"),
                       ("unclassifiable", "unknown")]:
        rows = [x for x in rep["changes"] if x["direction"] == key]
        if rows:
            out += ["", "%s:" % label] + [line(x) for x in rows]
    if rep["exempt"]:
        out += ["", "exempt (thresholds.json):"] + [line(x) for x in rep["exempt"]]
    if rep["structural"]:
        out += ["", "structural changes (not scored):"]
        out += ["  %s" % json.dumps(x, sort_keys=True) for x in rep["structural"]]
    out += [""]
    out.append("status: %s (profile %s)"
               % (rep["status"], rep["thresholds"].get("profile", "?")))
    for x in rep["breaches"]:
        out.append("  breach: %s" % x)
    return "\n".join(out)


def stamp(side):
    r = side.get("run") or {}
    p = r.get("pandoc") or {}
    return "%s  pandoc %s%s  %s" % (
        r.get("date", "date unrecorded"),
        p.get("version", "?"),
        "" if p.get("is_pin", True) else " (not the pin)",
        side.get("dir", ""))


def render_markdown(rep):
    t = rep["tally"]
    ok = rep["status"] == "ok"
    out = ["## Fidelity delta: %s" % ("within thresholds" if ok else "THRESHOLD BREACH"),
           "",
           "Profile `%s`. %s" % (rep["thresholds"].get("profile", "?"),
                                 rep["thresholds"].get("description", "")),
           "",
           "| | date | pandoc | commit |",
           "|---|---|---|---|"]
    for label, side in [("baseline", rep["baseline"]), ("candidate", rep["candidate"])]:
        r = side.get("run") or {}
        p = r.get("pandoc") or {}
        out.append("| %s | %s | %s | %s |" % (
            label, r.get("date", "-"), p.get("version", "-"), r.get("commit", "-")))
    out += ["",
            "**%s** (weight %d), %s."
            % (plural(t["regressions"], "regression"), t["regression_weight"],
               plural(t["improvements"], "improvement")), ""]
    for x in rep["breaches"]:
        out.append("- breach: %s" % x)
    rows = [c for c in rep["changes"] if c["direction"] in ("worse", "better")]
    if rows:
        # Sorted so the regressions are the first thing read, worst class first.
        order = {"worse": 0, "better": 1}
        rows.sort(key=lambda c: (order[c["direction"]], -c["weight"],
                                 c["lane"], c["format"], c["probe"]))
        shown, hidden = rows[:MAX_TABLE_ROWS], max(0, len(rows) - MAX_TABLE_ROWS)
        out += ["", "| | lane | format | probe | from | to | severity |",
                "|---|---|---|---|---|---|---|"]
        for c in shown:
            out.append("| %s | %s | `%s` | `%s` | %s | **%s** | %s |" % (
                "worse" if c["direction"] == "worse" else "better",
                c["lane"], c["format"], c["probe"], c["from"], c["to"], c["class"]))
        if hidden:
            out += ["", "%d further row(s) not shown; the full list is in "
                        "`results/delta.json`." % hidden]
    if not rows and not rep["structural"]:
        out += ["", "Every cell held its verdict."]
    return "\n".join(out) + "\n"


def history_record(rep, candidate):
    r = (rep["candidate"].get("run") or {})
    p = r.get("pandoc") or {}
    board = scoreboard.read(candidate)
    return {
        "date": r.get("date") or datetime.now(timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pandoc": p.get("version"),
        "is_pin": p.get("is_pin"),
        "commit": r.get("commit"),
        "probes": board["probes"],
        "totals": board["totals"],
        "delta": {"regressions": rep["tally"]["regressions"],
                  "improvements": rep["tally"]["improvements"],
                  "regression_weight": rep["tally"]["regression_weight"],
                  "status": rep["status"]},
    }


def load_thresholds(path, profile, fail):
    """One profile, plus the exemptions both profiles share.

    A missing profile is an error rather than a fallback to the strictest
    one: a typo in a workflow would otherwise turn the nightly watch into a
    gate nobody meant to arm, and it would look like pandoc had broken.
    """
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    profiles = doc.get("profiles", {})
    if profile not in profiles:
        fail("no profile %r in %s (have: %s)"
             % (profile, path, ", ".join(sorted(profiles)) or "none"))
    out = dict(profiles[profile])
    out["allow"] = doc.get("allow", [])
    out["profile"] = profile
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", default="results",
                    help="results directory to compare against (default: results)")
    ap.add_argument("--candidate", default="results",
                    help="results directory being judged (default: results)")
    ap.add_argument("--thresholds", default=str(DEFAULT_THRESHOLDS))
    ap.add_argument("--profile", default="pin",
                    help="which profile in the thresholds file to gate on")
    ap.add_argument("--json", dest="json_out",
                    help="write the full delta here")
    ap.add_argument("--markdown", dest="md_out",
                    help="write a job-summary table here")
    ap.add_argument("--record", dest="record",
                    help="append one summary line to this history file")
    ap.add_argument("--exit-zero", action="store_true",
                    help="report a breach but do not fail (for a report-only run)")
    args = ap.parse_args(argv)

    if pathlib.Path(args.baseline).resolve() == pathlib.Path(args.candidate).resolve():
        ap.error("baseline and candidate are the same directory - "
                 "there is nothing to compare")

    thresholds = load_thresholds(args.thresholds, args.profile, ap.error)
    changes, exempt, structural = compare(args.baseline, args.candidate, thresholds)
    t = tally(changes)
    br = breaches(t, thresholds, structural)
    rep = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline": {"dir": args.baseline,
                     "run": scoreboard.load_run(args.baseline)},
        "candidate": {"dir": args.candidate,
                      "run": scoreboard.load_run(args.candidate)},
        "thresholds": thresholds,
        "changes": changes,
        "exempt": exempt,
        "structural": structural,
        "tally": t,
        "breaches": br,
        "status": "breach" if br else "ok",
    }

    print(render_text(rep))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    if args.md_out:
        pathlib.Path(args.md_out).write_text(render_markdown(rep), encoding="utf-8")
    if args.record:
        with open(args.record, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(history_record(rep, args.candidate),
                                sort_keys=True) + "\n")
    return 0 if (rep["status"] == "ok" or args.exit_zero) else 1


if __name__ == "__main__":
    sys.exit(main())
