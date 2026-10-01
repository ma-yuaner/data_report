<template>
  <div class="page-wrap risk-business-page">
    <PageHeader eyebrow="RISK PROFIT ANALYSIS" :title="pageTitle" :description="pageDescription">
      <a-tag color="blue">实际数据 · MySQL</a-tag>
    </PageHeader>

    <a-alert class="source-banner" type="info" show-icon :message="data?.source || defaultSource"
      :description="`按${businessMeta.label}${timeFieldLabel}统计 · CNY预估利润，不代表财务结算`" />

    <section class="scope-panel" aria-label="风控利润分析筛选">
      <div class="section-heading">
        <h2>核对记录统计范围</h2>
        <span>默认今日 · 可快速切换本年 · 最长366天</span>
      </div>
      <div class="period-fields">
        <a-segmented v-model:value="preset" :options="periodOptions" :disabled="loading" @change="applyPreset" />
        <div class="date-fields">
          <span>统计期间</span>
          <a-date-picker v-model:value="draft.startDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" @change="preset = 'custom'" />
          <span>至</span>
          <a-date-picker v-model:value="draft.endDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" @change="preset = 'custom'" />
        </div>
      </div>

      <div class="filter-grid period-filter-grid">
        <label><span>快捷选择年份</span><a-select v-model:value="year" :options="yearOptions" :disabled="loading" @change="selectYear" /></label>
        <label v-if="ordersOnly"><span>业务类型</span><a-select v-model:value="selectedBusiness" :options="businessOptions" @change="changeBusiness" /></label>
        <label><span>盈亏范围</span><a-select v-model:value="draft.profitStatus" :options="profitOptions" /></label>
        <label v-if="!ordersOnly"><span>对比维度</span><a-select v-model:value="draft.groupBy" :options="groupOptions" /></label>
      </div>
      <div class="dimension-filter-title"><strong>维度筛选</strong><span>名称精确匹配；留空表示全部</span></div>
      <div class="filter-grid">
        <label v-for="field in filterFields" :key="field.key">
          <span>{{ field.label }}<small v-if="field.key === 'reason' && !reasonEnabled">当前表未标准化</small></span>
          <a-input v-model:value="draft[field.key]" allow-clear :disabled="field.key === 'reason' && !reasonEnabled"
            :placeholder="field.key === 'reason' && !reasonEnabled ? '待补标准原因字段' : `输入${field.label}全称`" @pressEnter="applyFilters" />
        </label>
      </div>
      <div class="scope-actions">
        <span>{{ hasPending ? '条件已变更，点击查询后生效' : `订单列表与上方分析使用同一组条件` }}</span>
        <div><a-button :disabled="loading" @click="resetFilters">重置</a-button><a-button type="primary" :loading="loading" @click="applyFilters"><SearchOutlined />查询</a-button></div>
      </div>
      <a-alert v-if="rangeError" class="range-error" type="error" show-icon :message="rangeError" />
    </section>

    <div class="applied-scope">
      <strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong>
      <div><a-tag>{{ labelOf(profitOptions, applied.profitStatus) }}</a-tag><a-tag v-for="item in appliedFilterTags" :key="item.label">{{ item.label }}：{{ item.value }}</a-tag></div>
    </div>
    <a-alert v-if="error" class="range-error" type="error" show-icon :message="error" />
    <a-alert v-if="data?.available && data.summary.status === 'no_records'" class="range-error" type="warning" show-icon
      message="当前核对表在所选条件下没有记录；无记录不等于公司没有业务，请检查日期、筛选值和同步覆盖。" />
    <a-alert v-if="hasMissing" class="range-error" type="warning" show-icon
      message="源票数或利润存在NULL，受影响的完整指标显示为—，不会按0补齐。" />

    <a-spin :spinning="loading" tip="正在查询MySQL风控核对数据">
      <template v-if="!ordersOnly">
        <div class="risk-kpi-grid">
          <section class="risk-kpi"><span>{{ businessMeta.label }}票数</span><strong>{{ count(data?.summary.ticketCount) }}</strong><small>SUM(ticket_num)</small></section>
          <section class="risk-kpi"><span>预估利润</span><strong :class="{ negative: negative(data?.summary.estimatedProfit) }">{{ money(data?.summary.estimatedProfit) }}<em v-if="data?.summary.estimatedProfit != null"> 元</em></strong><small>核对表源值汇总</small></section>
          <section class="risk-kpi risk-kpi-loss"><span>亏损票数</span><strong>{{ count(data?.summary.lossTicketCount) }}</strong><small>源记录利润 &lt; 0</small></section>
          <section class="risk-kpi risk-kpi-loss"><span>亏损金额</span><strong>{{ money(data?.summary.lossEstimatedProfit) }}<em v-if="data?.summary.lossEstimatedProfit != null"> 元</em></strong><small>保留负号</small></section>
          <section class="risk-kpi"><span>平均每张亏损</span><strong>{{ money(data?.summary.averageLossPerTicket) }}<em v-if="data?.summary.averageLossPerTicket != null"> 元</em></strong><small>亏损额绝对值 / 亏损票数</small></section>
          <section class="risk-kpi"><span>亏损票数占比</span><strong>{{ percent(data?.summary.lossTicketShare) }}</strong><small>亏损票数 / 总票数</small></section>
        </div>

        <div class="analysis-grid">
          <a-card :bordered="false" class="analysis-panel"><template #title><div class="panel-title"><span>月度趋势</span><small>利润与亏损票数同步观察</small></div></template>
            <BaseChart v-if="data?.available && data.trend.length" :option="trendOption" chart-label="风控利润月度趋势" />
            <a-empty v-else description="当前范围没有可展示的真实趋势数据" />
          </a-card>
          <a-card :bordered="false" class="analysis-panel"><template #title><div class="panel-title"><span>{{ groupLabel }}亏损集中度</span><small>按预估利润从低到高</small></div></template>
            <BaseChart v-if="data?.available && data.dimensions.length" :option="dimensionOption" :chart-label="groupLabel + '利润分布'" />
            <a-empty v-else description="当前维度没有可展示的真实数据" />
          </a-card>
        </div>

        <a-card :bordered="false" class="analysis-panel dimension-panel">
          <template #title><div class="panel-title"><span>{{ groupLabel }}明细对比</span><small>最多展示亏损靠前的50项</small></div></template>
          <template #extra><a-button type="primary" ghost :disabled="loading || !data?.available" @click="openOrdersDrawer">查看当前范围订单</a-button></template>
          <a-table :columns="dimensionColumns" :data-source="data?.dimensions || []" row-key="key" :pagination="false" :scroll="{ x: 850 }">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'"><strong>{{ record.name }}</strong></template>
              <template v-else-if="column.key === 'tickets'">{{ count(record.ticketCount) }}</template>
              <template v-else-if="column.key === 'lossTickets'">{{ count(record.lossTicketCount) }}</template>
              <template v-else-if="column.key === 'profit'"><strong :class="{ negative: negative(record.estimatedProfit) }">{{ money(record.estimatedProfit) }}</strong></template>
              <template v-else-if="column.key === 'share'">{{ percent(record.lossTicketShare) }}</template>
              <template v-else-if="column.key === 'action'"><a-button type="link" size="small" :disabled="record.value == null" @click="drillDimension(record)">筛选并看订单</a-button></template>
            </template>
          </a-table>
        </a-card>
      </template>

      <a-card v-if="ordersOnly" :bordered="false" class="analysis-panel orders-panel">
        <template #title><div class="panel-title"><span>{{ businessMeta.label }}订单明细</span><small>{{ count(data?.orders.total) }} 条核对记录 · 当前条件直接下钻</small></div></template>
        <RiskOrdersTable
          :rows="data?.orders.rows || []" :total="data?.orders.total || 0"
          :page="data?.orders.page || applied.page" :page-size="data?.orders.pageSize || applied.pageSize"
          :time-field="data?.period.timeField || timeField" :loading="loading"
          @change-page="changePage" @open-order="openOrder"
        />
      </a-card>
    </a-spin>

    <div class="notes"><InfoCircleOutlined /><div><strong>统计口径与边界</strong><p v-for="note in data?.notes || defaultNotes" :key="note">{{ note }}</p></div></div>

    <a-drawer v-if="!ordersOnly" v-model:open="ordersDrawerOpen" class="orders-drawer" :width="'min(1280px, 100vw)'" :title="`${businessMeta.label}订单明细`">
      <a-alert type="info" show-icon message="当前分析条件的真实订单" description="继承页面已查询的统计期间、盈亏范围和全部维度筛选；分页不会改变主页面汇总。" />
      <div class="orders-drawer-scope"><strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong><p>{{ ordersDrawerScope }}</p></div>
      <RiskOrdersTable
        :rows="data?.orders.rows || []" :total="data?.orders.total || 0"
        :page="data?.orders.page || applied.page" :page-size="data?.orders.pageSize || applied.pageSize"
        :time-field="data?.period.timeField || timeField" :loading="loading"
        @change-page="changePage" @open-order="openOrder"
      />
    </a-drawer>

    <a-drawer v-model:open="orderDetailOpen" width="620" :title="`${businessMeta.label}订单详情`">
      <a-descriptions v-if="selectedOrder" :column="1" bordered size="small">
        <a-descriptions-item label="统计日期">{{ selectedOrder.businessDate || '—' }}</a-descriptions-item>
        <a-descriptions-item label="OTA订单号">{{ selectedOrder.otaOrderNo || '—' }}</a-descriptions-item>
        <a-descriptions-item label="关联订单号">{{ selectedOrder.relationOrderNo || '—' }}</a-descriptions-item>
        <a-descriptions-item label="业务单号">{{ selectedOrder.serviceOrderNo || '—' }}</a-descriptions-item>
        <a-descriptions-item label="出票票号">{{ selectedOrder.issueTicketNo || '—' }}</a-descriptions-item>
        <a-descriptions-item label="乘客姓名">{{ selectedOrder.passengerName || '—' }}</a-descriptions-item>
        <a-descriptions-item label="平台 / 站点">{{ selectedOrder.platform || '—' }} / {{ selectedOrder.site || '—' }}</a-descriptions-item>
        <a-descriptions-item label="部门">{{ selectedOrder.department || '—' }}</a-descriptions-item>
        <a-descriptions-item label="航司 / 航程">{{ selectedOrder.airline || '—' }} / {{ selectedOrder.route || '—' }}</a-descriptions-item>
        <a-descriptions-item label="供应商">{{ selectedOrder.supplier || '—' }}</a-descriptions-item>
        <a-descriptions-item label="政策员 / 操作员">{{ selectedOrder.policyOperator || '—' }} / {{ selectedOrder.operator || '—' }}</a-descriptions-item>
        <a-descriptions-item label="标准盈亏原因">{{ selectedOrder.reason || '当前表未提供' }}</a-descriptions-item>
        <a-descriptions-item label="核实结果">{{ selectedOrder.verifyResult || '—' }}</a-descriptions-item>
        <a-descriptions-item label="利润备注">{{ selectedOrder.profitRemark || '—' }}</a-descriptions-item>
        <a-descriptions-item label="票数">{{ count(selectedOrder.ticketCount) }}</a-descriptions-item>
        <a-descriptions-item label="预估利润">{{ money(selectedOrder.estimatedProfit) }} 元</a-descriptions-item>
        <a-descriptions-item label="实际利润（推算）">{{ money(selectedOrder.actualProfit) }} 元</a-descriptions-item>
      </a-descriptions>
      <a-alert class="drawer-warning" type="warning" show-icon message="实际利润为源表推算字段，不代表财务已结算；责任与根因仍以业务核实证据为准。" />
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  DatePicker as ADatePicker,
  Descriptions as ADescriptions,
  DescriptionsItem as ADescriptionsItem,
  Drawer as ADrawer,
  Empty as AEmpty,
} from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { InfoCircleOutlined, SearchOutlined } from '@ant-design/icons-vue'
import type { EChartsCoreOption } from 'echarts/core'
import PageHeader from '@/components/PageHeader.vue'
import BaseChart from '@/components/BaseChart.vue'
import RiskOrdersTable from '@/components/RiskOrdersTable.vue'
import { fetchRiskBusiness, type RiskBusinessData, type RiskBusinessKey, type RiskBusinessScope, type RiskDimensionRow, type RiskGroupKey, type RiskOrderRow } from '@/api/riskBusiness'

const props = withDefaults(defineProps<{ businessType?: RiskBusinessKey; ordersOnly?: boolean }>(), { businessType: 'issue', ordersOnly: false })
const businessDefinitions: Record<RiskBusinessKey, { label: string; table: string; timeField: string; timeLabel: string }> = {
  issue: { label: '出票', table: 'bi_order_issue_profit_reconcile_year', timeField: 'business_date', timeLabel: '核对日期' },
  refund: { label: '退票', table: 'bi_order_refund_profit_reconcile_year', timeField: 'stat_date', timeLabel: '核对日期' },
  change: { label: '改签', table: 'bi_order_change_profit_reconcile_year', timeField: 'stat_date', timeLabel: '核对日期' },
}
const businessOptions = (Object.keys(businessDefinitions) as RiskBusinessKey[]).map(key => ({ label: businessDefinitions[key].label, value: key }))
const selectedBusiness = ref<RiskBusinessKey>(props.businessType)
const businessMeta = computed(() => businessDefinitions[selectedBusiness.value])
const reasonEnabled = computed(() => selectedBusiness.value === 'issue')
const pageTitle = computed(() => props.ordersOnly ? '风控订单明细' : `${businessMeta.value.label}利润分析`)
const pageDescription = computed(() => props.ordersOnly ? '统一检索出票、退票、改签核对订单并查看利润证据' : `从${businessMeta.value.label}结果下钻到平台、航司、部门、政策员和具体订单`)
const defaultSource = computed(() => `MySQL · sibebid.${businessMeta.value.table}`)
const timeField = computed(() => businessMeta.value.timeField)
const timeFieldLabel = computed(() => `核对日期（${data.value?.period.timeField || timeField.value}）`)
const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const currentYear = Number(today().slice(0, 4))
function defaultScope(): RiskBusinessScope {
  const day = today()
  return { startDate: day, endDate: day, platform: '', site: '', department: '', airline: '', supplier: '', policy: '', reason: '', verifyResult: '', profitStatus: 'all', groupBy: 'platform', page: 1, pageSize: 30 }
}
const draft = ref<RiskBusinessScope>(defaultScope())
const applied = ref<RiskBusinessScope>({ ...draft.value })
const preset = ref('today')
const year = ref(currentYear)
const data = ref<RiskBusinessData>()
const loading = ref(false)
const error = ref('')
const rangeError = ref('')
let requestId = 0
const periodOptions = [{ label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' }, { label: '本月', value: 'month' }, { label: '本年', value: 'year' }, { label: '自定义', value: 'custom' }]
const yearOptions = Array.from({ length: 6 }, (_, index) => ({ label: `${currentYear - index}年`, value: currentYear - index }))
const profitOptions = [{ label: '全部盈亏', value: 'all' }, { label: '仅亏损', value: 'loss' }, { label: '仅盈利', value: 'profit' }, { label: '零利润', value: 'zero' }]
const defaultGroups: { label: string; value: RiskGroupKey }[] = [
  { label: '按平台', value: 'platform' }, { label: '按站点', value: 'site' }, { label: '按业务部门', value: 'department' },
  { label: '按航司', value: 'airline' }, { label: '按供应商', value: 'supplier' }, { label: '按政策员', value: 'policy' },
  { label: '按核实结果', value: 'verifyResult' },
]
const groupOptions = computed(() => [
  ...defaultGroups,
  ...(reasonEnabled.value ? [{ label: '按盈亏原因', value: 'reason' as RiskGroupKey }] : []),
])
type TextFilterKey = 'platform' | 'site' | 'department' | 'airline' | 'supplier' | 'policy' | 'reason' | 'verifyResult'
const filterFields: { key: TextFilterKey; label: string }[] = [
  { key: 'platform', label: '平台' }, { key: 'site', label: '站点' }, { key: 'department', label: '业务部门' },
  { key: 'airline', label: '航司' }, { key: 'supplier', label: '供应商' }, { key: 'policy', label: '政策员' },
  { key: 'reason', label: '盈亏原因' }, { key: 'verifyResult', label: '核实结果' },
]
const hasPending = computed(() => JSON.stringify(draft.value) !== JSON.stringify(applied.value))
const hasMissing = computed(() => Boolean(data.value?.summary.ticketMissingCount || data.value?.summary.profitMissingCount))
const groupLabel = computed(() => data.value?.availableGroups.find(item => item.key === applied.value.groupBy)?.label || groupOptions.value.find(item => item.value === applied.value.groupBy)?.label.replace('按', '') || '维度')
const appliedFilterTags = computed(() => filterFields.filter(field => applied.value[field.key]).map(field => ({ label: field.label, value: applied.value[field.key] })))
const moneyFormatter = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const countFormatter = new Intl.NumberFormat('zh-CN')
const money = (value: string | number | null | undefined) => value == null ? '—' : moneyFormatter.format(Number(value))
const count = (value: number | null | undefined) => value == null ? '—' : countFormatter.format(value)
const percent = (value: string | null | undefined) => value == null ? '—' : `${(Number(value) * 100).toFixed(2)}%`
const negative = (value: string | null | undefined) => value != null && Number(value) < 0
const labelOf = (options: { label: string; value: string }[], value: string) => options.find(item => item.value === value)?.label || value
const defaultNotes = [
  '票数按SUM(ticket_num)，利润按SUM(estimated_profit_cny)，不使用记录条数替代票数。',
  '页面只展示MySQL核对表真实结果；没有记录时不生成模拟数据。',
]
const ordersDrawerOpen = ref(false)
const orderDetailOpen = ref(false)
const selectedOrder = ref<RiskOrderRow>()
const ordersDrawerScope = computed(() => {
  const tags = [
    labelOf(profitOptions, applied.value.profitStatus),
    ...appliedFilterTags.value.map(item => `${item.label}：${item.value}`),
  ]
  return tags.join(' · ') || '全部核对记录'
})

async function load(scope: RiskBusinessScope) {
  const id = ++requestId
  applied.value = { ...scope }
  loading.value = true
  error.value = ''
  data.value = undefined
  try {
    const result = await fetchRiskBusiness(selectedBusiness.value, scope)
    if (id === requestId) { data.value = result; error.value = result.error }
  } catch (failure) {
    if (id === requestId) error.value = failure instanceof Error ? failure.message : '风控利润分析查询失败'
  } finally { if (id === requestId) loading.value = false }
}
function applyFilters() {
  const first = Date.parse(draft.value.startDate), last = Date.parse(draft.value.endDate)
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first || last - first > 365 * 86400000) { rangeError.value = '请选择有效日期，结束日期不能早于开始日期，单次不能超过366天。'; return }
  rangeError.value = ''
  if (!reasonEnabled.value) draft.value.reason = ''
  if (!groupOptions.value.some(item => item.value === draft.value.groupBy)) draft.value.groupBy = 'platform'
  draft.value.page = 1
  ordersDrawerOpen.value = false
  orderDetailOpen.value = false
  void load({ ...draft.value })
}
function applyPreset(value: string | number) {
  const token = String(value)
  if (token === 'custom') return
  const day = today()
  let first = day, last = day
  if (token === 'yesterday') { first = new Date(Date.parse(day) - 86400000).toISOString().slice(0, 10); last = first }
  if (token === 'month') first = day.slice(0, 7) + '-01'
  if (token === 'year') first = day.slice(0, 4) + '-01-01'
  year.value = currentYear
  draft.value = { ...draft.value, startDate: first, endDate: last, page: 1 }
  applyFilters()
}
function selectYear() {
  preset.value = year.value === currentYear ? 'year' : 'custom'
  draft.value = {
    ...draft.value,
    startDate: `${year.value}-01-01`,
    endDate: year.value === currentYear ? today() : `${year.value}-12-31`,
    page: 1,
  }
  applyFilters()
}
function resetFilters() { preset.value = 'today'; year.value = currentYear; draft.value = defaultScope(); ordersDrawerOpen.value = false; orderDetailOpen.value = false; void load({ ...draft.value }) }
function changeBusiness() { preset.value = 'today'; year.value = currentYear; draft.value = defaultScope(); ordersDrawerOpen.value = false; orderDetailOpen.value = false; void load({ ...draft.value }) }
function changePage(page: number, pageSize: number) { draft.value = { ...applied.value, page, pageSize }; void load({ ...draft.value }) }
function openOrdersDrawer() {
  orderDetailOpen.value = false
  ordersDrawerOpen.value = true
}
async function drillDimension(row: RiskDimensionRow) {
  if (row.value == null) return
  draft.value = { ...applied.value, page: 1 }
  const group = applied.value.groupBy
  if (group === 'verifyResult') draft.value.verifyResult = row.value
  else if (group === 'reason') draft.value.reason = row.value
  else draft.value[group] = row.value
  await load({ ...draft.value })
  if (!error.value) openOrdersDrawer()
}

const trendOption = computed<EChartsCoreOption>(() => ({
  animation: false, color: ['#397cf6', '#d95763'], tooltip: { trigger: 'axis' }, legend: { top: 0, left: 0 },
  grid: { left: 70, right: 65, top: 48, bottom: 36 }, xAxis: { type: 'category', data: data.value?.trend.map(row => row.period) || [] },
  yAxis: [{ type: 'value', name: '预估利润 / 元' }, { type: 'value', name: '亏损票数' }],
  series: [
    { name: '预估利润', type: 'bar', barMaxWidth: 24, data: data.value?.trend.map(row => row.estimatedProfit == null ? null : Number(row.estimatedProfit)) || [] },
    { name: '亏损票数', type: 'line', yAxisIndex: 1, connectNulls: false, data: data.value?.trend.map(row => row.lossTicketCount) || [] },
  ],
}))
const dimensionOption = computed<EChartsCoreOption>(() => {
  const rows = (data.value?.dimensions || []).slice(0, 12).reverse()
  return { animation: false, tooltip: { trigger: 'axis' }, grid: { left: 105, right: 25, top: 22, bottom: 30 }, xAxis: { type: 'value', name: '预估利润 / 元' }, yAxis: { type: 'category', data: rows.map(row => row.name) }, series: [{ type: 'bar', barMaxWidth: 18, data: rows.map(row => ({ value: row.estimatedProfit == null ? null : Number(row.estimatedProfit), itemStyle: { color: negative(row.estimatedProfit) ? '#d95763' : '#397cf6', borderRadius: 3 } })) }] }
})
const dimensionColumns = computed(() => [
  { title: groupLabel.value, key: 'name', width: 180, fixed: 'left' as const }, { title: '票数', key: 'tickets', width: 100 },
  { title: '亏损票数', key: 'lossTickets', width: 110 }, { title: '预估利润 / 元', key: 'profit', width: 150 },
  { title: '亏损票数占比', key: 'share', width: 130 }, { title: '下钻', key: 'action', width: 130, fixed: 'right' as const },
])
function openOrder(row: RiskOrderRow) { selectedOrder.value = row; orderDetailOpen.value = true }

watch(() => props.businessType, value => {
  if (!props.ordersOnly && value !== selectedBusiness.value) { selectedBusiness.value = value; resetFilters() }
})
onMounted(() => { void load({ ...draft.value }) })
</script>

<style scoped>
.source-banner, .range-error { margin-bottom: 14px; border-radius: 10px; }
.scope-panel { padding: 18px 20px; margin-bottom: 14px; border: 1px solid #e4e9f0; border-radius: 12px; background: #fff; }
.section-heading, .scope-actions, .panel-title, .applied-scope { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading h2 { margin: 0; color: #26344b; font-size: 14px; }
.section-heading span, .scope-actions > span, .panel-title small { color: #8995a7; font-size: 11px; }
.period-fields { margin: 16px 0; display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.date-fields { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; color: #6c7a91; font-size: 12px; }
.date-fields :deep(.ant-picker) { width: 142px; }
.filter-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.period-filter-grid { margin-bottom: 16px; }
.filter-grid label { display: grid; gap: 6px; color: #64728a; font-size: 12px; }
.filter-grid label span { display: flex; justify-content: space-between; gap: 5px; }
.filter-grid label small { color: #b28744; font-size: 9px; }
.dimension-filter-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 2px 0 10px; padding-top: 14px; border-top: 1px solid #edf0f5; }
.dimension-filter-title strong { color: #475569; font-size: 12px; }
.dimension-filter-title span { color: #8995a7; font-size: 10px; }
.scope-actions { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf0f5; }
.scope-actions > div { display: flex; gap: 8px; }
.applied-scope { margin: 15px 2px; flex-wrap: wrap; color: #526079; font-size: 12px; }
.applied-scope > div { display: flex; gap: 6px; flex-wrap: wrap; }
.risk-kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.risk-kpi { min-width: 0; padding: 17px; border: 1px solid #e5eaf1; border-radius: 11px; background: #fff; box-shadow: 0 5px 18px rgba(28,45,72,.035); }
.risk-kpi > span, .risk-kpi > small { display: block; color: #7b8799; font-size: 10px; }
.risk-kpi > strong { display: block; margin: 11px 0 8px; color: #213048; font-size: clamp(18px, 1.7vw, 25px); white-space: nowrap; }
.risk-kpi > strong em { font-size: 10px; font-style: normal; font-weight: 400; }
.risk-kpi-loss { border-top: 3px solid #d95763; }
.risk-kpi-loss strong, .negative { color: #c44752 !important; }
.analysis-grid { display: grid; grid-template-columns: 1.15fr .85fr; gap: 14px; }
.analysis-panel { min-width: 0; margin-bottom: 14px; border: 1px solid #e4e9f0; border-radius: 12px; }
.analysis-panel :deep(.ant-card-head) { min-height: 54px; color: #2e3c52; font-size: 14px; }
.analysis-panel :deep(.base-chart) { min-height: 310px; height: 310px; }
.dimension-panel :deep(.ant-table-cell), .orders-panel :deep(.ant-table-cell), .orders-drawer :deep(.ant-table-cell) { padding: 12px 10px; font-size: 11px; }
.orders-drawer-scope { margin: 14px 0; padding: 12px 14px; border: 1px solid #e5eaf1; border-radius: 10px; background: #f7f9fc; color: #526079; font-size: 12px; }
.orders-drawer-scope p { margin: 4px 0 0; color: #7d89a0; font-size: 11px; }
.notes { display: flex; gap: 10px; padding: 10px 2px; color: #8293a9; font-size: 11px; line-height: 1.7; }
.notes p { margin: 5px 0; }
.drawer-warning { margin-top: 16px; }
@media (max-width: 1250px) { .risk-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } .filter-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px) { .analysis-grid { grid-template-columns: 1fr; } .filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .risk-kpi-grid, .filter-grid { grid-template-columns: 1fr; } .scope-actions { align-items: stretch; flex-direction: column; } }
</style>
