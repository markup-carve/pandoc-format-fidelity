"""The delta is a gate, so it is worth more than a smoke test.

Every case here is one the nightly watch will actually meet: a writer that got
worse, one that got better, a cell that only errors on this machine, a probe
that did not exist last time, and an opt-in lane nobody ran.
"""
import contextlib
import io
import json
import pathlib
import tempfile
import unittest

import delta

THRESHOLDS = {
    "allow": [{"lane": "matrix", "format": "pdf", "probe": "*",
               "reason": "needs a TeX engine"}],
    "profiles": {
        "strict": {"max_regressions": {"total": 0}, "max_regression_weight": 0,
                   "fail_on_unknown_verdict": True},
        "loose": {"max_regressions": {"total": 5},
                  "max_regressions_by_class": {"content": 0},
                  "max_regression_weight": 99},
    },
}


def write(d, name, obj):
    (pathlib.Path(d) / name).write_text(json.dumps(obj), encoding="utf-8")


class DeltaCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = pathlib.Path(self.tmp.name) / "a"
        self.b = pathlib.Path(self.tmp.name) / "b"
        self.a.mkdir()
        self.b.mkdir()
        self.thresholds_path = pathlib.Path(self.tmp.name) / "t.json"
        self.thresholds_path.write_text(json.dumps(THRESHOLDS), encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def both(self, name, old, new):
        write(self.a, name, old)
        write(self.b, name, new)
        self.complete()

    def complete(self):
        """Give both sides every required lane file.

        An absent lane is lost coverage and breaches on its own, so a test
        about one lane has to supply the others or it measures the gate
        instead of the case it means to.
        """
        for lane, spec in delta.LANES.items():
            if spec.get("optional"):
                continue
            for d in (self.a, self.b):
                if not (d / spec["file"]).exists():
                    write(d, spec["file"], {})

    def run_compare(self, profile="strict"):
        t = delta.load_thresholds(str(self.thresholds_path), profile,
                                  lambda m: (_ for _ in ()).throw(AssertionError(m)))
        changes, exempt, structural = delta.compare(self.a, self.b, t)
        return t, changes, exempt, structural


class TestCompare(DeltaCase):
    def test_a_dropped_verdict_is_a_regression(self):
        self.both("exact.json", {"html": {"note": "exact"}}, {"html": {"note": "lossy"}})
        _, changes, _, _ = self.run_compare()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["direction"], "worse")
        self.assertEqual(changes[0]["class"], "content")
        self.assertEqual(changes[0]["weight"], 3)

    def test_a_raised_verdict_is_an_improvement(self):
        self.both("matrix.json", {"rst": {"emph": "same"}}, {"rst": {"emph": "diff"}})
        _, changes, _, _ = self.run_compare()
        self.assertEqual(changes[0]["direction"], "better")

    def test_canonical_is_a_step_not_a_cliff(self):
        """exact -> canonical is a regression, but a smaller one than
        exact -> lossy, and canonical -> lossy is a regression of its own."""
        self.both("exact.json", {"html": {"emph": "exact"}},
                  {"html": {"emph": "canonical"}})
        _, changes, _, _ = self.run_compare()
        self.assertEqual(changes[0]["direction"], "worse")
        self.both("exact.json", {"html": {"emph": "canonical"}},
                  {"html": {"emph": "lossy"}})
        _, changes, _, _ = self.run_compare()
        self.assertEqual(changes[0]["direction"], "worse")

    def test_an_exempt_cell_does_not_count(self):
        self.both("matrix.json", {"pdf": {"emph": "diff"}}, {"pdf": {"emph": "err"}})
        _, changes, exempt, _ = self.run_compare()
        self.assertEqual(changes, [])
        self.assertEqual(len(exempt), 1)
        self.assertIn("TeX", exempt[0]["exempt"])

    def test_a_missing_baseline_directory_is_not_a_clean_run(self):
        """The likeliest way to get a false green: a typo in BASELINE. The
        candidate here is complete, so nothing but the absent baseline can
        make this breach."""
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        t = delta.load_thresholds(str(self.thresholds_path), "strict",
                                  lambda m: (_ for _ in ()).throw(AssertionError(m)))
        changes, _, structural = delta.compare(self.a / "nope", self.b, t)
        self.assertEqual(changes, [])
        found = delta.breaches(delta.tally(changes), t, structural)
        self.assertTrue(found)
        self.assertTrue(any("exact" in b for b in found), found)

    def test_a_new_probe_is_structural_not_a_regression(self):
        self.both("exact.json", {"html": {"emph": "exact"}},
                  {"html": {"emph": "exact", "brand_new": "lossy"}})
        _, changes, _, structural = self.run_compare()
        self.assertEqual(changes, [])
        added = [s for s in structural if s["what"] == "added"]
        self.assertEqual([(s["lane"], s["probe"]) for s in added],
                         [("exact", "brand_new")])

    def test_an_optional_lane_nobody_ran_is_silent(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        _, _, _, structural = self.run_compare()
        self.assertEqual([s for s in structural if s["lane"] == "carve_rt"], [])

    def test_an_optional_lane_present_on_one_side_is_reported(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        write(self.b, "carve-rt.json", {"lanes": {"bridge": {"emphasis": "exact"}}})
        _, _, _, structural = self.run_compare()
        carve = [s for s in structural if s["lane"] == "carve_rt"]
        self.assertEqual(len(carve), 1)
        self.assertEqual(carve[0]["what"], "new")

    def test_the_carve_lane_is_compared_when_both_sides_have_it(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        write(self.a, "carve-rt.json", {"lanes": {"bridge": {"table_span": "exact"}}})
        write(self.b, "carve-rt.json", {"lanes": {"bridge": {"table_span": "lossy"}}})
        _, changes, _, _ = self.run_compare()
        self.assertEqual(changes[0]["direction"], "worse")
        self.assertEqual(changes[0]["class"], "carve")

    def test_changed_carve_input_is_not_an_engine_improvement(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        write(self.a, "carve-rt.json", {"fixtures": {"span": {"source": "| a < |"}},
                                      "lanes": {"bridge": {"span": "lossy"}}})
        write(self.b, "carve-rt.json", {"fixtures": {"span": {"source": "| a | < |"}},
                                      "lanes": {"bridge": {"span": "exact"}}})
        _, changes, _, structural = self.run_compare()
        self.assertEqual(changes, [])
        self.assertEqual(structural[0]["what"], "changed-input")
        self.assertEqual(structural[0]["probe"], "span")

    def test_unchanged_carve_input_still_detects_regressions(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        for root, verdict in ((self.a, "exact"), (self.b, "lossy")):
            write(root, "carve-rt.json", {"fixtures": {"span": {"source": "| a | < |"}},
                                         "lanes": {"bridge": {"span": verdict}}})
        _, changes, _, structural = self.run_compare()
        self.assertEqual(changes[0]["direction"], "worse")
        self.assertEqual(structural, [])

    def test_respelled_beats_lossy(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        write(self.a, "carve-rt.json", {"lanes": {"bridge": {"footnote": "lossy"}}})
        write(self.b, "carve-rt.json", {"lanes": {"bridge": {"footnote": "respelled"}}})
        _, changes, _, _ = self.run_compare()
        self.assertEqual(changes[0]["direction"], "better")


class TestThresholds(DeltaCase):
    def test_strict_profile_breaches_on_one_regression(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "lossy"}})
        t, changes, _, _ = self.run_compare("strict")
        self.assertTrue(delta.breaches(delta.tally(changes), t))

    def test_loose_profile_tolerates_presentation_but_never_content(self):
        self.both("exact.json",
                  {"html": {"emph": "exact", "note": "exact"}},
                  {"html": {"emph": "lossy", "note": "exact"}})
        t, changes, _, _ = self.run_compare("loose")
        self.assertEqual(delta.breaches(delta.tally(changes), t), [])

        self.both("exact.json",
                  {"html": {"emph": "exact", "note": "exact"}},
                  {"html": {"emph": "exact", "note": "lossy"}})
        t, changes, _, _ = self.run_compare("loose")
        self.assertEqual(len(delta.breaches(delta.tally(changes), t)), 1)

    def test_a_missing_lane_breaches_instead_of_passing_green(self):
        """A lane that failed to be written, or a baseline directory that is
        not there, used to report zero regressions and exit 0."""
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        (self.b / "matrix.json").unlink()
        t, changes, _, structural = self.run_compare("strict")
        self.assertEqual(delta.tally(changes)["regressions"], 0)
        found = delta.breaches(delta.tally(changes), t, structural)
        self.assertTrue(any("matrix" in b for b in found), found)

    def test_a_removed_cell_breaches(self):
        self.both("exact.json", {"html": {"emph": "exact", "note": "exact"}},
                  {"html": {"emph": "exact"}})
        t, changes, _, structural = self.run_compare("strict")
        found = delta.breaches(delta.tally(changes), t, structural)
        self.assertTrue(any("note" in b for b in found), found)

    def test_an_added_cell_does_not_breach(self):
        self.both("exact.json", {"html": {"emph": "exact"}},
                  {"html": {"emph": "exact", "brand_new": "lossy"}})
        t, changes, _, structural = self.run_compare("strict")
        self.assertEqual(delta.breaches(delta.tally(changes), t, structural), [])

    def test_an_opt_in_lane_nobody_ran_does_not_breach(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        t, changes, _, structural = self.run_compare("strict")
        self.assertEqual(delta.breaches(delta.tally(changes), t, structural), [])

    def test_an_unknown_profile_is_an_error_not_a_fallback(self):
        with self.assertRaises(AssertionError):
            delta.load_thresholds(str(self.thresholds_path), "typo",
                                  lambda m: (_ for _ in ()).throw(AssertionError(m)))

    def test_an_undeclared_verdict_does_not_invent_a_regression(self):
        self.both("exact.json", {"html": {"emph": "exact"}},
                  {"html": {"emph": "sideways"}})
        t, changes, _, _ = self.run_compare("strict")
        tallied = delta.tally(changes)
        self.assertEqual(tallied["regressions"], 0)
        self.assertEqual(tallied["unknown"], 1)
        self.assertEqual(len(delta.breaches(tallied, t)), 1)


class TestMain(DeltaCase):
    """main() is what CI calls, so its exit code and its side effects are the
    contract - the report it prints is only for a human reading the log."""

    def run_main(self, extra):
        args = ["--baseline", str(self.a), "--candidate", str(self.b),
                "--thresholds", str(self.thresholds_path), "--profile", "strict"]
        with contextlib.redirect_stdout(io.StringIO()):
            return delta.main(args + extra)

    def test_exit_code_is_the_gate(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "lossy"}})
        self.assertEqual(self.run_main([]), 1)
        self.assertEqual(self.run_main(["--exit-zero"]), 0)

    def test_comparing_a_directory_with_itself_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            delta.main(["--baseline", str(self.a), "--candidate", str(self.a),
                        "--thresholds", str(self.thresholds_path),
                        "--profile", "strict"])

    def test_record_appends_one_line_per_run(self):
        self.both("exact.json", {"html": {"emph": "exact"}}, {"html": {"emph": "exact"}})
        log = pathlib.Path(self.tmp.name) / "history.jsonl"
        self.run_main(["--record", str(log)])
        self.run_main(["--record", str(log)])
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["delta"]["status"], "ok")

    def test_the_markdown_summary_names_the_direction_of_every_row(self):
        """The job summary had regressions and improvements in one table with
        nothing telling them apart, which read as all-bad."""
        self.both("exact.json", {"html": {"emph": "exact", "note": "lossy"}},
                  {"html": {"emph": "lossy", "note": "exact"}})
        md = pathlib.Path(self.tmp.name) / "s.md"
        self.run_main(["--markdown", str(md), "--exit-zero"])
        body = md.read_text(encoding="utf-8")
        self.assertIn("| worse |", body)
        self.assertIn("| better |", body)


if __name__ == "__main__":
    unittest.main()
