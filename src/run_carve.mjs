import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const bridge = process.env.CARVE_BRIDGE;
if (!bridge) {
    console.error('set CARVE_BRIDGE to a pandoc-carve dist/index.js to run this lane');
    process.exit(2);
}
// A relative CARVE_BRIDGE is relative to where make was run, not to this file
// in src/ - a bare import specifier would resolve against the module instead.
const {
    carveToPandoc, pandocToCarve, pandocToCarveAst, carveAstToPandoc,
    PANDOC_API_VERSION,
} = await import(pathToFileURL(resolve(bridge)).href);

const { probes, meta, metaBlocks } = JSON.parse(readFileSync('results/probes.json', 'utf8'));

const doc = (blocks, m = {}) => ({
    'pandoc-api-version': PANDOC_API_VERSION,
    meta: m,
    blocks,
});

/** Plain==Para normalization, same as the pandoc-side exact test. */
function norm(x) {
    if (Array.isArray(x)) return x.map(norm);
    if (x && typeof x === 'object') {
        const d = { ...x };
        if (d.t === 'Plain') d.t = 'Para';
        if ('c' in d) d.c = norm(d.c);
        return d;
    }
    return x;
}
const key = (x) => JSON.stringify(norm(x));

/** pandoc -> carve SOURCE -> pandoc */
function viaSource(blocks) {
    const { carve, warnings } = pandocToCarve(doc(blocks));
    const back = carveToPandoc(carve);
    return { text: carve, blocks: back.doc.blocks, meta: back.doc.meta ?? {}, warnings };
}

/** pandoc -> carve AST -> pandoc (no source layer) */
function viaAst(blocks) {
    const { ast, warnings } = pandocToCarveAst(doc(blocks));
    const back = carveAstToPandoc(ast);
    return { text: JSON.stringify(ast), blocks: back.doc.blocks, meta: back.doc.meta ?? {}, warnings };
}

const res = { source: {}, ast: {}, warnings: {}, carveOut: {} };
for (const [name, p] of Object.entries(probes)) {
    for (const [lane, fn] of [['source', viaSource], ['ast', viaAst]]) {
        let rich, deg;
        try {
            rich = fn(p.rich);
        } catch (e) {
            res[lane][name] = 'err:' + String(e.message).slice(0, 90);
            continue;
        }
        try {
            deg = fn(p.degraded);
        } catch (e) {
            res[lane][name] = 'err:' + String(e.message).slice(0, 90);
            continue;
        }
        const expressed = rich.text !== deg.text;
        const exact = key(rich.blocks) === key(norm(p.rich));
        res[lane][name] = exact ? 'exact' : (expressed ? 'diff' : 'same');
        res.rt = res.rt || {};
        res.rt[lane] = res.rt[lane] || {};
        res.rt[lane][name] = key(rich.blocks) !== key(deg.blocks) ? 'diff' : 'same';
        if (lane === 'source') {
            res.warnings[name] = rich.warnings;
            res.carveOut[name] = rich.text;
        }
    }
}

// metadata: 10 keys through both lanes
res.meta = {};
for (const lane of ['source', 'ast']) {
    const fn = lane === 'source' ? viaSource : viaAst;
    let out;
    try {
        const { carve, ast } = lane === 'source'
            ? pandocToCarve(doc(metaBlocks, meta))
            : pandocToCarveAst(doc(metaBlocks, meta));
        const back = lane === 'source' ? carveToPandoc(carve) : carveAstToPandoc(ast);
        out = back.doc.meta ?? {};
        if (lane === 'source') res.carveMeta = carve;
    } catch (e) {
        res.meta[lane] = { _err: String(e.message).slice(0, 120) };
        continue;
    }
    const row = {};
    for (const k of Object.keys(meta)) {
        row[k] = !(k in out) ? 'lost'
            : (JSON.stringify(out[k]) === JSON.stringify(meta[k]) ? 'exact' : 'partial');
    }
    res.meta[lane] = row;
}

writeFileSync('results/carve.json', JSON.stringify(res, null, 1));
const count = (lane, v) => Object.values(res[lane]).filter((x) => x === v).length;
for (const lane of ['source', 'ast']) {
    console.log(lane,
        'expressed(diff+exact)=', count(lane, 'diff') + count(lane, 'exact'),
        'exact=', count(lane, 'exact'),
        'err=', Object.values(res[lane]).filter((x) => String(x).startsWith('err')).length);
}
console.log('meta source:', JSON.stringify(res.meta.source));
console.log('meta ast   :', JSON.stringify(res.meta.ast));
