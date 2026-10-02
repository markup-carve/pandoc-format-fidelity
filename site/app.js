const $ = id => document.getElementById(id)
const el = (tag, text, attrs = {}) => {
  const node = document.createElement(tag)
  if (text !== undefined) node.textContent = text
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value)
  return node
}
const svg = (tag, attrs = {}, text) => {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag)
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value)
  if (text !== undefined) node.textContent = text
  return node
}
const repo = 'https://github.com/markup-carve/pandoc-format-fidelity'
const colors = ['#25745b', '#756093', '#464eac', '#b07824', '#ab354a']
const labels = ['Exact', 'Canonical', 'Survives round trip, not exact', 'Writer only', 'Lost / error']
const buckets = ['exact', 'canonical', 'survives', 'expressed', 'lost']
const glyphs = { err: '×', unparsable: '!', same: '−', lost: '−', lossy: '−', partial: '~', canonical: '≈', respelled: '≈', equivalent: '≡', exact: '✓', diff: '+' }
let data, selected = null, returnFocus = null
const tooltip = el('div', '', { class: 'tooltip', role: 'tooltip', id: 'bar-tooltip', hidden: '' })
document.body.append(tooltip)
function tableHead(table, names) {
  table.replaceChildren()
  const head = el('thead'), row = el('tr')
  names.forEach(name => row.append(el('th', name, { scope: 'col' })))
  head.append(row)
  const body = el('tbody')
  table.append(head, body)
  return body
}
function listRows() {
  return Object.entries(data.rows).filter(([, row]) => $('scope').value === 'all' || row.readable).sort(([a, x], [b, y]) => {
    const key = $('sort').value
    if (key === 'name') return a.localeCompare(b)
    const value = row => key === 'semantic' ? row.semantic_content?.pct ?? -1 : row[key]
    return value(y) - value(x) || a.localeCompare(b)
  })
}
const carveBadge = () => el('span', 'Carve', { class: 'carve-badge', title: 'pandoc-carve bridge lane, not a pandoc writer; left out of the medians' })
function charts() {
  $('carve-note').hidden = !Object.values(data.rows).some(row => row.carve)
  tooltip.hidden = true
  $('leaderboard-bars').replaceChildren()
  $('severity-bars').replaceChildren()
  const body = tableHead($('leaderboard-table'), ['Format', 'Semantic %', ...labels])
  for (const [name, row] of listRows()) {
    const wrapper = el('div', undefined, { class: row.carve ? 'bar-row is-carve' : 'bar-row', 'data-format': name })
    const summary = `${name}: ${buckets.map((key, i) => `${labels[i]} ${row.segments[key]}`).join(', ')}. Semantic fidelity ${row.semantic_content?.pct ?? 'unmeasured'}%.`
    const bar = svg('svg', { viewBox: '0 0 660 25', preserveAspectRatio: 'none', tabindex: '0', role: 'img', 'aria-label': summary, 'aria-describedby': 'bar-tooltip' })
    bar.append(svg('title', {}, summary))
    let start = 0
    buckets.forEach((key, i) => {
      const width = row.segments[key] / data.probes.length * 660
      bar.append(svg('rect', { x: start, y: 0, width, height: 25, fill: colors[i] }))
      start += width
    })
    function show() {
      tooltip.textContent = summary
      tooltip.hidden = false
      const bounds = bar.getBoundingClientRect()
      tooltip.style.left = `${Math.max(8, Math.min(bounds.left, innerWidth - tooltip.offsetWidth - 8))}px`
      tooltip.style.top = `${Math.max(8, Math.min(bounds.bottom + 6, innerHeight - tooltip.offsetHeight - 8))}px`
    }
    bar.addEventListener('mouseenter', show)
    bar.addEventListener('focus', show)
    bar.addEventListener('mouseleave', () => { tooltip.hidden = true })
    bar.addEventListener('blur', () => { tooltip.hidden = true })
    const nameLabel = el('span', undefined, { class: 'format-label' })
    nameLabel.append(el('span', name, { class: 'bar-name' }))
    if (name === 'native') nameLabel.append(el('span', 'reference', { class: 'reference-badge', title: "Pandoc's own AST" }))
    if (row.carve) nameLabel.append(carveBadge())
    wrapper.append(nameLabel, bar, el('span', row.semantic_content ? `${row.semantic_content.pct}%` : 'n/a', { class: 'score' }))
    $('leaderboard-bars').append(wrapper)
    const tr = el('tr')
    tr.append(el('th', name, { scope: 'row' }), el('td', row.semantic_content?.pct ?? 'unmeasured'))
    buckets.forEach(key => tr.append(el('td', row.segments[key])))
    body.append(tr)
    const severityRow = el('div', undefined, { class: row.carve ? 'severity-row is-carve' : 'severity-row' })
    const severityName = el('span', name, { class: 'bar-name' })
    if (row.carve) severityName.append(carveBadge())
    severityRow.append(severityName)
    for (const cls of ['content', 'structure', 'presentation']) {
      const by = row.semantic_content?.by[cls]
      const mini = el('div', undefined, { class: 'mini-bar', 'aria-label': `${name}, ${cls}: ${by ? `${by.kept} of ${by.probes} probes kept` : 'not measured'}` })
      const fill = el('i')
      fill.style.width = `${by ? by.weight / by.total * 100 : 0}%`
      mini.append(fill, el('span', by ? `${by.kept}/${by.probes}` : 'n/a'))
      severityRow.append(mini)
    }
    $('severity-bars').append(severityRow)
  }
}
const stateKeys = { lane: 'lane', 'format-filter': 'formatSearch', 'probe-filter': 'probeSearch', 'severity-filter': 'severity', 'verdict-filter': 'verdict' }
function saveState() {
  const query = new URLSearchParams(location.search)
  for (const [id, key] of Object.entries(stateKeys)) {
    const value = $(id).value
    if (value) query.set(key, value)
    else query.delete(key)
  }
  for (const key of ['format', 'probe']) {
    if (selected) query.set(key, selected[key])
    else query.delete(key)
  }
  history.replaceState(null, '', `${location.pathname}${query.size ? `?${query}` : ''}${location.hash}`)
}
function verdictOptions(value = '') {
  $('verdict-filter').replaceChildren(el('option', 'All verdicts', { value: '' }))
  const lane = data.lanes[$('lane').value]
  lane.order.forEach(v => $('verdict-filter').append(el('option', v, { value: v })))
  $('verdict-filter').value = lane.order.includes(value) ? value : ''
  $('cell-legend').replaceChildren()
  lane.order.forEach(v => $('cell-legend').append(el('span', `${glyphs[v] ?? '?'} ${v}`, { class: tone(lane.rank, v) })))
}
// Color by position within the lane's own order: writer `diff` and Carve `exact` are both best.
function tone(ranks, verdict) {
  const r = ranks[verdict]
  if (verdict === 'err' || r === undefined || r < 0) return 'tone-err'
  const real = Object.entries(ranks).filter(([v, x]) => v !== 'err' && x >= 0).map(([, x]) => x)
  const max = Math.max(...real), min = Math.min(...real)
  return r === max ? 'tone-good' : r === min ? 'tone-bad' : r === max - 1 ? 'tone-near' : 'tone-mid'
}
function cellButton(verdict, ranks, label, action) {
  const button = el('button', glyphs[verdict] ?? '?', { class: tone(ranks, verdict), title: label, 'aria-label': label })
  button.addEventListener('click', () => action(button))
  return button
}
function matrix() {
  const lane = data.lanes[$('lane').value]
  const format = $('format-filter').value.toLowerCase(), probeSearch = $('probe-filter').value.toLowerCase()
  const severity = $('severity-filter').value, verdict = $('verdict-filter').value
  const probes = lane.columns.filter(name => name.toLowerCase().includes(probeSearch) && (!severity || data.probes.find(p => p.name === name)?.class === severity))
  const formats = Object.keys(lane.grid).filter(name => name.toLowerCase().includes(format)).sort()
  const activeFormats = formats.filter(name => !verdict || probes.some(p => lane.grid[name][p] === verdict))
  const classes = ['content', 'structure', 'presentation']
  const probeClass = name => data.probes.find(p => p.name === name)?.class ?? 'metadata'
  const activeProbes = probes.filter(p => !verdict || activeFormats.some(name => lane.grid[name][p] === verdict)).sort((a, b) => classes.indexOf(probeClass(a)) - classes.indexOf(probeClass(b)))
  const body = tableHead($('matrix'), ['Format / probe', ...activeProbes])
  const headers = $('matrix').querySelectorAll('thead th')
  activeProbes.forEach((probe, i) => {
    const cls = probeClass(probe), header = headers[i + 1]
    header.replaceChildren(el('span', probe))
    header.title = `${probe}: ${cls}`
    if (i === 0 || cls !== probeClass(activeProbes[i - 1])) header.classList.add('group-start')
  })
  let count = 0
  for (const name of activeFormats) {
    const tr = el('tr')
    tr.append(el('th', name, { scope: 'row' }))
    for (const probe of activeProbes) {
      const td = el('td'), v = lane.grid[name][probe]
      if (probe === activeProbes[0] || probeClass(probe) !== probeClass(activeProbes[activeProbes.indexOf(probe) - 1])) td.classList.add('group-start')
      if (v && (!verdict || v === verdict)) {
        const button = cellButton(v, lane.rank, `${name}, ${probe}: ${v}`, button => openDetail(name, probe, button))
        button.dataset.format = name
        button.dataset.probe = probe
        button.setAttribute('aria-pressed', String(selected?.format === name && selected?.probe === probe))
        td.append(button)
        count++
      } else td.append(el('span', '·', { 'aria-label': 'Filtered out' }))
      tr.append(td)
    }
    body.append(tr)
  }
  $('matrix-count').textContent = `${activeFormats.length} formats · ${activeProbes.length} features · ${count} cells${count ? '' : ' · No matching results'}`
}
function openDetail(format, probe, button, focus = true) {
  selected = { format, probe }
  returnFocus = button ?? returnFocus
  const input = data.probes.find(p => p.name === probe)
  $('detail-title').textContent = `${format} / ${probe}`
  $('detail-severity').textContent = input ? `${input.class} · weight ${input.weight}` : 'Metadata key · not classified by probe severity'
  $('detail-verdicts').replaceChildren()
  for (const [key, lane] of Object.entries(data.lanes)) {
    const row = lane.grid[format]
    // Metadata keys and probes are separate domains, and the Carve lane's rows are bridge modes, not formats.
    if (row ? !(probe in row) : key === 'carve' || !Object.values(lane.grid).some(r => probe in r)) continue
    $('detail-verdicts').append(el('li', `${lane.title}: ${row ? row[probe] : 'not readable, so not round-tripped'}`))
    if (lane.errors?.[format]) $('detail-verdicts').append(el('li', `${lane.title} error: ${lane.errors[format]}`))
  }
  if (data.carve.measured && ['source', 'ast'].includes(format)) {
    $('detail-verdicts').append(el('li', `Carve round trip: ${data.carve.rt?.[format]?.[probe] ?? 'not measured'}`))
    for (const warning of data.carve.warnings?.[probe] ?? []) $('detail-verdicts').append(el('li', `Warning: ${warning}`))
  }
  $('rich-ast').textContent = input ? JSON.stringify(input.rich, null, 2) : 'Metadata is measured separately from the rich/degraded probe ASTs.'
  $('degraded-ast').textContent = input ? JSON.stringify(input.degraded, null, 2) : 'No degraded probe AST for this metadata key.'
  $('detail').hidden = false
  saveState()
  matrix()
  if (focus) {
    $('detail').focus({ preventScroll: true })
    $('detail').scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }
}
function closeDetail() {
  $('detail').hidden = true
  selected = null
  saveState()
  matrix()
  const replacement = [...$('matrix').querySelectorAll('button')].find(b => b.dataset.format === returnFocus?.dataset.format && b.dataset.probe === returnFocus?.dataset.probe)
  replacement?.focus({ preventScroll: true })
}
function restore() {
  const query = new URLSearchParams(location.search)
  for (const [id, key] of Object.entries(stateKeys)) {
    if (id === 'verdict-filter') continue
    const value = query.get(key) ?? (id === 'lane' ? 'matrix' : '')
    if ($(id).tagName !== 'SELECT' || [...$(id).options].some(o => o.value === value)) $(id).value = value
  }
  verdictOptions(query.get('verdict') ?? '')
  selected = null
  $('detail').hidden = true
  matrix()
  const format = query.get('format'), probe = query.get('probe')
  if (data.lanes[$('lane').value].grid[format]?.[probe]) openDetail(format, probe, null, false)
}
function carve() {
  const content = $('carve-content'), rt = data.carve_rt
  if (!rt.measured) {
    content.append(el('p', 'Carve round trip: not measured in this run.'))
    return
  }
  const legend = el('div', undefined, { class: 'legend' })
  rt.order.forEach(v => legend.append(el('span', `${glyphs[v] ?? '?'} ${v}`, { class: tone(rt.rank, v) })))
  const scroll = el('div', undefined, { class: 'table-scroll' }), table = el('table', undefined, { id: 'carve-grid', 'aria-label': 'Carve fixtures by lane' })
  const lanes = Object.keys(rt.lanes), body = tableHead(table, ['Fixture / lane', ...lanes])
  for (const fixture of Object.keys(rt.fixtures)) {
    const tr = el('tr')
    tr.append(el('th', fixture, { scope: 'row' }))
    for (const lane of lanes) {
      const td = el('td'), v = rt.lanes[lane][fixture]
      td.append(cellButton(v, rt.rank, `${fixture}, ${lane}: ${v}`, () => {
        $('carve-detail').hidden = false
        $('carve-detail-title').textContent = `${fixture} / ${lane}: ${v}`
        $('carve-evidence').textContent = JSON.stringify({ source: rt.fixtures[fixture].source,
          options: rt.laneOptions?.[lane] ?? {},
          warnings: (lane === 'bridge-preserve' ? rt.preserveWarnings : rt.warnings)?.[fixture] ?? [],
          error: rt.errors?.[lane]?.[fixture] ?? null,
          returnedSource: (lane === 'bridge-preserve' ? rt.preserveOutput : lane === 'bridge' ? rt.output : {})?.[fixture] ?? 'See raw data for export evidence' }, null, 2)
      }))
      tr.append(td)
    }
    body.append(tr)
  }
  scroll.append(table)
  content.append(legend, scroll)
}
function trend() {
  const records = [...data.history].sort((a, b) => a.date.localeCompare(b.date))
  if (!records.length) { $('trend-chart').append(el('p', 'No history recorded.')); return }
  const metrics = [['semantic_pct_median', 'Semantic', colors[0]], ['exact_median', 'Exact', colors[1]], ['roundtrip_median', 'Round trip', colors[2]], ['expressed_median', 'Expressed', colors[3]]]
  const chart = svg('svg', { viewBox: '0 0 1184 330', role: 'img', 'aria-label': 'History of median semantic fidelity and exact, round-trip, expressed probe shares' })
  chart.append(svg('title', {}, 'Median fidelity over recorded run dates'))
  for (let pct = 0; pct <= 100; pct += 25) {
    const y = 270 - pct * 2
    chart.append(svg('line', { x1: 60, x2: 1134, y1: y, y2: y, stroke: '#dce0db' }), svg('text', { x: 12, y: y + 5, fill: '#626b7f', 'font-size': 13 }, `${pct}%`))
  }
  const times = records.map(r => Date.parse(r.date)), first = Math.min(...times), span = Math.max(...times) - first
  const x = i => span ? 60 + (times[i] - first) / span * 1074 : 597
  const body = tableHead($('history-table'), ['Date (UTC)', 'Pandoc', 'Semantic %', 'Exact probes', 'Round-trip probes', 'Expressed probes'])
  records.forEach(r => {
    const row = el('tr')
    row.append(el('th', r.date, { scope: 'row' }), el('td', r.pandoc))
    metrics.forEach(([key]) => row.append(el('td', r.totals[key] ?? 'unmeasured')))
    body.append(row)
  })
  const legend = el('div', undefined, { class: 'legend', id: 'trend-legend' })
  metrics.forEach(([key, label, color]) => {
    const item = el('span', label), swatch = el('i', undefined, { class: 'dot' })
    swatch.style.background = color
    item.prepend(swatch)
    legend.append(item)
    const points = records.map((r, i) => {
      const raw = r.totals[key]
      return raw == null ? null : { x: x(i), y: 270 - (key === 'semantic_pct_median' ? raw : raw / r.probes * 100) * 2, raw, r }
    })
    // Missing measurements break the line instead of implying continuity.
    let path = '', connected = false
    for (const point of points) {
      if (!point) { connected = false; continue }
      path += `${connected ? 'L' : 'M'}${point.x},${point.y} `
      connected = true
    }
    chart.append(svg('path', { d: path, fill: 'none', stroke: color, 'stroke-width': 3 }))
    points.filter(Boolean).forEach(p => {
      const dot = svg('circle', { cx: p.x, cy: p.y, r: 5, fill: color, tabindex: 0, 'aria-label': `${p.r.date}, pandoc ${p.r.pandoc}, ${label}: ${p.raw}` })
      dot.append(svg('title', {}, `${p.r.date} · pandoc ${p.r.pandoc} · ${label}: ${p.raw}`))
      chart.append(dot)
    })
  })
  const unique = new Map()
  records.forEach((r, i) => { if (!unique.has(r.date.slice(0, 10))) unique.set(r.date.slice(0, 10), i) })
  const indices = [...unique.values()]
  let lastLabelX = -Infinity
  indices.forEach((i, n) => {
    if (x(i) - lastLabelX < 100) return
    lastLabelX = x(i)
    const anchor = n === 0 ? 'start' : n === indices.length - 1 ? 'end' : 'middle'
    chart.append(svg('text', { x: x(i), y: 300, fill: '#626b7f', 'font-size': 12, 'text-anchor': anchor }, records[i].date.slice(0, 10)))
  })
  $('trend-chart').append(chart, legend)
}
function provenance(value, prefix = '') {
  for (const [key, item] of Object.entries(value)) {
    const name = prefix ? `${prefix}.${key}` : key
    if (item && typeof item === 'object' && !Array.isArray(item)) provenance(item, name)
    else $('provenance').append(el('dt', name), el('dd', typeof item === 'string' ? item : JSON.stringify(item)))
  }
}
function render() {
  const run = data.run, pin = run.pandoc.is_pin
  for (const [label, value] of [['Pandoc', run.pandoc.version], ['Measured (UTC)', run.date], ['Commit', run.commit], ['Delta', data.delta.status]]) {
    const entry = el('div')
    entry.append(el('span', label, { class: 'label' }))
    const text = label === 'Commit' && /^[a-f0-9]{7,40}$/i.test(value) ? el('a', value, { href: `${repo}/commit/${value}` }) : el('p', value ?? 'unknown')
    if (label === 'Measured (UTC)' && value) {
      const date = new Date(value)
      const human = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date).replace('Sept', 'Sep')
      text.replaceChildren(el('time', `${human} UTC`, { datetime: value }))
    }
    if (label === 'Pandoc') text.append(el('span', pin ? 'pinned' : 'nightly', { class: 'badge' }))
    entry.append(text)
    $('run-strip').append(entry)
  }
  const stale = run.stale_banner ?? run.pandoc.stale_banner
  if (stale) { $('stale-banner').hidden = false; $('stale-banner').textContent = `Warning: stale pandoc banner. ${typeof stale === 'string' ? stale : JSON.stringify(stale)}` }
  for (const [key, label, value] of [['writers', 'Writers measured', data.totals.formats], ['roundtrip', 'Round-trip formats', data.totals.readable], ['probes', 'Isolated probes', data.probes.length], ['semantic', 'Median semantic fidelity', `${data.totals.semantic_pct_median ?? 'n/a'}%`]]) {
    const stat = el('div')
    stat.append(el('strong', value, { id: `stat-${key}` }), el('span', label))
    $('stats').append(stat)
  }
  labels.forEach((label, i) => { const item = el('span', label), dot = el('i', undefined, { class: 'dot' }); dot.style.background = colors[i]; item.prepend(dot); $('bar-legend').append(item) })
  Object.entries(data.lanes).forEach(([key, lane]) => $('lane').append(el('option', lane.title, { value: key })))
  if (!data.carve.measured) $('explorer').append(el('p', 'Carve bridge: not measured in this run.'))
  data.downloads.forEach(name => $('download-links').append(el('a', name, { href: `data/${encodeURIComponent(name)}`, download: '' })))
  provenance(run)
  charts(); restore(); carve(); trend()
  for (const id of ['sort', 'scope']) $(id).addEventListener('change', charts)
  for (const id of Object.keys(stateKeys)) {
    $(id).addEventListener(id.includes('filter') && $(id).tagName === 'INPUT' ? 'input' : 'change', () => {
      if (id === 'lane') verdictOptions()
      if (selected && !data.lanes[$('lane').value].grid[selected.format]?.[selected.probe]) { selected = null; $('detail').hidden = true }
      matrix(); saveState()
    })
  }
  $('close-detail').addEventListener('click', closeDetail)
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('detail').hidden) closeDetail() })
  window.addEventListener('popstate', restore)
  $('results').hidden = false
}
try {
  const response = await fetch('data/site.json')
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  data = await response.json()
  render()
} catch (error) {
  $('load-error').textContent = `Could not load the recorded results (${error.message}). Try reloading or read the static report.`
  $('load-error').append(el('a', ' Open report', { href: 'report.html' }))
  $('load-error').hidden = false
} finally { $('loading').hidden = true }
