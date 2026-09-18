<template>
  <div class="page-wrap comprehensive-page">
    <PageHeader eyebrow="BUSINESS PERFORMANCE" title="综合分析" description="从出退改增的经营结果，逐层定位平台、站点、航司和产品">
      <a-tag color="blue">实际数据 · Hive ADS</a-tag>
    </PageHeader>
    <a-alert class="source-banner" type="info" show-icon :message="data?.source || 'Hive · ads_business_profit_dimension_day'"
      :description="'CNY业务估算口径 · 不代表财务结算' + (data?.coverage.updatedAt ? ' · 最近加工：' + data.coverage.updatedAt : '')" />
    <section class="scope-panel" aria-label="综合分析筛选">
      <div class="section-heading"><h2>统计范围</h2><span>默认今日 · 各业务按自身发生时间统计</span></div>
      <div class="period-fields">
        <a-segmented v-model:value="draft.preset" :options="periodOptions" :disabled="loading" @change="applyPreset" />
        <div class="date-fields"><span>统计期间</span>
          <a-date-picker v-model:value="draft.startDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" @change="draft.preset = 'custom'" />
          <span>至</span><a-date-picker v-model:value="draft.endDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" @change="draft.preset = 'custom'" />
        </div>
      </div>
      <div class="dimension-fields">
        <label v-for="dimension in dimensions" :key="dimension.key"><span>{{ dimension.label }}<small v-if="dimension.key === 'product'">平台内原值</small></span>
          <a-select v-model:value="draft[dimension.key]" :aria-label="dimension.label + '筛选'" :options="filterOptions(dimension.key)" show-search option-filter-prop="label" :disabled="loading" />
        </label>
      </div>
      <div class="scope-actions"><span>{{ hasPending ? '条件已变更，点击查询后生效' : '时间与四个业务维度可组合筛选；结束日期包含当天' }}</span>
        <div><a-button :disabled="loading" @click="resetFilters"><UndoOutlined />重置</a-button><a-button type="primary" :loading="loading" @click="applyFilters"><SearchOutlined />查询</a-button></div>
      </div>
      <a-alert v-if="rangeError" class="range-error" type="error" show-icon :message="rangeError" />
    </section>
    <div class="applied-scope"><strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong>
      <div><a-tag v-if="!scopeItems.length" color="blue">全部范围</a-tag><a-tag v-for="item in scopeItems" :key="item.key" color="blue" :closable="!loading" @close="removeDimension(item.key)">{{ item.label }}：{{ optionLabel(item.key, applied[item.key]) }}</a-tag></div>
    </div>
    <a-alert v-if="error" class="range-error" type="error" show-icon :message="error" />
    <a-alert v-if="hasMissingProfit" class="range-error" type="warning" show-icon message="所选范围存在缺失利润；完整利润和合计显示为 —，已知金额不冒充完整利润。" />
    <a-spin :spinning="loading" tip="正在读取Hive ADS数据">
      <div class="summary-grid">
        <section class="summary-total" :data-total-profit="data?.totalProfit ?? undefined"><span>总业务估算利润</span><strong>{{ money(data?.totalProfit) }}<em v-if="data?.totalProfit != null">元</em></strong><p>出票 + 退票 + 改签 + 增值</p><small>CNY · 不含风控核对区重复汇总</small></section>
        <section v-for="business in businesses" :key="business.key" class="business-card" :style="{ '--business-color': business.color }">
          <div class="business-heading">{{ business.label }}利润</div><strong :class="{ negative: isNegative(metric(business.key)?.profit) }" :data-profit="metric(business.key)?.profit ?? undefined">{{ money(metric(business.key)?.profit) }}<em v-if="metric(business.key)?.profit != null">元</em></strong>
          <div class="business-count"><span>{{ business.countLabel }}</span><b :data-count="metric(business.key)?.count ?? undefined">{{ count(metric(business.key)?.count) }}</b></div>
          <p v-if="metric(business.key)?.profitMissingCount" class="missing-note">缺失 {{ count(metric(business.key)?.profitMissingCount) }} 条 · 已知 {{ money(metric(business.key)?.knownProfit) }} 元</p>
          <p v-if="metric(business.key)?.productMissingCount" class="missing-note">待补充产品 {{ count(metric(business.key)?.productMissingCount) }} 条</p>
          <button type="button" class="business-link" :disabled="!available || loading" @click="openDetail(business.key)">查看日汇总<ArrowRightOutlined /></button>
        </section>
      </div>
      <div class="charts-grid">
        <a-card :bordered="false" class="analysis-panel"><template #title><div class="panel-title"><span>经营利润趋势</span><small>按业务日 · 元</small></div></template>
          <BaseChart v-if="available" :option="trendOption" chart-label="出退改增利润及合计趋势" /><a-empty v-else description="数据未就绪，请检查时间范围或清洗结果" />
        </a-card>
        <a-card :bordered="false" class="analysis-panel"><template #title>四类业务利润构成</template>
          <BaseChart v-if="available" :option="compositionOption" chart-label="四类业务利润构成" /><a-empty v-else description="不使用演示数据填补查询结果" />
          <p class="composition-note">利润可以合计；四类业务数量分别列示，不合并为总票数。缺失利润不画成零值。</p>
        </a-card>
      </div>
      <a-card :bordered="false" class="analysis-panel comparison-panel"><template #title>维度经营对比</template>
        <div class="comparison-toolbar"><a-segmented v-model:value="groupDimension" :options="dimensionOptions" :disabled="loading" @change="changeGroup" /><span>选择某项继续分析，可叠加其他维度</span></div>
        <a-table class="dimension-table" :columns="comparisonColumns" :data-source="data?.comparison || []" row-key="key" :pagination="{ pageSize: 20, showSizeChanger: true }" :scroll="{ x: 1120 }" :locale="{ emptyText: available ? '所选条件没有业务记录' : '中间层数据未就绪' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'"><strong>{{ record.name }}</strong></template>
            <template v-else-if="isBusinessKey(column.key)"><div class="metric-cell"><strong :class="{ negative: isNegative(record.metrics[column.key].profit) }">{{ money(record.metrics[column.key].profit) }}<small> 元</small></strong><span>{{ count(record.metrics[column.key].count) }} 条</span><span v-if="record.metrics[column.key].profitMissingCount">缺失利润 {{ count(record.metrics[column.key].profitMissingCount) }} 条</span></div></template>
            <template v-else-if="column.key === 'total'"><strong :class="{ negative: isNegative(record.totalProfit) }">{{ money(record.totalProfit) }} 元</strong></template>
            <template v-else-if="column.key === 'action'"><a-button type="link" size="small" @click="drillDimension(record)">分析此项</a-button><a-button type="link" size="small" @click="openDetail(undefined, record)">日汇总</a-button></template>
          </template>
          <template #footer><div class="comparison-footer"><span>当前范围共 {{ data?.comparison.length || 0 }} 个{{ groupLabel }} · 分页仅影响显示，不截取总额</span><span>合计利润：{{ money(data?.totalProfit) }} 元</span></div></template>
        </a-table>
      </a-card>
    </a-spin>
    <div class="handoff-note"><InfoCircleOutlined /><div><strong>口径与数据边界</strong><p v-for="note in data?.notes || []" :key="note">{{ note }}</p></div></div>
    <a-drawer v-model:open="drawerOpen" :title="drawerTitle" :width="'min(900px, 100vw)'">
      <a-alert type="info" show-icon message="真实日汇总 · 非订单级明细" description="保留当前时间和维度条件；订单编号与原因证据不在本ADS表中，未生成模拟明细。" />
      <div class="drawer-scope"><strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong><p>{{ drawerScope }}</p></div>
      <a-alert v-if="drawerError" type="error" :message="drawerError" show-icon />
      <a-table :loading="drawerLoading" :columns="drawerColumns" :data-source="drawerRows" row-key="key" :pagination="{ pageSize: 20 }" :scroll="{ x: 620 }">
        <template #bodyCell="{ column, record }"><template v-if="column.key === 'count'">{{ count(record.count) }} 条</template><template v-else-if="column.key === 'profit'">{{ money(record.profit) }} 元</template><template v-else-if="column.key === 'missing'">{{ count(record.profitMissingCount) }}</template></template>
      </a-table>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { DatePicker as ADatePicker, Drawer as ADrawer, Empty as AEmpty } from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { ArrowRightOutlined, InfoCircleOutlined, SearchOutlined, UndoOutlined } from '@ant-design/icons-vue'
import type { EChartsCoreOption } from 'echarts/core'
import PageHeader from '@/components/PageHeader.vue'
import BaseChart from '@/components/BaseChart.vue'
import { fetchComprehensive, type BusinessKey, type ComprehensiveData, type DimensionKey, type DimensionRow, type FilterScope } from '@/api/comprehensive'

const businesses: { key: BusinessKey; label: string; countLabel: string; color: string }[] = [
  { key: 'issue', label: '出票', countLabel: '出票记录数', color: '#397cf6' },
  { key: 'refund', label: '退票', countLabel: '退票记录数', color: '#efab45' },
  { key: 'change', label: '改签', countLabel: '改签记录数', color: '#8570cf' },
  { key: 'ancillary', label: '增值', countLabel: '增值购买记录数', color: '#3aada0' },
]
const dimensions: { key: DimensionKey; label: string }[] = [{ key: 'platform', label: '平台' }, { key: 'site', label: '站点' }, { key: 'airline', label: '航司' }, { key: 'product', label: '产品' }]
const periodOptions = [{ label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' }, { label: '本月', value: 'month' }, { label: '本年', value: 'year' }, { label: '自定义', value: 'custom' }]
// Calendar dates always use the company's UTC+8 business timezone.
function businessToday() { return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }) }
function todayScope(): FilterScope { const day = businessToday(); return { preset: 'today', startDate: day, endDate: day, platform: '', site: '', airline: '', product: '' } }
const draft = ref<FilterScope>(todayScope())
const applied = ref<FilterScope>({ ...draft.value })
const groupDimension = ref<DimensionKey>('platform')
const data = ref<ComprehensiveData>()
const loading = ref(false)
const rangeError = ref('')
const error = ref('')
let requestId = 0
const available = computed(() => Boolean(data.value?.available))
const metric = (key: BusinessKey) => data.value?.metrics[key]
const hasPending = computed(() => JSON.stringify(draft.value) !== JSON.stringify(applied.value))
const scopeItems = computed(() => dimensions.filter(d => applied.value[d.key]))
const hasMissingProfit = computed(() => businesses.some(b => (metric(b.key)?.profitMissingCount || 0) > 0))
const groupLabel = computed(() => dimensions.find(d => d.key === groupDimension.value)!.label)
const dimensionOptions = dimensions.map(d => ({ label: '按' + d.label, value: d.key }))
const formatter = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const money = (amount: string | number | null | undefined) => amount == null ? '—' : formatter.format(Number(amount))
const count = (amount: number | null | undefined) => amount == null ? '—' : new Intl.NumberFormat('zh-CN').format(amount)
const isNegative = (amount: string | null | undefined) => amount != null && Number(amount) < 0
const chartNumber = (amount: string | null | undefined) => amount == null ? null : Number(amount)
const isBusinessKey = (key: unknown): key is BusinessKey => businesses.some(b => b.key === key)
const filterOptions = (key: DimensionKey) => [{ label: '全部' + dimensions.find(d => d.key === key)!.label, value: '' }, ...(data.value?.options[key] || [])]
function optionLabel(key: DimensionKey, value: string) { return data.value?.options[key].find(o => o.value === value)?.label || JSON.parse(value).filter(Boolean).join(' · ') || '未知' }

async function load(scope: FilterScope) {
  const id = ++requestId
  applied.value = { ...scope }
  const group = groupDimension.value
  loading.value = true
  error.value = ''
  data.value = undefined
  drawerOpen.value = false
  drawerRequestId++
  try {
    const result = await fetchComprehensive(scope, group)
    if (id !== requestId) return
    data.value = result
    error.value = result.error
  } catch (failure) {
    if (id === requestId) error.value = failure instanceof Error ? failure.message : '综合分析查询失败'
  } finally { if (id === requestId) loading.value = false }
}
function applyFilters() {
  const first = Date.parse(draft.value.startDate)
  const last = Date.parse(draft.value.endDate)
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first || last - first > 365 * 86400000) { rangeError.value = '请选择有效日期，结束日期不能早于开始日期，单次不能超过366天。'; return }
  rangeError.value = ''
  void load({ ...draft.value })
}
function applyPreset(value: string | number) {
  const preset = String(value)
  if (preset === 'custom') return
  const today = businessToday()
  let start = today, end = today
  if (preset === 'yesterday') { start = new Date(Date.parse(today) - 86400000).toISOString().slice(0, 10); end = start }
  if (preset === 'month') start = today.slice(0, 7) + '-01'
  if (preset === 'year') start = today.slice(0, 4) + '-01-01'
  draft.value = { ...draft.value, preset, startDate: start, endDate: end }
  applyFilters()
}
function resetFilters() { draft.value = todayScope(); groupDimension.value = 'platform'; applyFilters() }
function removeDimension(key: DimensionKey) { draft.value = { ...applied.value, [key]: '' }; applyFilters() }
function changeGroup() { void load({ ...applied.value }) }
function drillDimension(row: DimensionRow) {
  draft.value = { ...applied.value, [groupDimension.value]: row.value }
  const next = dimensions.find(d => !draft.value[d.key])
  if (next) groupDimension.value = next.key
  applyFilters()
}
const comparisonColumns = computed(() => [
  { title: groupLabel.value, key: 'name', width: 170, fixed: 'left' as const },
  ...businesses.map(b => ({ title: b.label + '利润 / 记录数', key: b.key, width: 165 })),
  { title: '合计利润', key: 'total', width: 145, sorter: (a: DimensionRow, b: DimensionRow) => a.totalProfit == null ? (b.totalProfit == null ? 0 : 1) : b.totalProfit == null ? -1 : Number(a.totalProfit) - Number(b.totalProfit) },
  { title: '继续分析', key: 'action', width: 160, fixed: 'right' as const },
])
const trendOption = computed<EChartsCoreOption>(() => ({
  animation: false, color: businesses.map(b => b.color), tooltip: { trigger: 'axis', valueFormatter: (value: number) => money(value) + ' 元' },
  legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8 }, grid: { left: 60, right: 18, top: 48, bottom: 36 },
  xAxis: { type: 'category', data: data.value?.trend.map(row => row.period) || [] }, yAxis: { type: 'value', name: '利润 / 元' },
  series: [...businesses.map(b => ({ name: b.label, type: 'bar' as const, barMaxWidth: 18, data: data.value?.trend.map(row => chartNumber(row.metrics[b.key].profit)) || [] })), { name: '合计', type: 'line', connectNulls: false, itemStyle: { color: '#263d63' }, data: data.value?.trend.map(row => chartNumber(row.totalProfit)) || [] }],
}))
const compositionOption = computed<EChartsCoreOption>(() => ({
  animation: false, tooltip: { trigger: 'axis', valueFormatter: (value: number) => money(value) + ' 元' },
  grid: { left: 45, right: 25, top: 28, bottom: 35 }, xAxis: { type: 'value' }, yAxis: { type: 'category', inverse: true, data: businesses.map(b => b.label) },
  series: [{ type: 'bar', barMaxWidth: 18, data: businesses.map(b => ({ value: chartNumber(metric(b.key)?.profit), itemStyle: { color: b.color, borderRadius: 3 } })) }],
}))
const drawerOpen = ref(false)
const drawerLoading = ref(false)
const drawerError = ref('')
const drawerData = ref<ComprehensiveData>()
const drawerBusiness = ref<BusinessKey>()
const drawerTitle = ref('日汇总明细')
const drawerScope = ref('')
let drawerRequestId = 0
async function openDetail(business?: BusinessKey, row?: DimensionRow) {
  const id = ++drawerRequestId
  drawerBusiness.value = business
  drawerData.value = undefined
  drawerError.value = ''
  drawerLoading.value = true
  const scope = { ...applied.value, ...(row ? { [groupDimension.value]: row.value } : {}) }
  drawerTitle.value = (row?.name || '当前范围') + ' · ' + (businesses.find(b => b.key === business)?.label || '出退改增') + '日汇总'
  drawerScope.value = dimensions.filter(d => scope[d.key]).map(d => d.label + '：' + optionLabel(d.key, scope[d.key])).join(' · ') || '全部范围'
  drawerOpen.value = true
  try {
    const result = row ? await fetchComprehensive(scope, groupDimension.value) : data.value!
    if (id === drawerRequestId) { drawerData.value = result; drawerError.value = result.error }
  } catch (failure) { if (id === drawerRequestId) drawerError.value = failure instanceof Error ? failure.message : '日汇总查询失败' }
  finally { if (id === drawerRequestId) drawerLoading.value = false }
}
const drawerRows = computed(() => drawerData.value?.available ? drawerData.value.trend.flatMap(day => businesses.filter(b => !drawerBusiness.value || b.key === drawerBusiness.value).map(b => ({ key: day.period + b.key, date: day.period, label: b.label, ...day.metrics[b.key] }))) : [])
const drawerColumns = [{ title: '业务日', dataIndex: 'date', width: 120 }, { title: '业务', dataIndex: 'label', width: 80 }, { title: '源记录数', key: 'count', width: 110 }, { title: '业务估算利润', key: 'profit', width: 160 }, { title: '缺失利润记录数', key: 'missing', width: 130 }]
onMounted(() => { void load({ ...draft.value }) })
</script>

<style scoped>
.comprehensive-page { padding-bottom: 32px; }
.source-banner, .range-error { margin-bottom: 16px; border-radius: 10px; }
.scope-panel { padding: 18px 20px; margin-bottom: 14px; border: 1px solid #e4e9f0; border-radius: 12px; background: #fff; }
.section-heading, .scope-actions, .comparison-toolbar, .comparison-footer, .panel-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading h2 { margin: 0; color: #26344b; font-size: 14px; }
.section-heading > span, .scope-actions > span, .comparison-toolbar > span, .panel-title small { color: #8995a7; font-size: 11px; }
.period-fields { margin: 16px 0; display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
.date-fields { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; color: #6c7a91; font-size: 12px; }
.date-fields :deep(.ant-picker) { width: 142px; }
.dimension-fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.dimension-fields label { display: grid; gap: 7px; min-width: 0; color: #64728a; font-size: 12px; }
.dimension-fields label > span { display: flex; justify-content: space-between; }
.dimension-fields small { color: #a4aebe; font-size: 10px; }
.dimension-fields :deep(.ant-select) { width: 100%; }
.scope-actions { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf0f5; }
.scope-actions > div { display: flex; gap: 9px; }
.applied-scope { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 15px 1px; flex-wrap: wrap; color: #526079; font-size: 12px; }
.summary-grid { display: grid; grid-template-columns: 1.2fr repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-total { padding: 20px; min-width: 0; border-radius: 12px; color: #fff; background: linear-gradient(135deg, #183359, #2b67bf); }
.summary-total > span { color: #d2e2fb; font-size: 12px; }
.summary-total strong, .business-card > strong { display: block; margin: 20px 0 16px; font-size: clamp(18px, 1.8vw, 29px); letter-spacing: -.035em; white-space: nowrap; }
.summary-total em, .business-card em { margin-left: 5px; font-size: 11px; font-weight: 400; font-style: normal; }
.summary-total p, .summary-total small { color: #cbddf6; font-size: 10px; }
.business-card { min-width: 0; padding: 18px 16px 10px; border: 1px solid #e4e9f0; border-top: 3px solid var(--business-color); border-radius: 12px; background: #fff; }
.business-heading { color: #56657d; font-size: 12px; }
.business-card > strong { color: #26354c; font-size: clamp(18px, 1.55vw, 24px); }
.business-count { display: flex; justify-content: space-between; gap: 6px; padding-top: 11px; border-top: 1px solid #edf0f5; color: #919bac; font-size: 10px; }
.business-count b { color: #5a6a83; font-size: 12px; }
.business-link { width: 100%; margin-top: 9px; padding: 4px 0; display: flex; justify-content: space-between; border: 0; background: none; color: #728ba9; font: inherit; font-size: 11px; cursor: pointer; }
.business-link:disabled { color: #b9c1cd; cursor: not-allowed; }
.charts-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(0, 1fr); gap: 16px; margin-bottom: 16px; }
.analysis-panel { min-width: 0; border: 1px solid #e4e9f0; border-radius: 12px; }
.analysis-panel :deep(.ant-card-head) { min-height: 56px; padding: 0 20px; border-color: #edf0f5; font-size: 14px; color: #2e3c52; }
.analysis-panel :deep(.ant-card-body) { padding: 16px 20px; }
.charts-grid :deep(.base-chart) { min-height: 280px; height: 280px; }
.charts-grid :deep(.ant-empty) { min-height: 230px; display: flex; flex-direction: column; justify-content: center; }
.composition-note, .missing-note { color: #97a2b3; font-size: 10px; line-height: 1.7; }
.missing-note { color: #b88635; margin: 8px 0; }
.comparison-toolbar { margin-bottom: 17px; flex-wrap: wrap; }
.dimension-table :deep(.ant-table-thead > tr > th) { color: #7b8799; font-size: 11px; font-weight: 500; background: #f8fafc; }
.dimension-table :deep(.ant-table-cell) { padding: 15px 12px; font-size: 12px; }
.metric-cell { display: grid; gap: 6px; }
.metric-cell span { color: #9ca7b7; font-size: 10px; }
.comparison-footer { flex-wrap: wrap; color: #8b98aa; font-size: 11px; }
.handoff-note { display: flex; gap: 10px; padding: 18px 2px; color: #8293a9; font-size: 11px; line-height: 1.7; }
.handoff-note p { margin: 5px 0; }
.negative { color: #c34b5b !important; }
.drawer-scope { margin: 20px 0; color: #586b86; font-size: 12px; }
@media (max-width: 1200px) { .summary-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } .summary-total { grid-column: 1 / -1; } }
@media (max-width: 900px) { .dimension-fields, .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .charts-grid { grid-template-columns: minmax(0, 1fr); } .section-heading, .scope-actions { flex-wrap: wrap; } }
@media (max-width: 560px) { .scope-panel { padding: 15px 12px; } .date-fields :deep(.ant-picker) { width: 124px; } .business-card { padding-inline: 12px; } .analysis-panel :deep(.ant-card-body) { padding: 14px 12px; } }
</style>
