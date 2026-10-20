import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

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
const { normalizeSmartAnalysisFilters, validateSmartAnalysisFilters } = await server.ssrLoadModule('/src/utils/smartAnalysisFilterValidation.ts')

const filters = () => ({
  startDate: '2026-10-20', endDate: '2026-10-20',
  firstDepStart: '', firstDepEnd: '', orderStart: '', orderEnd: '',
  otaOrderNo: '',
})

test('detail exact OTA order query clears and bypasses all date ranges', () => {
  const normalized = normalizeSmartAnalysisFilters({
    ...filters(), otaOrderNo: '  OTA-OLD-001  ', firstDepStart: '2026-12-01',
  }, 'detail')
  assert.equal(normalized.otaOrderNo, 'OTA-OLD-001')
  assert.deepEqual(
    [normalized.startDate, normalized.endDate, normalized.firstDepStart, normalized.firstDepEnd, normalized.orderStart, normalized.orderEnd],
    ['', '', '', '', '', ''],
  )
  assert.equal(validateSmartAnalysisFilters(normalized, 'detail'), '')
})

test('ordinary detail and dimension queries still require a complete date range', () => {
  const empty = { ...filters(), startDate: '', endDate: '' }
  assert.match(validateSmartAnalysisFilters(empty, 'detail'), /至少选择一个完整范围/)
  assert.match(validateSmartAnalysisFilters({ ...empty, otaOrderNo: 'OTA-001' }, 'dimension'), /至少选择一个完整范围/)
  assert.match(validateSmartAnalysisFilters({ ...empty, orderStart: '2026-10-20' }, 'detail'), /完整范围|同时选择进单日期/)
})
