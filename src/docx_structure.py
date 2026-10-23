"""Check that DOCX output carries the structure Word itself uses, not only its look.

The round-trip lanes read DOCX back through pandoc, so they cannot see what a Word
user relies on: headings in the navigation pane, lists that renumber, table headers
that repeat across pages.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

SOURCE = """\
# HEAD_ONE

## HEAD_TWO

### HEAD_THREE

- BULLET_A
- BULLET_B
    - BULLET_NESTED

1. ORDERED_A
2. ORDERED_B

| HEAD_CELL | OTHER_CELL |
|-----------|------------|
| BODY_ONE  | x          |
| BODY_TWO  | y          |
"""

HEADINGS = {'HEAD_ONE': 1, 'HEAD_TWO': 2, 'HEAD_THREE': 3}
# marker -> (list level, numbering format, list it shares a numId with)
LIST_ITEMS = {
    'BULLET_A': (0, 'bullet', 'bullet'),
    'BULLET_B': (0, 'bullet', 'bullet'),
    'BULLET_NESTED': (1, 'bullet', 'nested'),
    'ORDERED_A': (0, 'decimal', 'ordered'),
    'ORDERED_B': (0, 'decimal', 'ordered'),
}
# Per marker, plus: one numId per list, no typed markers, header row, body rows.
CHECKS = len(HEADINGS) + len(LIST_ITEMS) + 4


def text(element):
    return ''.join(t.text or '' for t in element.iter(W + 't'))


def val(element, path):
    found = element.find(path)
    return None if found is None else found.get(W + 'val')


def on(element):
    return element is not None and element.get(W + 'val', 'true') in ('true', 'on', '1')


def inspect(path):
    """Return (passed, failures) for one DOCX file."""
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read('word/document.xml'))
        styles = ET.fromstring(archive.read('word/styles.xml'))
        names = archive.namelist()
        numbering = ET.fromstring(archive.read('word/numbering.xml')) \
            if 'word/numbering.xml' in names else None

    style_names = {s.get(W + 'styleId'): (val(s, W + 'name') or '').lower()
                   for s in styles.iter(W + 'style')}
    formats = {}
    if numbering is not None:
        abstract = {a.get(W + 'abstractNumId'): {
            int(lvl.get(W + 'ilvl')): val(lvl, W + 'numFmt') for lvl in a.iter(W + 'lvl')}
            for a in numbering.iter(W + 'abstractNum')}
        for num in numbering.iter(W + 'num'):
            levels = dict(abstract.get(val(num, W + 'abstractNumId'), {}))
            # A level override is what Word displays, not the abstract definition.
            for override in num.iter(W + 'lvlOverride'):
                fmt = val(override, f'{W}lvl/{W}numFmt')
                if fmt:
                    levels[int(override.get(W + 'ilvl'))] = fmt
            formats[num.get(W + 'numId')] = levels

    paragraphs = {}
    for p in document.iter(W + 'p'):
        paragraphs.setdefault(text(p).strip(), p)

    passed = 0
    failures = []

    def expect(ok, message):
        nonlocal passed
        if ok:
            passed += 1
        else:
            failures.append(message)

    for marker, level in HEADINGS.items():
        p = paragraphs.get(marker)
        style = None if p is None else val(p, f'{W}pPr/{W}pStyle')
        name = style_names.get(style, '')
        expect(name == f'heading {level}',
               f'{marker}: expected style "heading {level}", got {name or style or "none"!r}')

    groups = {}
    for marker, (level, fmt, group) in LIST_ITEMS.items():
        p = paragraphs.get(marker)
        num = None if p is None else p.find(f'{W}pPr/{W}numPr')
        if num is None:
            expect(False, f'{marker}: no native numbering (w:numPr)')
            continue
        ilvl = int(val(num, W + 'ilvl') or 0)
        num_id = val(num, W + 'numId')
        actual = formats.get(num_id, {}).get(ilvl)
        groups.setdefault(group, set()).add(num_id)
        expect(ilvl == level and actual == fmt,
               f'{marker}: expected level {level} {fmt}, got level {ilvl} {actual}')
    expect(all(len(ids) == 1 for ids in groups.values()),
           f'list items of one list are split across numIds: {groups}')

    # The "1." of an ordered item must come from numbering.xml, never from the text.
    typed = [m for m in LIST_ITEMS if any(
        m in key and key != m for key in paragraphs)]
    expect(not typed, f'list markers typed into the text: {typed}')

    rows = next(document.iter(W + 'tbl'), ET.Element('none')).findall(W + 'tr')
    header = [on(r.find(f'{W}trPr/{W}tblHeader')) for r in rows]
    expect(bool(rows) and text(rows[0]).startswith('HEAD_CELL') and header[0],
           'table header row is not marked w:tblHeader')
    expect(len(rows) == 3 and not any(header[1:]),
           f'body rows marked as header or missing: {header}')
    return passed, failures


def check(pandoc):
    with tempfile.TemporaryDirectory(prefix='docx-structure-') as directory:
        output = Path(directory) / 'out.docx'
        try:
            subprocess.run([pandoc, '-f', 'markdown', '-t', 'docx', '-o', str(output)],
                           input=SOURCE, check=True, capture_output=True, text=True,
                           timeout=30)
        except subprocess.TimeoutExpired:
            raise AssertionError('DOCX structure: writer timed out after 30 seconds')
        except subprocess.CalledProcessError as error:
            raise AssertionError(f'DOCX structure: writer exited {error.returncode}: {error.stderr}')
        passed, failures = inspect(output)
    if failures:
        raise AssertionError(f'DOCX structure: {passed}/{CHECKS} passed\n' + '\n'.join(failures))
    return passed


if __name__ == '__main__':
    binary = os.environ.get('PANDOC', './vendor/pandoc/bin/pandoc')
    try:
        print(f'DOCX structure: {check(binary)}/{CHECKS} passed')
    except (AssertionError, OSError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
