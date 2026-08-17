"""Pandoc element-coverage probes.

Each probe is a pair (rich, degraded) of pandoc AST block lists that differ in
exactly one feature. The pair is the whole method: if a writer emits the same
bytes for both, the format cannot express that feature, and no amount of input
normalization changes that -- both sides went through the same writer with the
same options, so whatever canonical styling it applies is applied to both.

    rich      an AST that uses the feature
    degraded  the nearest AST that does not

`rich` is also compared against itself after a round-trip, which is the one
lane where canonicalization matters; see run_exact.py.
"""

API = [1, 23, 1, 2]

def S(s):
    return {"t": "Str", "c": s}

def SP():
    return {"t": "Space"}

def para(*inl):
    return {"t": "Para", "c": list(inl)}

def plain(*inl):
    return {"t": "Plain", "c": list(inl)}

def attr(i="", cls=None, kv=None):
    return [i, cls or [], [[k, v] for k, v in (kv or [])]]

NULLATTR = attr()

def cell(blocks, rowspan=1, colspan=1, a=None, align="AlignDefault"):
    return [a or NULLATTR, {"t": align}, rowspan, colspan, blocks]

def row(cells, a=None):
    return [a or NULLATTR, cells]

def body(rows, rowheadcols=0):
    return [NULLATTR, rowheadcols, [], rows]

def table(head_rows, body_rows, foot_rows=None, caption=None,
          colspecs=None, ncol=2, a=None, rowheadcols=0):
    colspecs = colspecs or [[{"t": "AlignDefault"}, {"t": "ColWidthDefault"}]] * ncol
    return {"t": "Table", "c": [
        a or NULLATTR,
        [None, caption or []],
        colspecs,
        [NULLATTR, [row(c) for c in head_rows]],
        [body([row(c) for c in body_rows], rowheadcols)],
        [NULLATTR, [row(c) for c in (foot_rows or [])]],
    ]}

def tcell(txt, **kw):
    return cell([plain(S(txt))], **kw)

TXT = S("alpha")
TXT2 = S("beta")

def simple_body(n=2):
    return [[tcell("a"), tcell("b")], [tcell("c"), tcell("d")]][:n]

PROBES = {}

def P(name, rich, degraded, group):
    PROBES[name] = {"rich": rich, "degraded": degraded, "group": group}

# ---------------- inline formatting ----------------
for nm, t in [("emph", "Emph"), ("strong", "Strong"), ("underline", "Underline"),
              ("strikeout", "Strikeout"), ("superscript", "Superscript"),
              ("subscript", "Subscript"), ("smallcaps", "SmallCaps")]:
    P(nm, [para({"t": t, "c": [TXT]})], [para(TXT)], "inline")

P("quoted_double", [para({"t": "Quoted", "c": [{"t": "DoubleQuote"}, [TXT]]})],
  [para(TXT)], "inline")
P("quoted_single", [para({"t": "Quoted", "c": [{"t": "SingleQuote"}, [TXT]]})],
  [para(TXT)], "inline")
P("code_inline", [para({"t": "Code", "c": [NULLATTR, "alpha"]})], [para(TXT)], "inline")
P("code_inline_attrs",
  [para({"t": "Code", "c": [attr("cid", ["python"], [("k", "v")]), "alpha"]})],
  [para({"t": "Code", "c": [NULLATTR, "alpha"]})], "attrs")
P("math_inline", [para({"t": "Math", "c": [{"t": "InlineMath"}, "x^2"]})],
  [para(S("x^2"))], "inline")
P("math_display", [para({"t": "Math", "c": [{"t": "DisplayMath"}, "x^2"]})],
  [para({"t": "Math", "c": [{"t": "InlineMath"}, "x^2"]})], "inline")
P("rawinline_html", [para(S("Z"), {"t": "RawInline", "c": ["html", "<i>alpha</i>"]})],
  [para(S("Z"))], "raw")
P("rawinline_tex", [para(S("Z"), {"t": "RawInline", "c": ["latex", "\\emph{alpha}"]})],
  [para(S("Z"))], "raw")
P("linebreak", [para(TXT, {"t": "LineBreak"}, TXT2)], [para(TXT, SP(), TXT2)], "inline")
P("softbreak", [para(TXT, {"t": "SoftBreak"}, TXT2)], [para(TXT, SP(), TXT2)], "inline")
P("span_attrs", [para({"t": "Span", "c": [attr("sid", ["c1"], [("k", "v")]), [TXT]]})],
  [para(TXT)], "attrs")
P("note", [para(TXT, {"t": "Note", "c": [para(S("fn"))]})], [para(TXT)], "block")
P("cite", [para({"t": "Cite", "c": [[{
    "citationId": "doe1990", "citationPrefix": [], "citationSuffix": [],
    "citationMode": {"t": "NormalCitation"}, "citationNoteNum": 1,
    "citationHash": 0}], [S("[@doe1990]")]]})],
  [para(S("[@doe1990]"))], "block")

# ---------------- links / images ----------------
LINK = {"t": "Link", "c": [NULLATTR, [TXT], ["http://e.com", ""]]}
P("link", [para(LINK)], [para(TXT)], "inline")
P("link_title", [para({"t": "Link", "c": [NULLATTR, [TXT], ["http://e.com", "T"]]})],
  [para(LINK)], "attrs")
P("link_attrs", [para({"t": "Link", "c": [attr("lid", ["c1"], [("k", "v")]), [TXT],
                                          ["http://e.com", ""]]})],
  [para(LINK)], "attrs")
IMG = {"t": "Image", "c": [NULLATTR, [TXT], ["i.png", ""]]}
P("image", [para(IMG, S("x"))], [para(TXT, S("x"))], "inline")
P("image_title", [para({"t": "Image", "c": [NULLATTR, [TXT], ["i.png", "T"]]}, S("x"))],
  [para(IMG, S("x"))], "attrs")
P("image_size", [para({"t": "Image", "c": [attr("", [], [("width", "50%")]), [TXT],
                                           ["i.png", ""]]}, S("x"))],
  [para(IMG, S("x"))], "attrs")

# ---------------- blocks ----------------
P("header", [{"t": "Header", "c": [2, NULLATTR, [TXT]]}], [para(TXT)], "block")
P("header_level", [{"t": "Header", "c": [3, NULLATTR, [TXT]]}],
  [{"t": "Header", "c": [2, NULLATTR, [TXT]]}], "block")
P("header_attrs", [{"t": "Header", "c": [2, attr("hid", ["c1"], [("k", "v")]), [TXT]]}],
  [{"t": "Header", "c": [2, attr("hid"), [TXT]]}], "attrs")
P("blockquote", [{"t": "BlockQuote", "c": [para(TXT)]}], [para(TXT)], "block")
P("codeblock", [{"t": "CodeBlock", "c": [NULLATTR, "x = 1"]}], [para(S("x = 1"))], "block")
P("codeblock_lang", [{"t": "CodeBlock", "c": [attr("", ["python"]), "x = 1"]}],
  [{"t": "CodeBlock", "c": [NULLATTR, "x = 1"]}], "attrs")
P("codeblock_attrs",
  [{"t": "CodeBlock", "c": [attr("cbid", ["python"], [("k", "v")]), "x = 1"]}],
  [{"t": "CodeBlock", "c": [attr("", ["python"]), "x = 1"]}], "attrs")
P("rawblock_html", [para(S("Z")), {"t": "RawBlock", "c": ["html", "<hr class=x>"]}], [para(S("Z"))], "raw")
P("rawblock_tex", [para(S("Z")), {"t": "RawBlock", "c": ["latex", "\\clearpage"]}], [para(S("Z"))], "raw")
P("hrule", [para(TXT), {"t": "HorizontalRule"}, para(TXT2)], [para(TXT), para(TXT2)], "block")
P("lineblock", [{"t": "LineBlock", "c": [[TXT], [TXT2]]}],
  [para(TXT, {"t": "SoftBreak"}, TXT2)], "block")
P("div_attrs", [{"t": "Div", "c": [attr("did", ["c1"], [("k", "v")]), [para(TXT)]]}],
  [para(TXT)], "attrs")

BUL = {"t": "BulletList", "c": [[plain(TXT)], [plain(TXT2)]]}
P("bulletlist", [BUL], [para(TXT), para(TXT2)], "list")
def ol(start=1, style="Decimal", delim="Period"):
    return {"t": "OrderedList", "c": [[start, {"t": style}, {"t": delim}],
                                      [[plain(TXT)], [plain(TXT2)]]]}
P("orderedlist", [ol()], [BUL], "list")
P("ol_start", [ol(start=3)], [ol()], "list")
P("ol_style_roman", [ol(style="UpperRoman")], [ol()], "list")
P("ol_style_alpha", [ol(style="LowerAlpha")], [ol()], "list")
P("ol_delim_paren", [ol(delim="OneParen")], [ol()], "list")
P("ol_example", [ol(style="Example")], [ol()], "list")
P("list_nested", [{"t": "BulletList", "c": [[plain(TXT), BUL]]}],
  [{"t": "BulletList", "c": [[plain(TXT)]]}], "list")
P("list_loose", [{"t": "BulletList", "c": [[para(TXT)], [para(TXT2)]]}], [BUL], "list")
P("deflist", [{"t": "DefinitionList", "c": [[[TXT], [[plain(TXT2)]]]]}],
  [{"t": "BulletList", "c": [[plain(TXT), plain(TXT2)]]}], "list")

P("figure", [{"t": "Figure", "c": [NULLATTR, [None, [plain(S("cap"))]], [plain(IMG)]]}],
  [para(IMG)], "block")
P("figure_attrs",
  [{"t": "Figure", "c": [attr("fid", ["c1"]), [None, [plain(S("cap"))]], [plain(IMG)]]}],
  [{"t": "Figure", "c": [NULLATTR, [None, [plain(S("cap"))]], [plain(IMG)]]}], "attrs")

# ---------------- tables ----------------
BASE = table([], simple_body())
P("table", [BASE], [para(S("a b")), para(S("c d"))], "table")
P("table_head", [table([[tcell("H1"), tcell("H2")]], simple_body())], [BASE], "table")
P("table_caption", [table([], simple_body(), caption=[plain(S("cap"))])], [BASE], "table")
P("table_foot", [table([], simple_body(), foot_rows=[[tcell("F1"), tcell("F2")]])],
  [BASE], "table")
P("table_colspan", [table([], [[tcell("a", colspan=2)], [tcell("c"), tcell("d")]])],
  [table([], [[tcell("a"), tcell("")], [tcell("c"), tcell("d")]])], "table")
P("table_rowspan", [table([], [[tcell("a", rowspan=2), tcell("b")], [tcell("d")]])],
  [table([], [[tcell("a"), tcell("b")], [tcell(""), tcell("d")]])], "table")
P("table_align", [table([], simple_body(),
                        colspecs=[[{"t": "AlignRight"}, {"t": "ColWidthDefault"}],
                                  [{"t": "AlignCenter"}, {"t": "ColWidthDefault"}]])],
  [BASE], "table")
P("table_colwidth", [table([], simple_body(),
                           colspecs=[[{"t": "AlignDefault"}, {"t": "ColWidth", "c": 0.25}],
                                     [{"t": "AlignDefault"}, {"t": "ColWidth", "c": 0.75}]])],
  [BASE], "table")
CAPPED = table([], simple_body(), caption=[plain(S("cap"))])
P("table_attrs",
  [table([], simple_body(), caption=[plain(S("cap"))],
         a=attr("tid", ["c1"], [("k", "v")]))],
  [CAPPED], "attrs")
# same feature on a table with no caption: in pandoc's markdown the attribute
# syntax rides the caption line, so there is nowhere to put it.
P("table_attrs_nocaption",
  [table([], simple_body(), a=attr("tid", ["c1"], [("k", "v")]))],
  [BASE], "attrs")
P("table_cell_attrs",
  [table([], [[tcell("a", a=attr("cid", ["c1"])), tcell("b")], [tcell("c"), tcell("d")]])],
  [BASE], "attrs")
P("table_cell_align",
  [table([], [[tcell("a", align="AlignRight"), tcell("b")], [tcell("c"), tcell("d")]])],
  [BASE], "attrs")
P("table_row_attrs",
  [table([], simple_body())], [BASE], "attrs")  # placeholder replaced below
PROBES["table_row_attrs"]["rich"] = [{"t": "Table", "c": [
    NULLATTR, [None, []],
    [[{"t": "AlignDefault"}, {"t": "ColWidthDefault"}]] * 2,
    [NULLATTR, []],
    [body([row([tcell("a"), tcell("b")], a=attr("rid", ["c1"])),
           row([tcell("c"), tcell("d")])])],
    [NULLATTR, []]]}]
P("table_block_cell",
  [table([], [[cell([para(TXT), para(TXT2)]), tcell("b")], [tcell("c"), tcell("d")]])],
  [table([], [[tcell("alpha beta"), tcell("b")], [tcell("c"), tcell("d")]])], "table")
P("table_rowheadcols",
  [table([], simple_body(), rowheadcols=1)], [BASE], "table")
P("table_multibody", [{"t": "Table", "c": [
    NULLATTR, [None, []],
    [[{"t": "AlignDefault"}, {"t": "ColWidthDefault"}]] * 2,
    [NULLATTR, []],
    [body([row([tcell("a"), tcell("b")])]),
     body([row([tcell("c"), tcell("d")])])],
    [NULLATTR, []]]}],
  [BASE], "table")
