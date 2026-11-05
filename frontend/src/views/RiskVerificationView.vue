<template>
  <div class="page-wrap verification-overview">
    <PageHeader eyebrow="RISK VERIFICATION" title="风控核对" description="独立清洗批量准备证据与核实结果；页面查询读取已保存结果，查询直接读取各日已成功发布结果；个人抽查独立留存，不再依赖整段日期加载到账号。">
      <a-space wrap><a-tag color="blue">订单去重 · 含各类盈亏原因</a-tag><a-button :loading="configLoading" @click="configOpen = true; loadConfigs()">读取通用配置候选</a-button></a-space>
    </PageHeader>
    <FilterPanel stacked :instant="false" :show-reset="false" :loading="loading" :hint="hasPending ? '日期已改变，点击查询后生效' : '按出票时间筛选，结束日期包含当天；同一订单多张票只计1单'">
      <template #header><h2>统计范围</h2><span>默认今日 · 单次最多31天</span></template>
      <template #period>
        <a-segmented v-model:value="preset" :options="presets" :disabled="loading" @change="applyPreset" />
        <DateRangeField v-model:start="startDate" v-model:end="endDate" :disabled="loading" @change="preset = 'custom'" />
      </template>
      <template #actions><a-button type="primary" :loading="loading" @click="queryOverview">查询最新清洗结果</a-button></template>
    </FilterPanel>
    <a-alert v-if="error" type="error" show-icon :message="error" />
    <a-drawer v-model:open="configOpen" title="出票通用配置取证（候选）" :width="'min(1000px, 100vw)'">
      <a-space wrap><a-input v-model:value="configPlatform" placeholder="平台编码，可留空" aria-label="配置平台编码" :disabled="configLoading" /><a-select v-model:value="configGroup" :options="[{ value: '', label: '两个规则大类' }, { value: '出票盈亏配置', label: '出票盈亏配置' }, { value: '出票规则配置', label: '出票规则配置' }]" :disabled="configLoading" aria-label="配置规则大类" /><a-button :loading="configLoading" @click="loadConfigs">读取候选</a-button></a-space>
      <a-alert v-if="configError" type="error" show-icon :message="configError" />
      <a-alert type="warning" show-icon :message="configNotice" />
      <a-table :data-source="configItems" :columns="configColumns" row-key="id" :scroll="{ x: 1000 }" :pagination="{ pageSize: 10 }">
        <template #expandedRowRender="{ record }"><p>配置说明：{{ record.rule_notes || '未配置' }}</p><pre class="config-content">{{ record.ext_json || '未配置' }}</pre><a-alert v-if="record.contentTruncated" type="warning" message="配置内容已截断，不能据此确定阈值" /></template>
      </a-table>
    </a-drawer>
    <a-alert v-if="catalogNotice" type="info" show-icon message="所选出票日期尚未同步" :description="`${catalogNotice}。请先运行所选日期的独立风控清洗任务，再查询最新清洗结果；缺少批次不表示零订单。`" />
    <a-alert v-if="overview?.dataFreshness" :type="['failed', 'running'].includes(overview.dataFreshness.latestAttempt?.status || '') ? 'warning' : 'info'" show-icon :message="`中台同步数据 · 最早同步 ${formatDateTimeDisplay(overview.dataFreshness.oldestSyncedAt)} · 最近同步 ${formatDateTimeDisplay(overview.dataFreshness.newestSyncedAt)}`" :description="syncDescription" />
    <div class="sampling-note"><strong>系统自动核实，人工只抽查与处理异常</strong><span>通过无须人工确认；证据不足、执行失败、规则未接入分别列示。</span><span>{{ overview?.sampling ? `当前账号已抽查 ${overview.sampling.sampled} 单，其中发现问题 ${overview.sampling.disputed} 单。` : '当前抽查统计尚未读取，不能按0单解释。' }}</span></div>
    <a-alert v-if="coverageMissingDays.length" type="warning" show-icon message="部分日期尚未完成清洗，其他已成功日期仍可查询" :description="`缺失日期：${coverageMissingDays.join('、')}。请等待回补或追补任务；未覆盖不表示零订单。`" />
    <div class="auto-actions"><small>直接读取每日成功清洗结果；页面每分钟刷新已生效范围（打开详情或存在操作时暂停），不触发ERP取证。</small></div>
    <details v-if="overview?.dataFreshness.preparation?.reports.length" class="preparation-reports">
      <summary>每日清洗报告（{{ overview.dataFreshness.preparation.reports.length }}天）<span :class="{ 'report-warning': overview.dataFreshness.preparation.reports.some(report => Object.keys(report.insufficientCauses || {}).length) }">{{ overview.dataFreshness.preparation.reports.some(report => Object.keys(report.insufficientCauses || {}).length) ? '含证据不足原因，展开查看' : '展开查看批次耗时与证据不足原因' }}</span></summary>
      <div class="preparation-report-list">
        <div v-for="report in overview.dataFreshness.preparation.reports" :key="report.day" class="preparation-report">
          <strong>{{ report.day }}清洗报告 · {{ report.orders }}单 · {{ report.seconds }}秒</strong>
          <span>{{ Object.keys(report.insufficientCauses || {}).length ? `证据不足原因：${Object.entries(report.insufficientCauses).map(([code, count]) => `${causeLabels[code] || code} ${count}单`).join('；')}` : '该日没有证据不足；核实通过与问题分别列示。' }}</span>
        </div>
      </div>
    </details>
    <div v-if="applied" class="applied-scope"><strong>{{ applied.start }} 至 {{ applied.end }}</strong><span>出票日期 · 已生效范围</span></div>
    <div class="metrics-grid" aria-label="核查概况">
      <button v-for="card in metricCards" :key="card.key" type="button" class="metric-card" :class="card.key" :disabled="!overview || loading" @click="drill(undefined, card.key === 'total' ? 'all' : card.key)">
        <span>{{ card.label }}</span><strong>{{ overview ? count(overview.metrics[card.key]) : '—' }}</strong><small>{{ card.note }}</small>
      </button>
    </div>
    <section class="analysis-panel">
      <div class="panel-heading"><div><h2>按盈亏原因分类核对</h2><p>点击数量，查看对应类型和状态的订单；后续新增类型沿用同一结构。</p></div><span>{{ overview?.categories.length ?? '—' }} 个类型</span></div>
      <div class="progress-legend" aria-label="核查进度颜色说明"><span v-for="state in progressStates" :key="state.key"><i :style="{ backgroundColor: state.color }" />{{ state.label }}</span><span><i class="progress-pending" />未完成</span></div>
      <a-table :columns="categoryColumns" :data-source="overview?.categories || []" row-key="reasonCode" :loading="loading" :pagination="{ pageSize: 10, showSizeChanger: true }" :scroll="{ x: 1180, y: 'min(60vh, 560px)' }" size="middle" :locale="{ emptyText: overview ? '所选出票期间没有盈亏原因有值的订单' : '请查询统计范围；读取失败不显示为0' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'reason'"><strong>{{ record.reasonLabel }}</strong><small class="block-muted">{{ record.reasonCode }}</small></template>
          <a-button v-else-if="isMetricKey(column.key)" type="link" :class="{ 'problem-link': column.key === 'problem' }" @click="drillMetric(record.reasonCode, column.key)">{{ count(metricValue(record, column.key)) }}</a-button>
          <template v-else-if="column.key === 'progress'">
            <div class="verification-progress" role="img" :aria-label="progressDescription(record)"><span v-for="segment in progressSegments(record)" :key="segment.key" :style="{ width: `${segment.percent}%`, backgroundColor: segment.color }" /></div>
            <small class="progress-counts"><span v-for="state in progressStates" :key="state.key">{{ state.label }} {{ record[state.key] }}</span></small>
            <small class="block-muted">已执行核实 {{ record.problem + record.supported + record.insufficient + record.failed }} / {{ record.total }} · {{ record.total ? `${completion(record)}%` : '不适用' }}</small>
            <small class="block-muted">执行进度不代表通过率；证据不足和执行失败仍需关注。</small>
          </template>
          <span v-else-if="column.key === 'rule'" class="rule-note">{{ record.ruleStatus }}</span>
          <a-button v-else-if="column.key === 'action'" type="link" @click="drill(record.reasonCode, 'all')">查看订单</a-button>
        </template>
      </a-table>
      <p v-for="note in overview?.notes || []" :key="note" class="muted">{{ note }}</p>
    </section>
    <section ref="ordersPanel" class="analysis-panel orders-panel">
      <div class="panel-heading"><div><h2>核查订单明细</h2><p>{{ selectedReasonLabel }} · {{ statusLabels[selectedStatus] }} · {{ applied ? `${applied.start} 至 ${applied.end}` : '尚未查询' }}</p></div><a-button :disabled="!applied || ordersLoading" @click="drill(undefined, 'all')">查看全部</a-button></div>
      <div class="order-filters">
        <label>盈亏原因分类<a-select v-model:value="selectedReason" :options="reasonOptions" allow-clear placeholder="全部类型" :disabled="!applied || ordersLoading" @change="filterOrders" /></label>
        <label>核查结果<a-select v-model:value="selectedStatus" :options="statusOptions" :disabled="!applied || ordersLoading" @change="filterOrders" /></label>
      </div>
        <a-alert v-if="ordersError" type="error" show-icon :message="ordersError" />
      <a-table :columns="orderColumns" :data-source="orders?.items || []" row-key="id" :loading="ordersLoading" :pagination="{ current: page, pageSize, total: orders?.total || 0, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'], showTotal: (total: number) => `共 ${total} 单` }" :scroll="{ x: 1020, y: 420 }" size="middle" @change="changePage" :locale="{ emptyText: orders ? '当前类型和状态下没有订单' : '点击上方类型或数量查看明细' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'reason'">{{ categoryLabel(record.profit_reason_type) }}</template>
          <a-tag v-else-if="column.key === 'status'" :color="statusColors[record.verificationStatus as VerificationStatus]">{{ statusLabels[record.verificationStatus as VerificationStatus] }}</a-tag>
          <a-button v-else-if="column.key === 'action'" type="link" @click="openOrder(record)">{{ '查看核实详情' }}</a-button>
        </template>
      </a-table>
    </section>
    <a-drawer :open="drawerOpen" :title="`订单核查 · ${activeOrderNo || activeOrderId}`" :width="'min(1280px, 100vw)'" :destroy-on-close="true" :closable="!panelBusy" :keyboard="!panelBusy" :mask-closable="!panelBusy" @close="closeDrawer">
      <RiskAutomaticDetail v-if="drawerOpen" :key="activeOrderId" ref="casePanel" :order-id="activeOrderId" :reason="activeReason" :source-updated-at="activeUpdatedAt" :issue-date="activeIssueDate" @changed="refreshResults" @busy-change="panelBusy = $event" />
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'

import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { Alert as AAlert, Button as AButton, Drawer as ADrawer, Modal, Segmented as ASegmented, Select as ASelect, Table as ATable, Tag as ATag } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import DateRangeField from '@/components/DateRangeField.vue'
import RiskAutomaticDetail from '@/components/RiskAutomaticDetail.vue'
import { ApiError } from '@/api/http'
import { riskProblems } from '@/api/riskVerification'
import { verificationOverview, type RiskCatalogFreshness, type VerificationCategory, type VerificationMetrics, type VerificationOrder, type VerificationOrders, type VerificationOverview, type VerificationStatus } from '@/api/riskVerification'

const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
const configOpen = ref(false), configLoading = ref(false), configError = ref(''), configNotice = ref('')
const configPlatform = ref('QUNAR'), configGroup = ref('出票盈亏配置')
const configItems = ref<Record<string, unknown>[]>([])
const configColumns = [{ title: '规则ID', dataIndex: 'id' }, { title: '规则名称', dataIndex: 'rule_name' }, { title: '平台', dataIndex: 'ota_code' }, { title: '站点', dataIndex: 'ota_site_code' }, ...[1, 2, 3, 4].map(segments => ({ title: `${segments}段阈值`, dataIndex: ['segmentThresholds', 'values', String(segments)], customRender: ({ text }: { text: unknown }) => text ?? '未识别/不适用' })), { title: '生效开始', dataIndex: 'start_time', customRender: ({ text }: { text: unknown }) => formatDateTimeDisplay(text) }, { title: '生效结束', dataIndex: 'end_time', customRender: ({ text }: { text: unknown }) => formatDateTimeDisplay(text) }, { title: '配置更新时间', dataIndex: 'update_time', customRender: ({ text }: { text: unknown }) => formatDateTimeDisplay(text) }]
async function loadConfigs() {
  if (configLoading.value) return
  configLoading.value = true; configError.value = ''; configItems.value = []
  try { const result = await riskProblems.configs(configPlatform.value.trim(), configGroup.value); if (alive) { configItems.value = result.items; configNotice.value = result.notice; configOpen.value = true } }
  catch (failure) { if (alive) configError.value = failure instanceof Error ? failure.message : '通用配置读取失败' }
  finally { if (alive) configLoading.value = false }
}
const startDate = ref(today)
const endDate = ref(today)
const preset = ref('today')
const presets = [{ label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' }, { label: '本月', value: 'month' }, { label: '自定义', value: 'custom' }]
const applied = ref<{ start: string; end: string }>()
const overview = ref<VerificationOverview>()
const syncDescription = computed(() => {
  const state = overview.value?.dataFreshness.latestAttempt?.status
  if (state === 'failed') return '最近同步失败，保留各日上次成功数据。查询不会重试；排查并重新运行独立清洗，旧核实结果可能已过期。'
  if (state === 'running') return '有同步批次尚未完成，当前显示各日已成功发布的数据；若长期未完成，请管理员检查批次。'
  return '查询和详情读取中台已保存数据；独立清洗完成后加载新结果。展示以各日完整成功批次为准，不代表实时数据。'
})
const orders = ref<VerificationOrders>()
const loading = ref(false)
const ordersLoading = ref(false)
const error = ref('')
const catalogNotice = ref('')
const ordersError = ref('')
const selectedReason = ref<string>()
const selectedStatus = ref<VerificationStatus | 'all'>('all')
const page = ref(1)
const pageSize = ref(20)
const ordersPanel = ref<HTMLElement>()
const hasPending = computed(() => Boolean(applied.value) && (startDate.value !== applied.value?.start || endDate.value !== applied.value?.end))
const statusLabels: Record<VerificationStatus | 'all', string> = { outdated: '已过期待更新', all: '全部状态', problem: '有问题', supported: '核实通过', insufficient: '证据不足', reviewing: '核实中', unchecked: '待自动核实', failed: '执行失败', rule_pending: '规则未接入' }
const statusColors: Record<VerificationStatus, string> = { outdated: 'orange', problem: 'red', supported: 'green', insufficient: 'orange', reviewing: 'blue', unchecked: 'default', failed: 'red', rule_pending: 'default' }
const statusOptions = Object.entries(statusLabels).filter(([value]) => value !== 'reviewing').map(([value, label]) => ({ value, label }))
const metricCards: { key: keyof VerificationMetrics; label: string; note: string }[] = [
  { key: 'total', label: '待核查订单', note: '盈亏原因有值 · 订单去重' },
  { key: 'problem', label: '有问题', note: '系统核算不符合规则' },
  { key: 'supported', label: '核实通过', note: '系统核实符合，无须人工确认' },
  { key: 'insufficient', label: '证据不足', note: '不能认定符合或有问题' },
  { key: 'failed', label: '执行失败', note: '取证或执行失败，需重试' },
  { key: 'unchecked', label: '待核实', note: '清洗完成后加载核实结果' },
  { key: 'outdated', label: '已过期', note: '旧结果不计为当前通过' },
  { key: 'rule_pending', label: '规则未接入', note: '不能套用其他类型规则' },
]
const metricKeys = metricCards.map(item => item.key)
const progressStates = [
  { key: 'supported', label: '核实通过', color: '#52c41a' },
  { key: 'problem', label: '有问题', color: '#ff4d4f' },
  { key: 'insufficient', label: '证据不足', color: '#faad14' },
  { key: 'failed', label: '执行失败', color: '#8c8c8c' },
] as const
const reasonOptions = computed(() => (overview.value?.categories || []).map(item => ({ value: item.reasonCode, label: item.reasonLabel })))
const selectedReasonLabel = computed(() => selectedReason.value ? categoryLabel(selectedReason.value) : '全部类型')
const categoryColumns = [{ title: '盈亏原因分类', key: 'reason', width: 210 }, ...metricCards.map(item => ({ title: item.label, key: item.key, width: 105 })), { title: '核查进度', key: 'progress', width: 220 }, { title: '规则状态', key: 'rule', width: 220 }, { title: '操作', key: 'action', width: 110 }]
const orderColumns = [{ title: '业务订单号', dataIndex: 'order_no', width: 220 }, { title: 'OTA订单号', dataIndex: 'ota_order_no', width: 200 }, { title: '盈亏原因分类', key: 'reason', width: 200 }, { title: '核查结果', key: 'status', width: 130 }, { title: '操作', key: 'action', width: 110 }]
const drawerOpen = ref(false)
const activeOrderId = ref('')
const activeOrderNo = ref('')
const activeReason = ref('')
const activeUpdatedAt = ref<string | null>(null)
const activeIssueDate = ref<string>()
const panelBusy = ref(false)
const casePanel = ref<InstanceType<typeof RiskAutomaticDetail>>()
let summaryRequest = 0
let orderRequest = 0
let alive = true
let refreshTimer: ReturnType<typeof setInterval> | undefined
const causeLabels: Record<string, string> = { HISTORY_RECONSTRUCTION: '历史配置无法还原', HISTORY_STATUS_BASELINE_MISSING: '历史状态缺修改前值', PARSER_REVIEW_REQUIRED: '解析能力待自查', HISTORY_LEDGER_INCOMPLETE: '历史记录不完整', SCOPE_INCOMPLETE: '关联范围不完整', PASSENGER_EVIDENCE: '乘机人证据不足', MONEY_EVIDENCE: '金额证据不足', THRESHOLD_EVIDENCE: '止损证据不足', UNCLASSIFIED_EVIDENCE: '待分析原因' }
const coverageMissingDays = computed(() => [...new Set([...(overview.value?.dataFreshness.missingDays || []), ...(overview.value?.dataFreshness.preparation?.missingDays || [])])].sort())
onBeforeUnmount(() => { alive = false; summaryRequest++; orderRequest++; if (refreshTimer) clearInterval(refreshTimer) })
onMounted(() => {
  void queryOverview()
  refreshTimer = setInterval(() => {
    if (alive && applied.value && !loading.value && !ordersLoading.value && !drawerOpen.value && document.visibilityState === 'visible') void refreshResults()
  }, 60000)
})
function count(value: number) { return value.toLocaleString('zh-CN') }
function catalogVersion(value?: RiskCatalogFreshness) { return value ? `${value.days.map(day => `${day.issue_date}:${day.etl_run_id}`).join('|')}#${value.reasonDictionaryVersion || ''}` : '' }
function categoryLabel(code: unknown) { return overview.value?.categories.find(item => item.reasonCode === code)?.reasonLabel || String(code || '未分类') }
function isMetricKey(key: unknown): key is keyof VerificationMetrics { return typeof key === 'string' && metricKeys.includes(key as keyof VerificationMetrics) }
function metricValue(row: Record<string, any>, key: unknown) { return isMetricKey(key) ? Number(row[key]) : 0 }
function drillMetric(reason: string, key: unknown) { if (isMetricKey(key)) return drill(reason, key === 'total' ? 'all' : key) }
function completion(row: Record<string, any>) { return row.total ? Math.round((row.problem + row.supported + row.insufficient + row.failed) / row.total * 100) : 0 }
function progressSegments(row: Record<string, any>) { return progressStates.filter(state => row[state.key] > 0 && row.total > 0).map(state => ({ ...state, percent: row[state.key] / row.total * 100 })) }
function progressDescription(row: Record<string, any>) { const processed = progressStates.reduce((sum, state) => sum + Number(row[state.key] || 0), 0); return `${progressStates.map(state => `${state.label} ${row[state.key] || 0} 单`).join('，')}，未完成 ${Math.max(0, row.total - processed)} 单，共 ${row.total} 单` }
function applyPreset() {
  if (preset.value === 'today') { startDate.value = today; endDate.value = today }
  if (preset.value === 'yesterday') { startDate.value = dayjs(today).subtract(1, 'day').format('YYYY-MM-DD'); endDate.value = startDate.value }
  if (preset.value === 'month') { startDate.value = today.slice(0, 7) + '-01'; endDate.value = today }
}
async function queryOverview() {
  const request = ++summaryRequest
  orderRequest++
  loading.value = true; ordersLoading.value = false; error.value = ''; catalogNotice.value = ''; ordersError.value = ''
  overview.value = undefined; orders.value = undefined; applied.value = undefined
  selectedReason.value = undefined; selectedStatus.value = 'all'; page.value = 1
  const first = startDate.value || ''; const last = endDate.value || ''
  try {
    const data = await verificationOverview.summary(first, last)
    if (alive && request === summaryRequest) { overview.value = data; applied.value = { start: first, end: last }; await loadOrders() }
  } catch (failure) {
    if (alive && request === summaryRequest) {
      if (failure instanceof ApiError && failure.code === 'RISK_CATALOG_NOT_SYNCED') catalogNotice.value = failure.message
      else error.value = failure instanceof Error ? failure.message : '统计读取失败，请重试'
    }
  }
  finally { if (alive && request === summaryRequest) loading.value = false }
}
async function loadOrders() {
  if (!applied.value) return
  const request = ++orderRequest
  const scope = { ...applied.value }
  const reason = selectedReason.value; const status = selectedStatus.value; const currentPage = page.value; const size = pageSize.value
  ordersLoading.value = true; ordersError.value = ''; orders.value = undefined
  try {
    const result = await verificationOverview.orders(scope.start, scope.end, reason, status, currentPage, size)
    if (alive && request === orderRequest) {
      if (catalogVersion(result.dataFreshness) !== catalogVersion(overview.value?.dataFreshness)) throw new Error('同步批次已改变，请重新查询统计范围后再查看订单')
      orders.value = result
    }
  } catch (failure) { if (alive && request === orderRequest) ordersError.value = failure instanceof Error ? failure.message : '订单读取失败，请重试' }
  finally { if (alive && request === orderRequest) ordersLoading.value = false }
}
async function drill(reason: string | undefined, status: VerificationStatus | 'all') {
  if (!applied.value) return
  selectedReason.value = reason; selectedStatus.value = status; page.value = 1
  await loadOrders()
  ordersPanel.value?.scrollIntoView({ behavior: 'auto', block: 'start' })
}
function filterOrders() { page.value = 1; void loadOrders() }
function changePage(pagination: { current?: number; pageSize?: number }) { page.value = pagination.current || 1; pageSize.value = pagination.pageSize || 20; void loadOrders() }
function openOrder(row: Record<string, any>) { activeOrderId.value = String(row.id); activeOrderNo.value = String(row.order_no || row.ota_order_no || ''); activeReason.value = String(row.profit_reason_type); activeUpdatedAt.value = row.update_time || null; activeIssueDate.value = String(row.issue_date || '').slice(0, 10) || undefined; panelBusy.value = false; drawerOpen.value = true }
function closeDrawer() {
  if (panelBusy.value) return
  if (casePanel.value?.hasUnsavedDrafts) { Modal.confirm({ title: '关闭当前核查？', content: '未保存的确认理由或知识草稿将丢失，已保存记录保留。', okText: '放弃未保存内容并关闭', cancelText: '继续核查', onOk: () => { drawerOpen.value = false } }); return }
  drawerOpen.value = false
}
async function refreshResults() {
  if (!applied.value) return
  const request = ++summaryRequest; const scope = { ...applied.value }
  try { const data = await verificationOverview.summary(scope.start, scope.end); if (alive && request === summaryRequest) { overview.value = data; error.value = ''; await loadOrders(); if (drawerOpen.value && !panelBusy.value && !casePanel.value?.hasUnsavedDrafts) await casePanel.value?.reload() } }
  catch (failure) { if (alive && request === summaryRequest) { overview.value = undefined; orders.value = undefined; error.value = failure instanceof Error ? failure.message : '记录已保存，但汇总刷新失败，请重新查询' } }
}
</script>

<style scoped>
.auto-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.verification-overview { display: grid; gap: 16px; }
.verification-overview > * { min-width: 0; }
.verification-overview :deep(.page-header) { margin-bottom: 0; }
.verification-overview :deep(.filter-panel) { margin-bottom: 0; }
.sampling-note { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; color: #526176; font-size: 13px; line-height: 1.7; }
.sampling-note strong { color: #334155; font-weight: 500; }
.preparation-reports { border: 1px solid #e4e9ef; border-radius: 8px; background: #fff; font-size: 13px; }
.preparation-reports summary { padding: 12px 16px; cursor: pointer; color: #334155; line-height: 1.6; }
.preparation-reports summary span { margin-left: 12px; color: #69768a; font-size: 12px; }
.preparation-reports summary .report-warning { color: #ad6800; }
.preparation-reports summary:focus-visible { outline: 2px solid #1677ff; outline-offset: 2px; }
.preparation-report-list { max-height: 280px; overflow-y: auto; padding: 0 16px 8px; }
.preparation-report { display: grid; gap: 4px; padding: 12px 0; border-top: 1px solid #edf0f4; overflow-wrap: anywhere; }
.preparation-report strong { font-weight: 500; }
.preparation-report span { color: #69768a; }
.auto-actions small { color: #69768a; font-size: 12px; line-height: 1.6; }
.applied-scope, .panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.applied-scope span, .panel-heading span, .panel-heading p, .muted, .block-muted { color: #69768a; font-size: 13px; }
.metrics-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.metric-card { min-width: 0; display: grid; gap: 6px; padding: 16px; text-align: left; border: 1px solid #e4e9ef; border-radius: 8px; background: #fff; cursor: pointer; color: #182235; font: inherit; }
.metric-card strong { font-size: 28px; line-height: 1.3; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.metric-card small { color: #69768a; font-size: 12px; line-height: 1.6; }
.metric-card.problem strong, .problem-link { color: #cf1322; }
.metric-card:focus-visible { outline: 2px solid #1677ff; outline-offset: 2px; }
.metric-card:disabled { cursor: default; }
.analysis-panel { min-width: 0; padding: 20px; background: #fff; border: 1px solid #e4e9ef; border-radius: 8px; }
.panel-heading { margin-bottom: 16px; }
h2 { margin: 0 0 6px; font-size: 18px; }
.panel-heading p { margin: 0; }
.block-muted { display: block; }
.rule-note { font-size: 13px; }
.config-content { white-space: pre-wrap; overflow-wrap: anywhere; }
.progress-legend, .progress-counts { display: flex; flex-wrap: wrap; gap: 6px 12px; font-size: 12px; }
.progress-legend { margin-bottom: 12px; color: #69768a; }
.progress-legend > span { display: inline-flex; align-items: center; gap: 5px; }
.progress-legend i { width: 8px; height: 8px; border-radius: 2px; }
.progress-pending, .verification-progress { background: #edf0f4; }
.verification-progress { display: flex; height: 10px; border-radius: 5px; overflow: hidden; margin-bottom: 6px; }
.verification-progress > span { flex-shrink: 0; height: 100%; }
.progress-supported { color: #237804; }
.progress-problem { color: #cf1322; }
.order-filters { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.order-filters label { display: grid; gap: 6px; min-width: 240px; }
.orders-panel { scroll-margin-top: 20px; }
@media (max-width: 1280px) { .metrics-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .analysis-panel { padding: 16px; } .order-filters label { min-width: 0; width: 100%; } }
</style>
