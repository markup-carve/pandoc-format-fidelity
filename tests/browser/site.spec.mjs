import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
const data = JSON.parse(readFileSync('dist/data/site.json', 'utf8'))
async function ready(page) { await page.goto('/'); await expect(page.locator('#results')).toBeVisible() }
test('stats match recorded totals without page errors', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await ready(page)
  await expect(page.locator('#stat-writers')).toHaveText(String(data.totals.formats))
  await expect(page.locator('#stat-roundtrip')).toHaveText(String(data.totals.readable))
  await expect(page.locator('#stat-probes')).toHaveText(String(data.probes.length))
  await expect(page.locator('#stat-semantic')).toHaveText(`${data.totals.semantic_pct_median}%`)
  expect(errors).toEqual([])
})
test('leaderboard scope and alphabetical sort', async ({ page }) => {
  await ready(page)
  await expect(page.locator('#leaderboard-bars .bar-row')).toHaveCount(data.totals.readable)
  await page.locator('#scope').selectOption('all')
  await expect(page.locator('#leaderboard-bars .bar-row')).toHaveCount(data.totals.formats)
  await page.locator('#sort').selectOption('name')
  const names = await page.locator('#leaderboard-bars .bar-name').allTextContents()
  expect(names).toEqual(Object.keys(data.rows).sort((a, b) => a.localeCompare(b)))
  await page.locator('#leaderboard-bars svg').first().focus()
  await expect(page.locator('#bar-tooltip')).toBeVisible()
})
test('explorer filters and deep-linked AST detail', async ({ page }) => {
  await ready(page)
  await page.locator('#lane').selectOption('exact')
  await page.locator('#format-filter').fill('asciidoc')
  await page.locator('#probe-filter').fill('emph')
  await expect(page.locator('#matrix tbody button')).toHaveCount(1)
  await page.locator('#matrix tbody button').press('Enter')
  await expect(page.locator('#detail')).toBeVisible()
  await expect(page.locator('#rich-ast')).toContainText('Emph')
  await expect(page.locator('#degraded-ast')).toContainText('Str')
  expect(new URL(page.url()).searchParams.get('format')).toBe('asciidoc')
  await page.reload()
  await expect(page.locator('#detail')).toBeVisible()
  await expect(page.locator('#lane')).toHaveValue('exact')
  await expect(page.locator('#format-filter')).toHaveValue('asciidoc')
  await page.keyboard.press('Escape')
  await expect(page.locator('#detail')).toBeHidden()
})
test('unfiltered cell detail scrolls into view and shows metadata errors', async ({ page }) => {
  await ready(page)
  await page.locator('#lane').selectOption('meta')
  await page.locator('#matrix tbody button').first().click()
  await expect(page.locator('#detail')).toBeInViewport()
  const failed = Object.keys(data.lanes.meta.errors)[0]
  test.skip(!failed, 'no failed metadata conversion recorded')
  await page.locator('#format-filter').fill(failed)
  await page.locator('#matrix tbody button').first().click()
  await expect(page.locator('#detail-verdicts')).toContainText('metadata error:')
  await expect(page.locator('#detail-verdicts')).not.toContainText('metadata: lost')
})
test('Carve fixtures and warnings', async ({ page }) => {
  await ready(page)
  await expect(page.locator('#carve-grid tbody tr')).toHaveCount(Object.keys(data.carve_rt.fixtures).length)
  await page.getByRole('button', { name: 'comment, bridge: respelled', exact: true }).click()
  await expect(page.locator('#carve-evidence')).toContainText('dropped')
})
test('format names are literal text', async ({ page }) => {
  const injected = structuredClone(data), name = '<img src=x onerror="window.pwned=1">'
  injected.rows[name] = injected.rows.asciidoc
  delete injected.rows.asciidoc
  for (const lane of Object.values(injected.lanes)) {
    if (lane.grid.asciidoc) { lane.grid[name] = lane.grid.asciidoc; delete lane.grid.asciidoc }
  }
  await page.route('**/data/site.json', route => route.fulfill({ json: injected }))
  await ready(page)
  await expect(page.locator('#leaderboard-bars')).toContainText(name)
  expect(await page.evaluate(() => window.pwned)).toBeUndefined()
  await expect(page.locator('#leaderboard-bars img')).toHaveCount(0)
})
test('fetch failure has an alert', async ({ page }) => {
  await page.route('**/data/site.json', route => route.fulfill({ status: 503, body: 'Unavailable' }))
  await page.goto('/')
  await expect(page.locator('#load-error')).toBeVisible()
  await expect(page.locator('#load-error')).toContainText('Could not load')
})
test('page has no horizontal overflow', async ({ page }) => {
  await ready(page)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.locator('#scope').selectOption('all')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
test('one history point and optional Carve sections', async ({ page }) => {
  const single = structuredClone(data)
  single.history = single.history.slice(0, 1)
  single.carve = { measured: false }; single.carve_rt = { measured: false }
  delete single.lanes.carve
  await page.route('**/data/site.json', route => route.fulfill({ json: single }))
  await ready(page)
  await expect(page.locator('#trend-chart circle')).toHaveCount(4)
  await expect(page.locator('#carve-content')).toContainText('not measured in this run')
  await expect(page.locator('#explorer')).toContainText('Carve bridge: not measured in this run')
})
test('compact heatmaps, aligned severity columns and provenance', async ({ page }) => {
  await ready(page)
  for (const selector of ['#matrix tbody button', '#carve-grid tbody button']) {
    const cell = page.locator(selector).first()
    expect([...await cell.textContent()]).toHaveLength(1)
    expect(await cell.getAttribute('title')).toBe(await cell.getAttribute('aria-label'))
    const box = await cell.boundingBox()
    expect(box.width).toBe(24)
    expect(box.height).toBe(24)
  }
  const headings = page.locator('.severity-heading > span')
  const bars = page.locator('#severity-bars .severity-row').first().locator('> *')
  for (let i = 1; i < 4; i++) {
    expect((await headings.nth(i).boundingBox()).x).toBe((await bars.nth(i).boundingBox()).x)
  }
  await expect(page.locator('#run-strip time')).toHaveAttribute('datetime', data.run.date)
  await expect(page.locator('#run-strip time')).toHaveText(new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(data.run.date)).replace('Sept', 'Sep') + ' UTC')
  await expect(page.locator('[data-format="native"] .reference-badge')).toHaveText('reference')
  await expect(page.locator('header nav a[href="#carve"]')).toBeVisible()
  await expect(page.locator('header nav a[href="#trend"]')).toBeVisible()
})
test('trend labels each date once and uses an HTML legend', async ({ page }) => {
  await ready(page)
  const dates = await page.locator('#trend-chart svg text').allTextContents()
  const dateLabels = dates.filter(label => /^\d{4}-\d{2}-\d{2}$/.test(label))
  expect(new Set(dateLabels).size).toBe(dateLabels.length)
  await expect(page.locator('#trend-legend span')).toHaveCount(4)
  for (const point of await page.locator('#trend-chart circle title').allTextContents()) expect(point).toContain('pandoc')
})
