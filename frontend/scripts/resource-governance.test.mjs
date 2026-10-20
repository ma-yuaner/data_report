import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { createSSRApp, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const server = await createServer({
  configFile: false,
  root,
  resolve: { alias: { '@': resolve(root, 'src') } },
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
})
after(() => server.close())
const { http } = await server.ssrLoadModule('/src/api/http.ts')
const { useGovernanceAnalysis } = await server.ssrLoadModule('/src/features/resource-governance/useGovernanceAnalysis.ts')

const scope = () => ({
  startDate: '2026-10-01', endDate: '2026-10-19', dataSource: 'gds', groupBy: 'gds',
  platform: '', site: '', gds: '', resourceChannel: '', pcc: '', apiGroup: '', breachOnly: true,
})
const payload = (params, marker) => ({
  marker, error: '', dimension: { key: params.groupBy, label: '资源', rows: [] }, ratioApplicable: true,
})
async function model() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { render: () => null } }] })
  await router.push('/')
  const applied = ref(scope())
  const data = ref({ dimension: { key: 'gds', label: 'GDS' } })
  let analysis
  const app = createSSRApp({ setup() { analysis = useGovernanceAnalysis(applied, data); return () => null } })
  app.use(router)
  await renderToString(app)
  return { analysis, applied, router }
}

test('formatters keep missing, zero and infinite values distinct', async () => {
  const { nullableCount, percent, ratioText } = await server.ssrLoadModule('/src/features/resource-governance/formatters.ts')
  assert.equal(nullableCount(null), '—')
  assert.equal(nullableCount(0), '0')
  assert.equal(percent(null), '—')
  assert.equal(percent('0'), '0.00%')
  assert.equal(ratioText({ ratioInfinite: true }), '∞')
  assert.equal(ratioText({ queryToSegmentRatio: null }), '—')
})

test('legacy API entry keeps explicit exports pointing to the feature implementation', async () => {
  const legacy = await server.ssrLoadModule('/src/api/resourceGovernance.ts')
  const feature = await server.ssrLoadModule('/src/features/resource-governance/api.ts')
  assert.deepEqual(Object.keys(legacy).sort(), Object.keys(feature).sort())
  for (const name of Object.keys(feature)) assert.equal(legacy[name], feature[name])
})

test('page composition exposes the drawer bindings and keeps ratio styles independent', async () => {
  const { useResourceGovernance } = await server.ssrLoadModule('/src/features/resource-governance/useResourceGovernance.ts')
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { render: () => null } }] })
  await router.push('/')
  let page
  const app = createSSRApp({ setup() { page = useResourceGovernance(); return () => null } })
  app.use(router)
  await renderToString(app)
  assert.equal(typeof page.openAnalysis, 'function')
  assert.equal(page.drawerOpen.value, false)
  assert.ok(Array.isArray(page.analysisDimensionColumns.value))
  assert.deepEqual(page.ratioClass(), { danger: false, healthy: false })
})

test('drill-down and back preserve the applied scope, filters and dates', async (t) => {
  const calls = []
  t.mock.method(http, 'get', async (_path, options) => {
    calls.push({ ...options.params })
    return { data: { success: true, data: payload(options.params) } }
  })
  const { analysis, applied } = await model()
  await analysis.openAnalysis({ value: '1A', name: '1A' })
  assert.equal(analysis.analysisScope.value.gds, '1A')
  assert.equal(analysis.analysisScope.value.groupBy, 'resourceChannel')
  await analysis.continueAnalysis({ value: 'MP', name: 'MP' })
  assert.equal(analysis.analysisScope.value.resourceChannel, 'MP')
  assert.equal(analysis.analysisScope.value.groupBy, 'apiGroup')
  await analysis.backAnalysis()
  assert.equal(analysis.analysisScope.value.resourceChannel, '')
  assert.equal(analysis.analysisScope.value.gds, '1A')
  assert.equal(analysis.analysisScope.value.startDate, applied.value.startDate)
  assert.ok(calls.every((call) => call.breachOnly && call.endDate === '2026-10-19'))
  assert.equal(applied.value.gds, '')
})

test('route diagnosis navigation carries all supported filters and closes the drawer', async (t) => {
  t.mock.method(http, 'get', async (_path, options) => ({ data: { success: true, data: payload(options.params) } }))
  const { analysis, applied, router } = await model()
  applied.value = { ...scope(), platform: '平台A', site: '站点B', pcc: 'PCC1' }
  await analysis.openApiGroupAnalysis({ value: '1A_MPIS', name: 'MPIS' })
  let destination
  t.mock.method(router, 'push', (value) => { destination = value; return Promise.resolve() })
  analysis.openAnalysisRoute({ route: 'SHA-PEK' })
  assert.equal(analysis.drawerOpen.value, false)
  assert.equal(destination.path, '/resource-governance/route-diagnosis')
  assert.deepEqual(destination.query, {
    startDate: '2026-10-01', endDate: '2026-10-19', platform: '平台A', site: '站点B',
    gds: undefined, pcc: 'PCC1', resourceChannel: 'MPIS', apiGroup: '1A_MPIS', entry: 'gds-analysis', route: 'SHA-PEK',
  })
})

test('a late drawer response cannot replace the most recent selection', async (t) => {
  const pending = []
  t.mock.method(http, 'get', (_path, options) => new Promise((resolveResponse) => {
    pending.push(() => resolveResponse({ data: { success: true, data: payload(options.params, options.params.gds) } }))
  }))
  const { analysis } = await model()
  const first = analysis.openAnalysis({ value: '1A', name: '1A' })
  const second = analysis.openAnalysis({ value: '1B', name: '1B' })
  pending[1]()
  await second
  pending[0]()
  await first
  assert.equal(analysis.analysisData.value.marker, '1B')
  assert.equal(analysis.drawerLoading.value, false)
})
