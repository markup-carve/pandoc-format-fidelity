"""The severity rubric has to cover the probe set exactly, or a score lies.

A probe with no class would either crash a lookup or, worse, be quietly
weighted as zero and drop out of the total - which reads as a format losing
nothing.
"""
import unittest

import severity
from probes import PROBES


class TestSeverity(unittest.TestCase):
    def test_every_probe_is_classified(self):
        self.assertEqual(severity.check(), [])

    def test_weights_are_ordered(self):
        self.assertGreater(severity.WEIGHT["content"], severity.WEIGHT["structure"])
        self.assertGreater(severity.WEIGHT["structure"],
                           severity.WEIGHT["presentation"])

    def test_totals_add_up(self):
        t = severity.totals()
        self.assertEqual(t["all"]["probes"], len(PROBES))
        self.assertEqual(
            t["all"]["weight"],
            sum(t[c]["weight"] for c in severity.CLASSES))

    def test_keeping_everything_scores_full(self):
        s = severity.score(set(PROBES))
        self.assertEqual(s["weight"], s["total"])
        self.assertEqual(s["pct"], 100.0)

    def test_keeping_nothing_scores_zero(self):
        s = severity.score(set())
        self.assertEqual(s["weight"], 0)
        self.assertEqual(s["pct"], 0.0)

    def test_content_outweighs_presentation(self):
        """The whole point of the rubric: losing a footnote body has to cost
        more than losing a column's alignment."""
        keep_all_but_note = set(PROBES) - {"note"}
        keep_all_but_align = set(PROBES) - {"table_align"}
        self.assertLess(severity.score(keep_all_but_note)["weight"],
                        severity.score(keep_all_but_align)["weight"])


if __name__ == "__main__":
    unittest.main()
