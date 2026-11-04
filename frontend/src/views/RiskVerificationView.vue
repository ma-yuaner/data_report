<template>
  <div class="page-wrap verification-overview">
    <PageHeader eyebrow="RISK VERIFICATION" title="风控核对" description="按出票日期查看各类待核查订单，定位问题，再下钻核查具体订单。">
      <a-tag color="blue">订单去重 · 含各类盈亏原因</a-tag>
    </PageHeader>
    <FilterPanel stacked :instant="false" :show-reset="false" :loading="loading" :hint="hasPending ? '日期已改变，点击查询后生效' : '按出票时间筛选，结束日期包含当天；同一订单多张票只计1单'">
      <template #header><h2>统计范围</h2><span>默认今日 · 单次最多31天</span></template>
      <template #period>
        <a-segmented v-model:value="preset" :options="presets" :disabled="loading" @change="applyPreset" />
        <DateRangeField v-model:start="startDate" v-model:end="endDate" :disabled="loading" @change="preset = 'custom'" />
      </template>
      <template #actions><a-button type="primary" :loading="loading" @click="queryOverview">查询</a-button></template>
    </FilterPanel>
    <a-alert v-if="error" type="error" show-icon :message="error" />
    <a-alert v-if="overview?.dataFreshness" :type="['failed', 'running'].includes(overview.dataFreshness.latestAttempt?.status || '') ? 'warning' : 'info'" show-icon :message="`中台同步数据 · 最早同步 ${overview.dataFreshness.oldestSyncedAt} · 最近同步 ${overview.dataFreshness.newestSyncedAt}`" :description="syncDescription" />
    <a-alert type="info" show-icon message="有问题指核查后发现选因或依据不符合规则，不是亏损本身" description="以下结果按当前登录人的最新人工核查记录统计。未核查、核查中、证据不足分别列示；尚未接入规则的类型也会展示，不自动判为正常。" />
    <div v-if="applied" class="applied-scope"><strong>{{ applied.start }} 至 {{ applied.end }}</strong><span>出票日期 · 已生效范围</span></div>
    <div class="metrics-grid" aria-label="核查概况">
      <button v-for="card in metricCards" :key="card.key" type="button" class="metric-card" :class="card.key" :disabled="!overview || loading" @click="drill(undefined, card.key === 'total' ? 'all' : card.key)">
        <span>{{ card.label }}</span><strong>{{ overview ? count(overview.metrics[card.key]) : '—' }}</strong><small>{{ card.note }}</small>
      </button>
    </div>
    <section class="analysis-panel">
      <div class="panel-heading"><div><h2>按盈亏原因分类核对</h2><p>点击数量，查看对应类型和状态的订单；后续新增类型沿用同一结构。</p></div><span>{{ overview?.categories.length ?? '—' }} 个类型</span></div>
      <a-table :columns="categoryColumns" :data-source="overview?.categories || []" row-key="reasonCode" :loading="loading" :pagination="{ pageSize: 10, showSizeChanger: true }" :scroll="{ x: 1180 }" size="middle" :locale="{ emptyText: overview ? '所选出票期间没有盈亏原因有值的订单' : '请查询统计范围；读取失败不显示为0' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'reason'"><strong>{{ record.reasonLabel }}</strong><small class="block-muted">{{ record.reasonCode }}</small></template>
          <a-button v-else-if="isMetricKey(column.key)" type="link" :class="{ 'problem-link': column.key === 'problem' }" @click="drillMetric(record.reasonCode, column.key)">{{ count(metricValue(record, column.key)) }}</a-button>
          <template v-else-if="column.key === 'progress'"><a-progress :percent="completion(record)" size="small" /><small class="block-muted">人工有结论 {{ record.problem + record.supported + record.insufficient }} / {{ record.total }}</small></template>
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
          <a-button v-else-if="column.key === 'action'" type="link" @click="openOrder(record)">{{ record.caseId ? '继续核查' : '进入核查' }}</a-button>
        </template>
      </a-table>
    </section>
    <a-drawer :open="drawerOpen" :title="`订单核查 · ${activeOrderNo || activeOrderId}`" :width="'min(1280px, 100vw)'" :destroy-on-close="true" :closable="!panelBusy" :keyboard="!panelBusy" :mask-closable="!panelBusy" @close="closeDrawer">
      <RiskVerificationCasePanel v-if="drawerOpen" :key="activeOrderId" ref="casePanel" embedded :order-id="activeOrderId" :case-id="activeCaseId" @changed="refreshResults" @busy-change="panelBusy = $event" />
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { Alert as AAlert, Button as AButton, Drawer as ADrawer, Modal, Progress as AProgress, Segmented as ASegmented, Select as ASelect, Table as ATable, Tag as ATag } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import DateRangeField from '@/components/DateRangeField.vue'
import RiskVerificationCasePanel from '@/components/RiskVerificationCasePanel.vue'
import { verificationOverview, type RiskCatalogFreshness, type VerificationCategory, type VerificationMetrics, type VerificationOrder, type VerificationOrders, type VerificationOverview, type VerificationStatus } from '@/api/riskVerification'

const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
const startDate = ref(today)
const endDate = ref(today)
const preset = ref('today')
const presets = [{ label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' }, { label: '本月', value: 'month' }, { label: '自定义', value: 'custom' }]
const applied = ref<{ start: string; end: string }>()
const overview = ref<VerificationOverview>()
const syncDescription = computed(() => {
  const state = overview.value?.dataFreshness.latestAttempt?.status
  if (state === 'failed') return '最近同步失败，当前仍展示各日上次成功数据。查询和刷新不会重新同步，请联系管理员检查清洗批次。'
  if (state === 'running') return '有同步批次尚未完成，当前显示各日已成功发布的数据；若长期未完成，请管理员检查批次。'
  return '汇总和列表读取中台目录，刷新不会访问ERP或触发清洗。订单详情按需重新取证，可能比目录更新。'
})
const orders = ref<VerificationOrders>()
const loading = ref(false)
const ordersLoading = ref(false)
const error = ref('')
const ordersError = ref('')
const selectedReason = ref<string>()
const selectedStatus = ref<VerificationStatus | 'all'>('all')
const page = ref(1)
const pageSize = ref(20)
const ordersPanel = ref<HTMLElement>()
const hasPending = computed(() => Boolean(applied.value) && (startDate.value !== applied.value?.start || endDate.value !== applied.value?.end))
const statusLabels: Record<VerificationStatus | 'all', string> = { all: '全部状态', problem: '有问题', supported: '选因符合', insufficient: '证据不足', reviewing: '核查中', unchecked: '未核查' }
const statusColors: Record<VerificationStatus, string> = { problem: 'red', supported: 'green', insufficient: 'orange', reviewing: 'blue', unchecked: 'default' }
const statusOptions = Object.entries(statusLabels).map(([value, label]) => ({ value, label }))
const metricCards: { key: keyof VerificationMetrics; label: string; note: string }[] = [
  { key: 'total', label: '待核查订单', note: '盈亏原因有值 · 订单去重' },
  { key: 'problem', label: '有问题', note: '人工确认选因或依据不符' },
  { key: 'supported', label: '选因符合', note: '仅表示已核查选因符合' },
  { key: 'insufficient', label: '证据不足', note: '不能认定符合或有问题' },
  { key: 'reviewing', label: '核查中', note: '已开始审核，尚未人工确认' },
  { key: 'unchecked', label: '未核查', note: '未审核或快照变更待重核' },
]
const metricKeys = metricCards.map(item => item.key)
const reasonOptions = computed(() => (overview.value?.categories || []).map(item => ({ value: item.reasonCode, label: item.reasonLabel })))
const selectedReasonLabel = computed(() => selectedReason.value ? categoryLabel(selectedReason.value) : '全部类型')
const categoryColumns = [{ title: '盈亏原因分类', key: 'reason', width: 210 }, ...metricCards.map(item => ({ title: item.label, key: item.key, width: 105 })), { title: '核查进度', key: 'progress', width: 180 }, { title: '规则状态', key: 'rule', width: 220 }, { title: '操作', key: 'action', width: 110 }]
const orderColumns = [{ title: '业务订单号', dataIndex: 'order_no', width: 220 }, { title: 'OTA订单号', dataIndex: 'ota_order_no', width: 200 }, { title: '盈亏原因分类', key: 'reason', width: 200 }, { title: '核查结果', key: 'status', width: 130 }, { title: '操作', key: 'action', width: 110 }]
const drawerOpen = ref(false)
const activeOrderId = ref('')
const activeOrderNo = ref('')
const activeCaseId = ref('')
const panelBusy = ref(false)
const casePanel = ref<InstanceType<typeof RiskVerificationCasePanel>>()
let summaryRequest = 0
let orderRequest = 0
let alive = true
onBeforeUnmount(() => { alive = false; summaryRequest++; orderRequest++ })
onMounted(queryOverview)
function count(value: number) { return value.toLocaleString('zh-CN') }
function catalogVersion(value?: RiskCatalogFreshness) { return value ? `${value.days.map(day => `${day.issue_date}:${day.etl_run_id}`).join('|')}#${value.reasonDictionaryVersion || ''}` : '' }
function categoryLabel(code: unknown) { return overview.value?.categories.find(item => item.reasonCode === code)?.reasonLabel || String(code || '未分类') }
function isMetricKey(key: unknown): key is keyof VerificationMetrics { return typeof key === 'string' && metricKeys.includes(key as keyof VerificationMetrics) }
function metricValue(row: Record<string, any>, key: unknown) { return isMetricKey(key) ? Number(row[key]) : 0 }
function drillMetric(reason: string, key: unknown) { if (isMetricKey(key)) return drill(reason, key === 'total' ? 'all' : key) }
function completion(row: Record<string, any>) { return row.total ? Math.round((row.problem + row.supported + row.insufficient) / row.total * 100) : 0 }
function applyPreset() {
  if (preset.value === 'today') { startDate.value = today; endDate.value = today }
  if (preset.value === 'yesterday') { startDate.value = dayjs(today).subtract(1, 'day').format('YYYY-MM-DD'); endDate.value = startDate.value }
  if (preset.value === 'month') { startDate.value = today.slice(0, 7) + '-01'; endDate.value = today }
}
async function queryOverview() {
  const request = ++summaryRequest
  orderRequest++
  loading.value = true; ordersLoading.value = false; error.value = ''; ordersError.value = ''
  overview.value = undefined; orders.value = undefined; applied.value = undefined
  selectedReason.value = undefined; selectedStatus.value = 'all'; page.value = 1
  const first = startDate.value || ''; const last = endDate.value || ''
  try {
    const data = await verificationOverview.summary(first, last)
    if (alive && request === summaryRequest) { overview.value = data; applied.value = { start: first, end: last }; await loadOrders() }
  } catch (failure) { if (alive && request === summaryRequest) error.value = failure instanceof Error ? failure.message : '统计读取失败，请重试' }
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
function openOrder(row: Record<string, any>) { activeOrderId.value = String(row.id); activeOrderNo.value = String(row.order_no || row.ota_order_no || ''); activeCaseId.value = row.caseId || ''; panelBusy.value = false; drawerOpen.value = true }
function closeDrawer() {
  if (panelBusy.value) return
  if (casePanel.value?.hasUnsavedDrafts) { Modal.confirm({ title: '关闭当前核查？', content: '未保存的确认理由或知识草稿将丢失，已保存记录保留。', okText: '放弃未保存内容并关闭', cancelText: '继续核查', onOk: () => { drawerOpen.value = false } }); return }
  drawerOpen.value = false
}
async function refreshResults() {
  if (!applied.value) return
  const request = ++summaryRequest; const scope = { ...applied.value }
  try { const data = await verificationOverview.summary(scope.start, scope.end); if (alive && request === summaryRequest) { overview.value = data; await loadOrders() } }
  catch (failure) { if (alive && request === summaryRequest) error.value = failure instanceof Error ? failure.message : '确认已保存，但汇总刷新失败，请重新查询' }
}
</script>

<style scoped>
.verification-overview { display: grid; gap: 16px; }
.verification-overview :deep(.filter-panel) { margin-bottom: 0; }
.applied-scope, .panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.applied-scope span, .panel-heading span, .panel-heading p, .muted, .block-muted { color: #69768a; font-size: 13px; }
.metrics-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }
.metric-card { display: grid; gap: 8px; padding: 20px 16px; text-align: left; border: 1px solid #e4e9ef; border-radius: 8px; background: #fff; cursor: pointer; color: #182235; }
.metric-card strong { font-size: 30px; font-weight: 600; }
.metric-card small { color: #69768a; }
.metric-card.problem strong, .problem-link { color: #cf1322; }
.metric-card:focus-visible { outline: 2px solid #1677ff; outline-offset: 2px; }
.metric-card:disabled { cursor: default; }
.analysis-panel { min-width: 0; padding: 20px; background: #fff; border: 1px solid #e4e9ef; border-radius: 8px; }
.panel-heading { margin-bottom: 16px; }
h2 { margin: 0 0 6px; font-size: 18px; }
.panel-heading p { margin: 0; }
.block-muted { display: block; }
.rule-note { font-size: 13px; }
.order-filters { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.order-filters label { display: grid; gap: 6px; min-width: 240px; }
.orders-panel { scroll-margin-top: 20px; }
@media (max-width: 1280px) { .metrics-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .analysis-panel { padding: 16px; } .order-filters label { min-width: 0; width: 100%; } }
</style>
