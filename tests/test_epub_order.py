import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile
from xml.etree import ElementTree as ET

from epub_order import check, fixture


class EpubOrderTests(unittest.TestCase):
    def test_fixture_orders_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'order.epub'
            fixture(path, 3, ['z', 'a'], ['a', 'z'], ['a', 'z'])
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.namelist()[0], 'mimetype')
                self.assertEqual(archive.getinfo('mimetype').compress_type, zipfile.ZIP_STORED)
                self.assertEqual([n for n in archive.namelist() if n in ['a.xhtml', 'z.xhtml']],
                                 ['a.xhtml', 'z.xhtml'])
                package = ET.fromstring(archive.read('book.opf'))
                ns = {'opf': 'http://www.idpf.org/2007/opf'}
                self.assertEqual([i.attrib['idref'] for i in package.findall('opf:spine/opf:itemref', ns)],
                                 ['z', 'a'])
                self.assertEqual([i.attrib['id'] for i in package.findall('opf:manifest/opf:item', ns)][:2],
                                 ['a', 'z'])

    def test_correct_reader_runs_all_sixteen_cases(self):
        def reader(args, **kwargs):
            with zipfile.ZipFile(args[-1]) as archive:
                package = ET.fromstring(archive.read('book.opf'))
                spine = package.find('{http://www.idpf.org/2007/opf}spine')
                output = '\n'.join(i.attrib['idref'].upper() + '_ORDER_MARKER' for i in spine)
                return subprocess.CompletedProcess(args, 0, output, '')
        with patch('epub_order.subprocess.run', side_effect=reader) as run:
            self.assertEqual(check('test-pandoc'), 16)
            self.assertEqual(run.call_count, 16)

    def test_wrong_order_missing_and_duplicate_content_fail(self):
        for output in ['A_ORDER_MARKER Z_ORDER_MARKER', 'Z_ORDER_MARKER',
                       'Z_ORDER_MARKER A_ORDER_MARKER A_ORDER_MARKER']:
            with self.subTest(output=output):
                with patch('epub_order.subprocess.run', return_value=
                           subprocess.CompletedProcess([], 0, output, '')):
                    with self.assertRaises(AssertionError):
                        check('test-pandoc')

    def test_reader_error_fails(self):
        with patch('epub_order.subprocess.run', side_effect=
                   subprocess.CalledProcessError(1, 'test-pandoc', stderr='reader failure')) as run:
            with self.assertRaisesRegex(AssertionError, 'reader failure'):
                check('test-pandoc')
            self.assertEqual(run.call_count, 16)

    def test_reader_timeout_fails_without_skipping_later_cases(self):
        with patch('epub_order.subprocess.run', side_effect=
                   subprocess.TimeoutExpired('test-pandoc', 30)) as run:
            with self.assertRaisesRegex(AssertionError, 'timed out after 30 seconds'):
                check('test-pandoc')
            self.assertEqual(run.call_count, 16)
