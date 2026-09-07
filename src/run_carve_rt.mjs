/**
 * Carve round-trip lane: Carve source in, Carve source out.
 *
 * The existing Carve lane (src/run_carve.mjs) runs the pandoc probes through
 * the bridge, which answers "how much of a pandoc document can Carve hold".
 * This one asks the question a Carve author actually has: **I wrote this in
 * Carve and exported it - what comes back?**
 *
 * That is a different measurement, and it needs a different input. A pandoc
 * probe cannot ask it, because the pandoc AST has no node for a Carve
 * admonition, a task list, a highlight or an editorial mark, so those features
 * never appear in the probe set at all. The inputs here are Carve source
 * files, one construct each, under fixtures/carve/.
 *
 * Two lanes:
 *
 *   bridge      carve -> pandoc AST -> carve. What the bridge alone keeps.
 *   via FORMAT  carve -> pandoc AST -> FORMAT -> pandoc AST -> carve. What
 *               survives an actual export and re-import.
 *
 * Four verdicts, because "not byte-identical" and "lost something" are
 * different claims, and between them sits a third that matters more here than
 * it does on the pandoc side:
 *
 *   exact       the source came back character for character
 *   equivalent  the bytes differ but both parse to the same Carve AST, so a
 *               formatter restyled it and nothing was lost
 *   respelled   the Carve ASTs differ but the rendered HTML is identical: the
 *               document is spelled differently and reads the same. A `[^1]`
 *               reference footnote returning as an inline `^[...]`, a `.`
 *               auto-number returning as `1.`, a `::: >` container returning
 *               as a `>` quote. Calling those loss would be wrong, and calling
 *               them equivalent would hide that the source no longer matches
 *               what the author wrote.
 *   lossy       the rendering differs: something changed for the reader
 *   unparsable  the output is no longer Carve at all
 *   err         a step failed, which is not a fidelity verdict
 *
 * One case is worth knowing about before reading the numbers: a dropped `%%`
 * comment lands as `respelled`, because a comment renders to nothing and the
 * HTML really is identical. The loss is real for the author and invisible to
 * the reader, so it shows up in `warnings` instead, where the bridge says
 * plainly that it dropped it.
 *
 * `respelled` needs a Carve renderer. It comes from the @markup-carve/carve
 * that the bridge itself depends on, resolved through the bridge's own path so
 * the two can never be different versions. When it cannot be resolved the lane
 * still runs and says so in `renderer`: every respelling then lands as `lossy`,
 * which understates fidelity rather than overstating it.
 *
 * Run it with:
 *   make carve-rt CARVE_BRIDGE=../pandoc-carve/dist/index.js
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve, join, basename, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = resolve(new URL('..', import.meta.url).pathname);
const FIXTURES = join(ROOT, 'fixtures', 'carve');
const OUT = join(ROOT, 'results', 'carve-rt.json');
const PANDOC = process.env.PANDOC || join(ROOT, 'vendor', 'pandoc', 'bin', 'pandoc');

// Formats a Carve author would plausibly export to and read back. Deliberately
// short: the axis that matters here is the fixture, not the format, and every
// format costs two pandoc processes per fixture.
const FORMATS = (process.env.CARVE_RT_FORMATS
    || 'markdown,gfm,commonmark_x,djot,html,latex,typst,docx,odt,rst,org,jats,epub'
).split(',').filter(Boolean);

const bridgePath = process.env.CARVE_BRIDGE;
if (!bridgePath) {
    console.error('set CARVE_BRIDGE to a pandoc-carve dist/index.js to run this lane');
    process.exit(2);
}
const bridgeUrl = pathToFileURL(resolve(bridgePath));
const { carveToPandoc, pandocToCarve, carveToCarveAst } = await import(bridgeUrl.href);

// The renderer the bridge itself uses, or nothing. Resolved through the bridge
// so a checkout and a published dist both find their own copy rather than some
// other version that happens to be installed nearby.
let carveToHtml = null;
let rendererNote = 'not resolved: every respelling is reported as lossy';
try {
    // Resolved through package.json rather than the package root: the package
    // is ESM-only, so its "." export has an `import` condition and no
    // `require` one, and createRequire().resolve() of the root fails outright.
    // "./package.json" is exported by convention and gives the directory.
    const pkgPath = createRequire(bridgeUrl).resolve('@markup-carve/carve/package.json');
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
    const entry = pkg.exports?.['.']?.import ?? pkg.module ?? pkg.main;
    const lib = await import(pathToFileURL(join(dirname(pkgPath), entry)).href);
    if (typeof lib.carveToHtml === 'function') {
        carveToHtml = lib.carveToHtml;
        rendererNote = `@markup-carve/carve ${lib.LIB_VERSION ?? 'version unreported'}`;
    } else {
        rendererNote = 'resolved, but it exports no carveToHtml';
    }
} catch (e) {
    rendererNote = `not resolved (${String(e.message).slice(0, 80)})`;
}

/** Source positions are not content: they move whenever the bytes move. */
function stripPos(x) {
    if (Array.isArray(x)) return x.map(stripPos);
    if (x && typeof x === 'object') {
        const out = {};
        for (const [k, v] of Object.entries(x)) {
            if (k === 'pos' || k === 'srcByteLength') continue;
            out[k] = stripPos(v);
        }
        return out;
    }
    return x;
}

/** Trailing whitespace is the formatter's, not the document's. */
const normText = (s) => String(s).replace(/[ \t]+$/gm, '').replace(/\n+$/, '\n');

function astKey(carveText) {
    return JSON.stringify(stripPos(carveToCarveAst(carveText)));
}

function verdict(source, got) {
    if (normText(got) === normText(source)) return 'exact';
    let sameAst;
    try {
        sameAst = astKey(got) === astKey(source);
    } catch {
        // The output no longer parses as Carve. That is a loss, and a louder
        // one than a changed AST, so it is worth saying which fixtures do it.
        return 'unparsable';
    }
    if (sameAst) return 'equivalent';
    if (!carveToHtml) return 'lossy';
    try {
        return carveToHtml(got) === carveToHtml(source) ? 'respelled' : 'lossy';
    } catch {
        return 'lossy';
    }
}

function pandocRun(args, input) {
    return execFileSync(PANDOC, args, {
        input,
        maxBuffer: 64 * 1024 * 1024,
        stdio: ['pipe', 'pipe', 'pipe'],
    });
}

// The container formats wrap a whole document in chrome of their own: epub and
// fb2 add an empty title header, ipynb a cell Div. Without stripping it every
// fixture comes back "lossy" for a reason that has nothing to do with the
// fixture - epub scored 0 of 40 before this. Same list as common.unwrap() on
// the pandoc side, and it has to stay the same list.
const WRAPCLS = new Set(['cell', 'section']);

function unwrap(blocks) {
    let changed = true;
    while (changed) {
        changed = false;
        const out = [];
        for (const b of blocks) {
            if (b?.t === 'Header' && b.c?.[2]?.length === 0) { changed = true; continue; }
            if (b?.t === 'Para' && b.c?.length === 1 && b.c[0]?.t === 'Span'
                && b.c[0].c?.[1]?.length === 0) { changed = true; continue; }
            out.push(b);
        }
        blocks = out;
        if (blocks.length === 1 && blocks[0]?.t === 'Div'
            && (blocks[0].c?.[0]?.[1] ?? []).some((c) => WRAPCLS.has(c))) {
            blocks = blocks[0].c[1];
            changed = true;
        }
    }
    return blocks;
}

/** pandoc AST -> FORMAT -> pandoc AST, the export and re-import in the middle. */
function throughFormat(doc, fmt) {
    const json = JSON.stringify(doc);
    const written = pandocRun(
        ['-f', 'json', '-t', fmt, '-o', '-', '--wrap=preserve',
         `--resource-path=${join(ROOT, 'fixtures')}`],
        json);
    const back = pandocRun(['-f', fmt, '-t', 'json'], written);
    const doc2 = JSON.parse(back.toString('utf8'));
    // Keep only the metadata keys the source document actually had. The epub
    // reader invents a date, a uuid identifier and a language on every read;
    // carrying those back into Carve puts three frontmatter lines the author
    // never wrote in front of every fixture, and the whole lane reads as loss.
    const meta = {};
    for (const k of Object.keys(doc.meta ?? {})) {
        if (doc2.meta && k in doc2.meta) meta[k] = doc2.meta[k];
    }
    return { ...doc2, meta, blocks: unwrap(doc2.blocks) };
}

const files = readdirSync(FIXTURES).filter((f) => f.endsWith('.crv')).sort();
if (!files.length) {
    console.error(`no .crv fixtures in ${FIXTURES}`);
    process.exit(2);
}

const res = {
    generated: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
    pandoc: (() => {
        try {
            return execFileSync(PANDOC, ['--version'], { encoding: 'utf8' })
                .split('\n')[0].trim();
        } catch { return null; }
    })(),
    bridge: bridgePath,
    renderer: rendererNote,
    formats: FORMATS,
    fixtures: {},
    lanes: { bridge: {} },
    warnings: {},
    output: {},
};
for (const fmt of FORMATS) res.lanes[fmt] = {};

for (const file of files) {
    const name = basename(file, '.crv');
    const source = readFileSync(join(FIXTURES, file), 'utf8');
    res.fixtures[name] = { bytes: Buffer.byteLength(source), source };

    let doc;
    try {
        const forward = carveToPandoc(source);
        doc = forward.doc;
        if (forward.warnings?.length) res.warnings[name] = forward.warnings;
    } catch (e) {
        res.lanes.bridge[name] = 'err';
        res.output[name] = `carveToPandoc: ${String(e.message).slice(0, 140)}`;
        for (const fmt of FORMATS) res.lanes[fmt][name] = 'err';
        continue;
    }

    try {
        const back = pandocToCarve(doc);
        res.lanes.bridge[name] = verdict(source, back.carve);
        res.output[name] = back.carve;
    } catch (e) {
        res.lanes.bridge[name] = 'err';
        res.output[name] = `pandocToCarve: ${String(e.message).slice(0, 140)}`;
    }

    for (const fmt of FORMATS) {
        try {
            const round = throughFormat(doc, fmt);
            res.lanes[fmt][name] = verdict(source, pandocToCarve(round).carve);
        } catch (e) {
            res.lanes[fmt][name] = 'err';
        }
    }
}

writeFileSync(OUT, JSON.stringify(res, null, 1) + '\n');

const tally = (lane) => {
    const c = { exact: 0, equivalent: 0, respelled: 0, lossy: 0, unparsable: 0, err: 0 };
    for (const v of Object.values(res.lanes[lane])) c[v] = (c[v] || 0) + 1;
    return c;
};
console.log(`results/carve-rt.json: ${files.length} Carve fixtures`);
console.log(`  renderer: ${rendererNote}`);
for (const lane of ['bridge', ...FORMATS]) {
    const c = tally(lane);
    console.log(
        `  ${lane.padEnd(13)} exact ${String(c.exact).padStart(2)}  ` +
        `equivalent ${String(c.equivalent).padStart(2)}  ` +
        `respelled ${String(c.respelled).padStart(2)}  ` +
        `lossy ${String(c.lossy).padStart(2)}  ` +
        `unparsable ${String(c.unparsable).padStart(2)}  ` +
        `err ${String(c.err).padStart(2)}`);
}
