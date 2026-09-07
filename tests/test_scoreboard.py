"""The scoreboard is the single reading three things quote, so its arithmetic
is worth pinning: the dashboard, the history line and the delta's record all
read the same numbers from here."""
import json
import pathlib
import tempfile
import unittest

import scoreboard
from probes import PROBES


def lane_for(fmt, verdict):
    return {fmt: {n: verdict for n in PROBES}}


class TestScoreboard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, obj):
        (self.d / name).write_text(json.dumps(obj), encoding="utf-8")

    def test_a_format_that_keeps_everything_scores_full(self):
        self.write("matrix.json", lane_for("perfect", "diff"))
        self.write("roundtrip.json", lane_for("perfect", "diff"))
        self.write("exact.json", lane_for("perfect", "exact"))
        self.write("meta.json", {"perfect": {k: "exact" for k in scoreboard.MKEYS}})
        row = scoreboard.rows(self.d)["perfect"]
        self.assertEqual(row["expressed"], len(PROBES))
        self.assertEqual(row["exact"], len(PROBES))
        self.assertEqual(row["meta"], 10)
        self.assertEqual(row["semantic_content"]["pct"], 100.0)

    def test_a_format_that_keeps_nothing_scores_zero(self):
        self.write("matrix.json", lane_for("hopeless", "same"))
        self.write("roundtrip.json", lane_for("hopeless", "same"))
        self.write("exact.json", lane_for("hopeless", "lossy"))
        self.write("meta.json", {"hopeless": {k: "lost" for k in scoreboard.MKEYS}})
        row = scoreboard.rows(self.d)["hopeless"]
        self.assertEqual(row["expressed"], 0)
        self.assertEqual(row["semantic_content"]["pct"], 0.0)

    def test_canonical_counts_as_content_kept_but_not_as_exact(self):
        """The whole reason the exact lane has three verdicts: a restyled
        document still came home."""
        self.write("matrix.json", lane_for("restyler", "diff"))
        self.write("exact.json", lane_for("restyler", "canonical"))
        self.write("roundtrip.json", lane_for("restyler", "diff"))
        self.write("meta.json", {})
        row = scoreboard.rows(self.d)["restyler"]
        self.assertEqual(row["exact"], 0)
        self.assertEqual(row["canonical"], len(PROBES))
        self.assertEqual(row["semantic_exact"]["pct"], 0.0)
        self.assertEqual(row["semantic_content"]["pct"], 100.0)

    def test_metadata_partial_is_half_a_key(self):
        self.assertEqual(
            scoreboard.meta_score({k: ("exact" if i < 4 else "partial")
                                   for i, k in enumerate(scoreboard.MKEYS)}), 7.0)

    def test_a_format_that_could_not_be_measured_scores_none_not_zero(self):
        """None keeps an unmeasurable row out of the medians. Zero would drag
        the trend line down and make it a statement about the machine."""
        self.assertIsNone(scoreboard.meta_score({"_err": "no TeX engine"}))
        self.assertIsNone(scoreboard.meta_score(None))

    def test_the_ast_serializations_are_not_rows(self):
        self.write("matrix.json", {**lane_for("json", "diff"), **lane_for("html", "diff")})
        self.write("exact.json", {})
        self.write("roundtrip.json", {})
        self.write("meta.json", {})
        self.assertEqual(sorted(scoreboard.rows(self.d)), ["html"])

    def test_aggregate_uses_medians_and_ignores_the_unmeasurable(self):
        rws = {
            "a": {"expressed": 10, "readable": True, "exact": 10, "roundtrip": 10,
                  "meta": 10, "semantic_content": {"pct": 90.0}},
            "b": {"expressed": 20, "readable": True, "exact": 20, "roundtrip": 20,
                  "meta": None, "semantic_content": {"pct": 50.0}},
            "c": {"expressed": 30, "readable": False, "exact": None,
                  "roundtrip": None, "meta": None, "semantic_content": None},
        }
        agg = scoreboard.aggregate(rws)
        self.assertEqual(agg["formats"], 3)
        self.assertEqual(agg["readable"], 2)
        self.assertEqual(agg["expressed_median"], 20)
        self.assertEqual(agg["meta_median"], 10)
        self.assertEqual(agg["semantic_pct_median"], 70.0)


if __name__ == "__main__":
    unittest.main()
