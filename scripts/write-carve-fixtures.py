"""Write fixtures/carve/*.crv.

The fixtures are source files, not generated artifacts - this script exists so
they can be written in one reviewable place with their bytes exact (a heredoc
mangles backslashes and a hand edit drifts the trailing newlines, and both show
up as round-trip noise the lane would report as loss).

Run it once when adding a construct; the .crv files are what the lane reads.
"""
import pathlib

DEST = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "carve"

# One construct per file, in the smallest document that carries it. Anything
# else in the file is a second feature the verdict cannot separate from the
# first, which is the same discipline the pandoc probes follow.
FIXTURES = {
    "emphasis": "/italic/ and *bold* and _underline_ in a line.\n",
    "strike-highlight": "~struck~ and =highlighted= in a line.\n",
    "bold-italic": "A /*bold italic*/ run.\n",
    "sup-sub": "H{,2,}O and mc{^2^}.\n",
    "code-inline": "Call `render()` on it.\n",
    "link": "A [labelled link](https://example.com) in prose.\n",
    "link-title": 'A [labelled link](https://example.com "Tooltip") in prose.\n',
    "autolink": "Bare <https://example.com> in prose.\n",
    "image": "![A grey square](i.png)\n",
    "heading": "## A second-level heading\n",
    "heading-attrs": "{#anchor .lead}\n## A second-level heading\n",
    "bullet-list": "- first\n- second\n",
    "ordered-list": ". first\n. second\n",
    "nested-list": "- first\n  - nested\n- second\n",
    "task-list": "- [ ] open\n- [x] done\n",
    "definition-list": ":: term\n: the definition\n",
    "blockquote": "> quoted prose\n",
    "code-block": "```python\nx = 1\n```\n",
    "code-block-header": '```python "config.py"\nx = 1\n```\n',
    "raw-html": "```=html\n<hr class=rule>\n```\n",
    "table": "|= Head A |= Head B |\n| a | b |\n| c | d |\n",
    "table-align": "|=> Right |=~ Center |\n| a | b |\n",
    "table-caption": "|= Head A |= Head B |\n| a | b |\n^ A caption\n",
    "table-span": "|= Head A |= Head B |\n| a < |\n| c | d |\n",
    "admonition": "::: note \"Take note\"\nBody of the note.\n:::\n",
    "quote-container": "::: >\nquoted prose\n:::\n",
    "footnote": "Text with a marker.[^1]\n\n[^1]: The footnote body.\n",
    "inline-footnote": "Text with a marker.^[The footnote body.]\n",
    "math-inline": "Euler: $`e^{i\\pi}+1=0`\n",
    "math-display": "$$`\\int_0^1 x\\,dx`\n",
    "span-attrs": "A [marked run]{.highlight} in prose.\n",
    "thematic-break": "before\n\n---\n\nafter\n",
    "frontmatter": "---\ntitle: A title\n---\n\nBody prose.\n",
    "editorial-insert": "An {+inserted+} word.\n",
    "editorial-delete": "A {-deleted-} word.\n",
    "editorial-substitute": "A {~old~>new~} word.\n",
    "comment": "Visible prose. %% a comment\n",
    "crossref": "{#target}\n## A target heading\n\nSee </#target>.\n",
    "hard-break": "first line\\\nsecond line\n",
    "caption-image": "![A grey square](i.png)\n^ A caption\n",
}


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(FIXTURES.items()):
        (DEST / (name + ".crv")).write_text(text, encoding="utf-8")
    print("wrote %d fixtures to %s" % (len(FIXTURES), DEST))


if __name__ == "__main__":
    main()
