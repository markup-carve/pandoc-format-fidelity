import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class ReportProseTests(unittest.TestCase):
    def test_changed_measurements_update_headlines_and_comparisons(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'results').mkdir()
            (root / 'docs').mkdir()
            shutil.copytree(ROOT / 'resources', root / 'resources')
            for name in ['matrix', 'roundtrip', 'exact', 'meta', 'formats', 'run', 'carve', 'carve-rt']:
                shutil.copy(ROOT / f'results/{name}.json', root / f'results/{name}.json')

            def change(name, edit):
                path = root / f'results/{name}.json'
                data = json.loads(path.read_text())
                edit(data)
                path.write_text(json.dumps(data))

            def degrade_source(data):
                data['source'] = dict.fromkeys(data['source'], 'same')
                data['source']['emph'] = 'exact'
                data['ast'] = dict.fromkeys(data['ast'], 'same')
                data['ast']['emph'] = 'exact'
                data['ast']['strong'] = 'exact'

            change('carve', degrade_source)
            change('meta', lambda d: d.update(markdown=dict.fromkeys(d['markdown'], 'lost')))
            def one_html_feature(data):
                data['html'] = dict.fromkeys(data['html'], 'lossy')
                data['html']['emph'] = 'exact'

            change('exact', one_html_feature)
            change('matrix', lambda d: d.update(djot=dict.fromkeys(d['djot'], 'same')))
            result = subprocess.run([sys.executable, str(ROOT / 'src/gen_report.py')], cwd=root,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = (root / 'docs/index.html').read_text()
            self.assertIn('<span class="num">2 / 1</span>', output)
            self.assertIn('html returns 1', output)
            self.assertIn('scores out of ten are: markdown 0', output)
            self.assertNotIn('10.0', output)
            self.assertNotIn('None', output)
            self.assertIn('Carve source returns 0 of 16 attribute', output)
            self.assertNotIn('Carve tops the round-trip', output)
            self.assertNotIn('Carve is ahead on both counts', output)
            section = output.split('<h2>Where Carve lands</h2>')[1].split('<h3>Carve source round trips</h3>')[0]
            html_row = re.search(r'<td class="l fmt">html</td>(.*?)</tr>', section).group(1)
            self.assertEqual(re.findall(r'<b>([^<]+)</b>', html_row)[1], '1')
            self.assertIn('djot 0 /', output)
            self.assertIn('via <code>.crv</code> source, 1 and', output)
            self.assertNotIn('{{', output)
            change('meta', lambda d: d.update(markdown={'_err': 'reader failed'}))
            missing = subprocess.run([sys.executable, str(ROOT / 'src/gen_report.py')], cwd=root,
                                     capture_output=True, text=True)
            self.assertEqual(missing.returncode, 0, missing.stderr)
            output = (root / 'docs/index.html').read_text()
            self.assertIn('scores out of ten are: markdown not measured', output)
            self.assertNotIn('not measured/10', output)
            self.assertNotIn('None', output)
