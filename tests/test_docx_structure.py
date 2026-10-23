import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from docx_structure import CHECKS, check, inspect

NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def para(text, style=None, num=None):
    ppr = ''
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if num:
        ppr += f'<w:numPr><w:ilvl w:val="{num[0]}"/><w:numId w:val="{num[1]}"/></w:numPr>'
    return f'<w:p><w:pPr>{ppr}</w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'


def tr(cells, header=False):
    trpr = '<w:trPr><w:tblHeader/></w:trPr>' if header else ''
    return '<w:tr>' + trpr + ''.join(f'<w:tc>{para(c)}</w:tc>' for c in cells) + '</w:tr>'


HEADINGS = [para('HEAD_ONE', 'Heading1'), para('HEAD_TWO', 'Heading2'),
            para('HEAD_THREE', 'Heading3')]
LISTS = [para('BULLET_A', num=(0, 1)), para('BULLET_B', num=(0, 1)),
         para('BULLET_NESTED', num=(1, 2)),
         para('ORDERED_A', num=(0, 3)), para('ORDERED_B', num=(0, 3))]
TABLE = [tr(['HEAD_CELL', 'OTHER_CELL'], header=True), tr(['BODY_ONE', 'x']),
         tr(['BODY_TWO', 'y'])]
STYLES = ''.join(f'<w:style w:styleId="Heading{n}"><w:name w:val="heading {n}"/></w:style>'
                 for n in (1, 2, 3))
NUMBERING = (
    '<w:abstractNum w:abstractNumId="10"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>'
    '<w:lvl w:ilvl="1"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>'
    '<w:abstractNum w:abstractNumId="20"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>'
    '</w:abstractNum>'
    '<w:num w:numId="1"><w:abstractNumId w:val="10"/></w:num>'
    '<w:num w:numId="2"><w:abstractNumId w:val="10"/></w:num>'
    '<w:num w:numId="3"><w:abstractNumId w:val="20"/></w:num>')


def build(path, headings=HEADINGS, lists=LISTS, table=TABLE, styles=STYLES,
          numbering=NUMBERING):
    body = ''.join(headings + lists) + '<w:tbl>' + ''.join(table) + '</w:tbl>'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', f'<w:document {NS}><w:body>{body}</w:body></w:document>')
        archive.writestr('word/styles.xml', f'<w:styles {NS}>{styles}</w:styles>')
        if numbering is not None:
            archive.writestr('word/numbering.xml', f'<w:numbering {NS}>{numbering}</w:numbering>')


class DocxStructureTests(unittest.TestCase):
    def run_inspect(self, **parts):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'doc.docx'
            build(path, **parts)
            return inspect(path)

    def test_native_structure_passes_every_check(self):
        self.assertEqual(self.run_inspect(), (CHECKS, []))

    def test_heading_by_direct_formatting_fails(self):
        passed, failures = self.run_inspect(
            headings=[para('HEAD_ONE', 'Title'), *HEADINGS[1:]])
        self.assertEqual(passed, CHECKS - 1)
        self.assertIn('HEAD_ONE', failures[0])

    def test_heading_style_is_resolved_by_name_not_id(self):
        styles = STYLES.replace('w:styleId="Heading1"', 'w:styleId="Berschrift1"')
        passed, failures = self.run_inspect(
            headings=[para('HEAD_ONE', 'Berschrift1'), *HEADINGS[1:]], styles=styles)
        self.assertEqual(failures, [])

    def test_typed_list_markers_fail(self):
        lists = LISTS[:3] + [para('1. ORDERED_A'), para('2. ORDERED_B')]
        passed, failures = self.run_inspect(lists=lists)
        self.assertTrue(any('ORDERED_A: no native numbering' in f for f in failures))
        self.assertTrue(any('typed into the text' in f for f in failures))

    def test_wrong_format_or_level_fails(self):
        lists = LISTS[:2] + [para('BULLET_NESTED', num=(0, 2))] + LISTS[3:]
        passed, failures = self.run_inspect(lists=lists)
        self.assertEqual(len(failures), 1)
        self.assertIn('BULLET_NESTED', failures[0])
        numbering = NUMBERING.replace('w:val="decimal"', 'w:val="bullet"')
        passed, failures = self.run_inspect(numbering=numbering)
        self.assertEqual(len(failures), 2)

    def test_level_override_wins_over_abstract_format(self):
        numbering = NUMBERING.replace(
            '<w:num w:numId="3"><w:abstractNumId w:val="20"/></w:num>',
            '<w:num w:numId="3"><w:abstractNumId w:val="20"/><w:lvlOverride w:ilvl="0">'
            '<w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:lvlOverride></w:num>')
        passed, failures = self.run_inspect(numbering=numbering)
        self.assertEqual(len(failures), 2)
        self.assertTrue(all('decimal, got level 0 bullet' in f for f in failures))

    def test_list_split_across_numids_fails(self):
        lists = [LISTS[0], para('BULLET_B', num=(0, 2))] + LISTS[2:]
        passed, failures = self.run_inspect(lists=lists)
        self.assertTrue(any('split across numIds' in f for f in failures))

    def test_missing_numbering_part_fails(self):
        passed, failures = self.run_inspect(numbering=None)
        self.assertEqual(len([f for f in failures if 'level' in f]), 5)

    def test_table_header_row_must_be_marked(self):
        table = [tr(['HEAD_CELL', 'OTHER_CELL']), *TABLE[1:]]
        passed, failures = self.run_inspect(table=table)
        self.assertEqual(failures, ['table header row is not marked w:tblHeader'])
        table = [TABLE[0], tr(['BODY_ONE', 'x'], header=True), TABLE[2]]
        passed, failures = self.run_inspect(table=table)
        self.assertEqual(len(failures), 1)
        self.assertIn('body rows', failures[0])

    def test_writer_error_fails(self):
        with patch('docx_structure.subprocess.run', side_effect=
                   subprocess.CalledProcessError(1, 'test-pandoc', stderr='writer failure')):
            with self.assertRaisesRegex(AssertionError, 'writer failure'):
                check('test-pandoc')

    def test_writer_timeout_fails(self):
        with patch('docx_structure.subprocess.run', side_effect=
                   subprocess.TimeoutExpired('test-pandoc', 30)):
            with self.assertRaisesRegex(AssertionError, 'timed out after 30 seconds'):
                check('test-pandoc')
