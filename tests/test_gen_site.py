import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import gen_site
import scoreboard
from probes import PROBES

ROOT = Path(__file__).resolve().parent.parent


class SiteTests(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "dist"
            data = gen_site.build(ROOT / "results", output)
            expected = scoreboard.read(ROOT / "results")
            self.assertEqual(data["totals"], expected["totals"])
            self.assertEqual(set(data["rows"]), set(expected["rows"]))
            self.assertEqual([p["name"] for p in data["probes"]], list(PROBES))
            for key in ("matrix", "roundtrip", "exact"):
                raw = json.loads((ROOT / "results" / gen_site.LANES[key]["file"]).read_text())
                self.assertEqual(data["lanes"][key]["grid"], raw)
                for row in data["lanes"][key]["grid"].values():
                    self.assertTrue(set(PROBES) <= set(row))
            raw_meta = json.loads((ROOT / "results/meta.json").read_text())
            failed = {f for f, row in raw_meta.items() if "_err" in row}
            self.assertEqual(set(data["lanes"]["meta"]["errors"]), failed)
            for fmt in failed:
                self.assertEqual(set(data["lanes"]["meta"]["grid"][fmt].values()), {"err"})
            self.assertNotIn("/tmp/", data["carve_rt"].get("bridge", ""))
            self.assertEqual(data["carve_rt"].get("warnings"), json.loads((ROOT / "results/carve-rt.json").read_text())["warnings"])
            html = (output / "index.html").read_text()
            self.assertRegex(html, r'app.js\?v=[a-f0-9]{12}')
            self.assertRegex(html, r'style.css\?v=[a-f0-9]{12}')
            for source in (ROOT / "results").glob("*.json"):
                self.assertEqual(source.read_bytes(), (output / "data" / source.name).read_bytes())
            self.assertTrue((output / "report.html").exists())

    def test_missing_files_and_probe_mismatch(self):
        for name in ("run.json", "matrix.json", "roundtrip.json", "exact.json", "meta.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp) / "results"
                shutil.copytree(ROOT / "results", directory)
                (directory / name).unlink()
                result = subprocess.run([sys.executable, str(ROOT / "src/gen_site.py"), "--results", str(directory), "--output", str(Path(temp) / "dist")], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name, result.stderr)
                self.assertIn("missing required input", result.stderr)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "results"
            shutil.copytree(ROOT / "results", directory)
            path = directory / "matrix.json"
            data = json.loads(path.read_text())
            del data[next(iter(data))][next(iter(PROBES))]
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "keys disagree"):
                gen_site.document(directory)

    def test_optional_carve(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "results"
            shutil.copytree(ROOT / "results", directory)
            for name in ("carve.json", "carve-rt.json"):
                (directory / name).unlink()
            data = gen_site.build(directory, Path(temp) / "dist")
            self.assertFalse(data["carve"]["measured"])
            self.assertFalse(data["carve_rt"]["measured"])
            self.assertNotIn("carve", data["lanes"])
