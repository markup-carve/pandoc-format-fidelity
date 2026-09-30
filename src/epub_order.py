"""Check EPUB spine order independently of content-fidelity scores."""
import itertools
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

CASES = tuple(itertools.product([2, 3], [False, True], [False, True], [False, True]))


def fixture(path, version, spine, manifest, entries):
    items = ''.join(
        f'<item id="{name}" href="{name}.xhtml" media-type="application/xhtml+xml"/>'
        for name in manifest)
    items += '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    if version == 3:
        items += '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    modified = '<meta property="dcterms:modified">2026-09-30T00:00:00Z</meta>' if version == 3 else ''
    opf = (
        f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="uid">urn:test:spine</dc:identifier><dc:title>Order</dc:title>'
        f'<dc:language>en</dc:language>{modified}</metadata><manifest>{items}</manifest>'
        '<spine toc="ncx">' + ''.join(f'<itemref idref="{name}"/>' for name in spine)
        + '</spine></package>')
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        archive.writestr('META-INF/container.xml',
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
            '<rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>')
        archive.writestr('book.opf', opf)
        archive.writestr('toc.ncx',
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            '<head><meta name="dtb:uid" content="urn:test:spine"/></head>'
            '<docTitle><text>Order</text></docTitle><navMap>' + ''.join(
                f'<navPoint id="p{i}" playOrder="{i}"><navLabel><text>{name}</text></navLabel>'
                f'<content src="{name}.xhtml"/></navPoint>'
                for i, name in enumerate(['z', 'a'], 1)) + '</navMap></ncx>')
        if version == 3:
            archive.writestr('nav.xhtml',
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
                '<head><title>Navigation</title></head><body><nav epub:type="toc"><ol>'
                '<li><a href="z.xhtml">Z</a></li><li><a href="a.xhtml">A</a></li>'
                '</ol></nav></body></html>')
        for name in entries:
            archive.writestr(f'{name}.xhtml',
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter</title></head>'
                f'<body><p>{name.upper()}_ORDER_MARKER</p></body></html>')


def check(pandoc):
    count = 0
    failures = []
    with tempfile.TemporaryDirectory(prefix='epub-order-') as directory:
        for version, s, m, z in CASES:
            spine = ['a', 'z'] if s else ['z', 'a']
            manifest = ['z', 'a'] if m else ['a', 'z']
            entries = ['z', 'a'] if z else ['a', 'z']
            path = Path(directory) / f'v{version}-s{int(s)}-m{int(m)}-z{int(z)}.epub'
            fixture(path, version, spine, manifest, entries)
            try:
                result = subprocess.run([pandoc, '-f', 'epub', '-t', 'plain', str(path)],
                                        check=True, capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired:
                failures.append(f'{path.name}: reader timed out after 30 seconds')
                continue
            except subprocess.CalledProcessError as error:
                failures.append(f'{path.name}: reader exited {error.returncode}: {error.stderr}')
                continue
            actual = result.stdout.split()
            expected = [f'{name.upper()}_ORDER_MARKER' for name in spine]
            if actual != expected:
                failures.append(f'{path.name}: expected {expected}, got {actual}')
                continue
            count += 1
    if failures:
        raise AssertionError(f'EPUB spine order: {count}/{len(CASES)} passed\n' + '\n'.join(failures))
    return count


if __name__ == '__main__':
    binary = os.environ.get('PANDOC', './vendor/pandoc/bin/pandoc')
    try:
        print(f'EPUB spine order: {check(binary)}/{len(CASES)} passed')
    except (AssertionError, OSError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
