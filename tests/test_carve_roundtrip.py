import json
import os
import pathlib
import runpy
import shutil
import subprocess
import tempfile
import unittest

from gen_dashboard import table_carve_rt

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestCarveRoundtrip(unittest.TestCase):
    def test_fixture_generator_matches_committed_inputs(self):
        fixtures = runpy.run_path(str(ROOT / 'scripts' / 'write-carve-fixtures.py'))['FIXTURES']
        committed = {p.stem: p.read_text() for p in (ROOT / 'fixtures' / 'carve').glob('*.crv')}
        self.assertEqual(fixtures, committed)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the Carve runner')
    def test_preservation_options_do_not_reach_export_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'src').mkdir()
            (root / 'results').mkdir()
            (root / 'fixtures' / 'carve').mkdir(parents=True)
            for name in ('run_carve_rt.mjs', 'checkout_revision.mjs'):
                shutil.copy(ROOT / 'src' / name, root / 'src' / name)
            source = 'Visible prose. %% a comment\n'
            (root / 'fixtures' / 'carve' / 'comment.crv').write_text(source)
            (root / 'fixtures' / 'carve' / 'failure.crv').write_text('FAIL')
            (root / 'fixtures' / 'carve' / 'warning.crv').write_text('WARN')
            (root / 'fixtures' / 'carve' / 'all-failure.crv').write_text('ALLFAIL')
            bridge = root / 'bridge.mjs'
            bridge.write_text('''
export function carveToPandoc(source, options = {}) {
    if (source === 'ALLFAIL') throw new Error('forward failure');
    if (source === 'FAIL' && options.roundtrip) throw new Error('preserve failure');
    return {doc: {source, options, blocks: [], meta: {}},
            warnings: source === 'WARN' ? ['forward warning'] : options.roundtrip ? [] : ['comment dropped']};
}
export function pandocToCarve(doc) {
    return {carve: doc.options.roundtrip ? doc.source : 'Visible prose.\\n',
            warnings: doc.source === 'WARN' ? ['reverse warning'] : []};
}
export function carveToCarveAst(source) { return {source}; }
''')
            pandoc = root / 'pandoc'
            pandoc.write_text('''#!/usr/bin/env python3
import sys
if '--version' in sys.argv:
    print('pandoc test double')
else:
    sys.stdout.write(sys.stdin.read())
''')
            pandoc.chmod(0o755)
            env = {**os.environ, 'CARVE_BRIDGE': str(bridge),
                   'PANDOC': str(pandoc), 'CARVE_RT_FORMATS': 'html'}
            subprocess.run(['node', str(root / 'src' / 'run_carve_rt.mjs')],
                           env=env, check=True, capture_output=True, text=True)
            data = json.loads((root / 'results' / 'carve-rt.json').read_text())
            self.assertEqual(data['lanes']['bridge-preserve']['comment'], 'exact')
            self.assertEqual(data['preserveOutput']['comment'], source)
            self.assertNotIn('comment', data['preserveWarnings'])
            self.assertEqual(data['warnings']['comment'], ['comment dropped'])
            self.assertEqual(data['lanes']['html']['comment'], data['lanes']['bridge']['comment'])
            self.assertNotEqual(data['lanes']['html']['comment'], 'exact')
            self.assertEqual(data['laneOptions']['bridge-preserve'], {'roundtrip': True})
            self.assertEqual(data['preserveWarnings']['warning'], ['forward warning', 'reverse warning'])
            self.assertEqual(data['warnings']['warning'], ['forward warning', 'reverse warning'])
            self.assertEqual(data['lanes']['bridge-preserve']['failure'], 'err')
            self.assertEqual(data['errors']['bridge-preserve']['failure'],
                             {'stage': 'carveToPandoc', 'message': 'preserve failure'})
            self.assertIn('carveToPandoc:', data['preserveOutput']['failure'])
            self.assertEqual(data['errors']['html']['all-failure'],
                             {'stage': 'carveToPandoc', 'message': 'forward failure'})

    def test_dashboard_labels_preservation_and_ragged_rows(self):
        data = {'fixtures': {'comment': {}, 'table-ragged': {}, 'table-span': {}, 'table-rowspan': {}}, 'formats': [],
                'lanes': {'bridge': {'comment': 'respelled', 'table-ragged': 'lossy'},
                          'bridge-preserve': {'comment': 'exact', 'table-ragged': 'lossy'}}}
        html = table_carve_rt(data)
        self.assertIn('bridge-preserve', html)
        self.assertIn('roundtrip: true', html)
        self.assertIn('table-ragged tests a short row', html)
        self.assertIn('Export-format rows use the default bridge options', html)
        del data['fixtures']['table-rowspan']
        self.assertNotIn('table-ragged tests a short row', table_carve_rt(data))

    def test_older_results_do_not_show_an_unmeasured_preservation_lane(self):
        html = table_carve_rt({'fixtures': {'comment': {}}, 'formats': [],
                              'lanes': {'bridge': {'comment': 'respelled'}}})
        self.assertNotIn('bridge-preserve', html)
