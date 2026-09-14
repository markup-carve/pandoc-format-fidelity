"""The stamp is the file everything else's provenance rests on.

The case these pin is real: on 2026-09-08 the nightly watch measured a build
calling itself `3.10.2-nightly-2026-08-16`, pulled from an upstream run created
that morning, and filed a whole night's numbers three weeks early. The banner
was the only thing the stamp knew, so nothing could notice.
"""
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import run_env


class TestBannerDate(unittest.TestCase):
    def test_a_nightly_names_itself_after_a_date(self):
        self.assertEqual(
            run_env.banner_date("pandoc 3.10.2-nightly-2026-08-16"), "2026-08-16")

    def test_a_release_names_no_date(self):
        self.assertIsNone(run_env.banner_date("pandoc 3.11"))

    def test_no_banner_is_not_a_crash(self):
        self.assertIsNone(run_env.banner_date(None))


class TestSource(unittest.TestCase):
    def test_nothing_set_records_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(run_env.source())

    def test_blank_is_the_same_as_unset(self):
        """A workflow that resolves an empty run id must not look like it
        knows where the build came from."""
        with mock.patch.dict(os.environ, {"PANDOC_SOURCE_RUN": "  "}, clear=True):
            self.assertIsNone(run_env.source())

    def test_what_is_set_is_recorded(self):
        with mock.patch.dict(os.environ, {"PANDOC_SOURCE_RUN": "123",
                                          "PANDOC_SOURCE_REF": "abc"}, clear=True):
            self.assertEqual(run_env.source(), {"run": "123", "ref": "abc"})


class TestStamp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "run.json"
        self.addCleanup(self.tmp.cleanup)

    def stamp(self, banner, env):
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(run_env, "OUT", self.out), \
                mock.patch.object(run_env, "pandoc_banner", lambda: banner), \
                contextlib.redirect_stdout(io.StringIO()):
            run_env.main()
        return json.loads(self.out.read_text(encoding="utf-8"))["pandoc"]

    def test_a_build_that_misnames_itself_is_flagged(self):
        got = self.stamp("pandoc 3.10.2-nightly-2026-08-16",
                         {"PANDOC_SOURCE_RUN": "34201713587",
                          "PANDOC_SOURCE_DATE": "2026-09-08T07:54:40Z"})
        self.assertTrue(got["source"]["stale_banner"])
        self.assertEqual(got["source"]["names_itself"], "2026-08-16")

    def test_a_build_that_agrees_with_its_run_is_not_flagged(self):
        got = self.stamp("pandoc 3.11-nightly-2026-09-08",
                         {"PANDOC_SOURCE_RUN": "34201713587",
                          "PANDOC_SOURCE_DATE": "2026-09-08T07:54:40Z"})
        self.assertNotIn("stale_banner", got["source"])

    def test_a_release_with_no_source_records_no_source(self):
        got = self.stamp("pandoc 3.11", {})
        self.assertNotIn("source", got)

    def test_a_source_with_no_date_cannot_contradict_the_banner(self):
        """Half the information is not grounds for calling a build wrong."""
        got = self.stamp("pandoc 3.10.2-nightly-2026-08-16",
                         {"PANDOC_SOURCE_RUN": "1"})
        self.assertNotIn("stale_banner", got["source"])


if __name__ == "__main__":
    unittest.main()
