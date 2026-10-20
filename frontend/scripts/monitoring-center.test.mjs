import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const source = await readFile(resolve(root, 'src/views/MonitoringCenterView.vue'), 'utf8')

test('new monitor keeps the three original monitor types', () => {
  assert.match(source, /value: 'ORDER_SEGMENT_THRESHOLD', label: '订单航段'/)
  assert.match(source, /value: 'GDS_QUERY_RATIO_DAILY', label: 'GDS查定比（日）'/)
  assert.match(source, /value: 'OTA_SUCCESS_RATE_DAILY', label: 'OTA成功率（日）'/)
})

test('notification management exposes its three nested tabs', () => {
  assert.match(source, /<a-tab-pane key="endpoints" tab="通知群">/)
  assert.match(source, /<a-tab-pane key="templates" tab="消息模板">/)
  assert.match(source, /<a-tab-pane key="routes" tab="通知路由">/)
  assert.match(source, /:tab-bar-style="\{ display: 'none' \}"/)
  assert.doesNotMatch(source, /\.route-tabs :deep\(\.ant-tabs-nav\) \{ display: none; \}/)
})

test('notification group tab owns a visible create action', () => {
  const endpointPane = source.match(/<a-tab-pane key="endpoints" tab="通知群">([\s\S]*?)<\/a-tab-pane>/)?.[1] || ''
  assert.match(endpointPane, /<a-button type="primary" @click="openEndpoint\(\)">新增通知群<\/a-button>/)
})

test('message templates can only be copied from a registered event template', () => {
  assert.match(source, /新增消息模板/)
  assert.match(source, /事件类型 \/ 基础模板/)
  assert.match(source, /monitoringApi\.createMessageTemplate/)
  assert.match(source, /activeTemplateFields/)
})
