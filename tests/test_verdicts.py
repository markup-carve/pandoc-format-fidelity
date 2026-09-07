"""The ranking is what makes "regression" mean anything, so it gets pinned."""
import unittest

import verdicts


class TestVerdicts(unittest.TestCase):
    def test_every_lane_declares_its_ideal(self):
        for lane, spec in verdicts.LANES.items():
            self.assertIn(spec["ideal"], spec["rank"], lane)
            self.assertEqual(
                spec["rank"][spec["ideal"]], max(spec["rank"].values()),
                "%s: the ideal verdict has to be the top rank" % lane)

    def test_err_ranks_below_every_substantive_verdict(self):
        for lane, spec in verdicts.LANES.items():
            if "err" not in spec["rank"]:
                continue
            self.assertEqual(spec["rank"]["err"], min(spec["rank"].values()), lane)

    def test_direction(self):
        self.assertEqual(verdicts.direction("exact", "exact", "lossy"), "worse")
        self.assertEqual(verdicts.direction("exact", "lossy", "exact"), "better")
        self.assertEqual(verdicts.direction("exact", "lossy", "lossy"), "same")
        self.assertEqual(verdicts.direction("matrix", "diff", "same"), "worse")
        self.assertEqual(verdicts.direction("meta", "partial", "exact"), "better")

    def test_canonical_sits_between_lossy_and_exact(self):
        r = verdicts.LANES["exact"]["rank"]
        self.assertLess(r["lossy"], r["canonical"])
        self.assertLess(r["canonical"], r["exact"])

    def test_an_undeclared_verdict_is_unknown_not_zero(self):
        """Scoring an unknown string as the worst rank would invent a
        regression out of a typo or a new verdict."""
        self.assertIsNone(verdicts.rank("exact", "sideways"))
        self.assertEqual(verdicts.direction("exact", "exact", "sideways"), "unknown")

    def test_cells_skips_the_error_bookkeeping(self):
        data = {"html": {"emph": "exact", "_errs": ["noise"]},
                "_meta": "not a format row"}
        self.assertEqual(sorted(verdicts.cells(data, "exact")),
                         [("html", "emph", "exact")])


if __name__ == "__main__":
    unittest.main()
