<template>
  <div class="page-wrap risk-monthly-page">
    <PageHeader eyebrow="RISK CONTROL" title="风控分析" description="利润核对 · 快速对比出票、改签、退票的票数与月度金额"><a-tag color="blue">实际数据 · MySQL</a-tag></PageHeader>
    <a-alert class="source-banner" type="info" show-icon :message="data?.source || 'MySQL · sibebid'" :description="'金额为CNY预估利润，不代表财务结算。' + (data ? ' 查询于：' + data.generatedAt.replace('T', ' ').slice(0, 19) : '')" />
    <section class="scope-panel">
      <div class="section-heading"><h2>核对记录统计范围</h2><span>默认今日 · 可快速切换本年查看月度对比</span></div>
      <div class="period-fields"><a-segmented v-model:value="preset" :options="periodOptions" :disabled="loading" @change="applyPreset" />
        <div class="date-fields"><a-date-picker v-model:value="draft.startDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" @change="preset = 'custom'" /><span>至</span><a-date-picker v-model:value="draft.endDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" @change="preset = 'custom'" /></div>
      </div>
      <div class="filter-fields">
        <label><span>快捷选择年份</span><a-select v-model:value="year" :options="yearOptions" :disabled="loading" @change="selectYear" /></label>
        <label><span>业务类型</span><a-select v-model:value="draft.businessType" :options="businessOptions" :disabled="loading" /></label>
        <label><span>盈亏范围</span><a-select v-model:value="draft.profitStatus" :options="profitOptions" :disabled="loading" /></label>
        <label><span>月份日期口径</span><a-select v-model:value="draft.dateBasis" :options="dateBasisOptions" :disabled="loading" /></label>
      </div>
      <div class="scope-actions"><span>{{ hasPending ? '条件已变更，查询后生效' : '结束日期包含当天；默认不额外限定亏损记录' }}</span><div><a-button :disabled="loading" @click="resetFilters">重置</a-button><a-button type="primary" :loading="loading" @click="applyFilters">查询</a-button></div></div>
      <a-alert v-if="rangeError" class="range-error" type="error" show-icon :message="rangeError" />
    </section>
    <div class="applied-scope"><strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong><div><a-tag>{{ labelOf(businessOptions, applied.businessType) }}</a-tag><a-tag>{{ labelOf(profitOptions, applied.profitStatus) }}</a-tag><a-tag>{{ labelOf(dateBasisOptions, applied.dateBasis) }}</a-tag></div></div>
    <p class="time-basis">{{ data?.businesses.map(b => b.label + '：' + b.timeField).join(' · ') }}</p>
    <a-alert v-if="error" class="range-error" type="error" show-icon :message="error" />
    <a-alert v-if="data?.available && data.summary.status === 'no_records'" class="range-error" type="warning" show-icon message="所选期间在当前核对表中没有记录，请切换本年/其他日期或检查同步覆盖。没有记录不代表公司没有业务。" />
    <a-alert v-if="hasMissing" class="range-error" type="warning" show-icon message="源票数或利润存在NULL，受影响的完整指标显示为—；已知部分单列，不按0填补。" />
    <a-spin :spinning="loading" tip="正在查询MySQL核对记录">
      <div class="summary-grid" :style="{ '--card-count': (data?.businesses.length || 3) + 1 }">
        <section class="summary-total"><span>所选核对记录金额合计</span><strong :data-summary-profit="data?.summary.estimatedProfit ?? undefined">{{ money(data?.summary.estimatedProfit) }}<em v-if="data?.summary.estimatedProfit != null">元</em></strong><p>仅合计当前所选出退改核对记录</p><small>不重复计入经营总览预估利润</small></section>
        <section v-for="business in data?.businesses || []" :key="business.key" class="business-card" :data-business="business.key" :style="{ '--business-color': colors[business.key] }">
          <div class="business-heading"><span>{{ business.label }}</span><a-tag v-if="business.metrics.status === 'no_records'">无记录</a-tag></div>
          <strong :class="{ negative: negative(business.metrics.estimatedProfit) }" :data-profit="business.metrics.estimatedProfit ?? undefined">{{ money(business.metrics.estimatedProfit) }}<em v-if="business.metrics.estimatedProfit != null">元</em></strong>
          <div class="business-count"><span>{{ business.label }}票数</span><b :data-tickets="business.metrics.ticketCount ?? undefined">{{ count(business.metrics.ticketCount) }}</b></div>
          <p v-if="business.metrics.profitMissingCount" class="missing-note">利润缺失 {{ count(business.metrics.profitMissingCount) }} 条 · 已知 {{ money(business.metrics.knownProfit) }} 元</p>
          <p v-if="business.metrics.ticketMissingCount" class="missing-note">票数缺失 {{ count(business.metrics.ticketMissingCount) }} 条 · 已知 {{ count(business.metrics.knownTicketCount) }} 票</p>
        </section>
      </div>
      <a-card :bordered="false" class="analysis-panel trend-panel"><template #title><div class="panel-title"><span>月度趋势对比</span><a-segmented v-model:value="chartMetric" :options="[{ label: '利润金额', value: 'profit' }, { label: '票数', value: 'tickets' }]" /></div></template>
        <BaseChart v-if="data?.available && data.summary.status !== 'no_records'" :option="trendOption" chart-label="出退改月度票数与预估利润趋势" /><a-empty v-else description="所选核对表记录未就绪或没有记录，不显示模拟结果" />
        <p class="chart-note">负数保留原值；无记录或缺失指标留空，不画成0。标注“部分期间”的月份只统计所选日期，不与整月等同。</p>
      </a-card>
      <a-card :bordered="false" class="analysis-panel monthly-panel"><template #title><div class="panel-title"><span>月度票数与金额对比</span><small>每行一个月份 · 出退改并列查看</small></div></template>
        <a-table class="monthly-table" :columns="columns" :data-source="data?.months || []" row-key="month" :pagination="false" :scroll="{ x: 1120 }" :locale="{ emptyText: '查询成功后显示所选期间的月度数据' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'month'"><strong>{{ record.label }}</strong><a-tag v-if="record.isPartial" color="gold" class="partial-tag">部分期间</a-tag></template>
            <template v-else-if="column.business">
              <span v-if="column.metric === 'tickets'">{{ count(record.metrics[column.business]?.ticketCount) }}</span>
              <div v-else class="profit-cell"><strong :class="{ negative: negative(record.metrics[column.business]?.estimatedProfit) }">{{ money(record.metrics[column.business]?.estimatedProfit) }}</strong><small v-if="record.metrics[column.business]?.profitMissingCount">缺失 {{ count(record.metrics[column.business].profitMissingCount) }} 条 · 已知 {{ money(record.metrics[column.business].knownProfit) }}</small><small v-else-if="record.metrics[column.business]?.status === 'no_records'">无记录</small></div>
            </template>
            <template v-else-if="column.key === 'total'"><strong :class="{ negative: negative(record.summary.estimatedProfit) }">{{ money(record.summary.estimatedProfit) }}</strong></template>
            <template v-else-if="column.key === 'action'"><a-button type="link" size="small" :disabled="loading" @click="selectMonth(record.month)">看本月</a-button></template>
          </template>
          <template #footer><div class="comparison-footer"><span>当前范围 {{ data?.months.length || 0 }} 个月份 · 票数按ticket_num求和，不以记录条数替代</span><strong>预估利润合计：{{ money(data?.summary.estimatedProfit) }} 元</strong></div></template>
        </a-table>
      </a-card>
    </a-spin>
    <div class="notes"><InfoCircleOutlined /><div><strong>统计口径与边界</strong><p v-for="note in data?.notes || []" :key="note">{{ note }}</p></div></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { DatePicker as ADatePicker, Empty as AEmpty } from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import type { EChartsCoreOption } from 'echarts/core'
import PageHeader from '@/components/PageHeader.vue'
import BaseChart from '@/components/BaseChart.vue'
import { getRiskMonthly, type RiskMonthlyData, type RiskScope } from '@/api/riskMonthly'

const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const currentYear = Number(today().slice(0, 4))
function todayScope(): RiskScope { const day = today(); return { startDate: day, endDate: day, businessType: 'all', profitStatus: 'all', dateBasis: 'reconcile' } }
const draft = ref<RiskScope>(todayScope())
const applied = ref<RiskScope>({ ...draft.value })
const preset = ref('today')
const year = ref(currentYear)
const data = ref<RiskMonthlyData>()
const loading = ref(false)
const error = ref('')
const rangeError = ref('')
const chartMetric = ref('profit')
let requestId = 0
const colors = { issue: '#397cf6', change: '#8570cf', refund: '#e7a343' }
const periodOptions = [{ label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' }, { label: '本月', value: 'month' }, { label: '本年', value: 'year' }, { label: '自定义', value: 'custom' }]
const yearOptions = Array.from({ length: 6 }, (_, i) => ({ label: String(currentYear - i) + '年', value: currentYear - i }))
const businessOptions = [{ label: '出退改全部', value: 'all' }, { label: '出票', value: 'issue' }, { label: '改签', value: 'change' }, { label: '退票', value: 'refund' }]
const profitOptions = [{ label: '全部盈亏', value: 'all' }, { label: '亏损记录', value: 'loss' }, { label: '盈利记录', value: 'profit' }, { label: '零利润记录', value: 'zero' }]
const dateBasisOptions = [{ label: '与经营总览一致', value: 'overview' }, { label: '源核对日期', value: 'reconcile' }]
const labelOf = (options: { label: string; value: string }[], value: string) => options.find(o => o.value === value)?.label || value
const hasPending = computed(() => JSON.stringify(draft.value) !== JSON.stringify(applied.value))
const hasMissing = computed(() => Boolean(data.value?.summary.profitMissingCount || data.value?.summary.ticketMissingCount))
const formatter = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const money = (value: string | null | undefined) => value == null ? '—' : formatter.format(Number(value))
const count = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value)
const negative = (value: string | null | undefined) => value != null && Number(value) < 0

async function applyFilters() {
  const first = Date.parse(draft.value.startDate), last = Date.parse(draft.value.endDate)
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first || last - first > 365 * 86400000) { rangeError.value = '请选择有效日期，结束日期不能早于开始日期，单次不超过366天。'; return }
  rangeError.value = ''
  const id = ++requestId, scope = { ...draft.value }
  applied.value = scope
  loading.value = true
  data.value = undefined
  error.value = ''
  try { const result = await getRiskMonthly(scope); if (id === requestId) { data.value = result; error.value = result.error } }
  catch (failure) { if (id === requestId) error.value = failure instanceof Error ? failure.message : '风控月度查询失败' }
  finally { if (id === requestId) loading.value = false }
}
function applyPreset(value: string | number) {
  if (value === 'custom') return
  const day = today()
  let first = day, last = day
  if (value === 'yesterday') { first = new Date(Date.parse(day) - 86400000).toISOString().slice(0, 10); last = first }
  if (value === 'month') first = day.slice(0, 7) + '-01'
  if (value === 'year') first = day.slice(0, 4) + '-01-01'
  year.value = currentYear
  draft.value = { ...draft.value, startDate: first, endDate: last }
  void applyFilters()
}
function selectYear() { preset.value = year.value === currentYear ? 'year' : 'custom'; draft.value = { ...draft.value, startDate: String(year.value) + '-01-01', endDate: year.value === currentYear ? today() : String(year.value) + '-12-31' }; void applyFilters() }
function selectMonth(month: string) {
  const lastDay = new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0)).toISOString().slice(0, 10)
  preset.value = 'custom'
  year.value = Number(month.slice(0, 4))
  draft.value = { ...applied.value, startDate: month + '-01', endDate: month === today().slice(0, 7) ? today() : lastDay }
  void applyFilters()
}
function resetFilters() { preset.value = 'today'; year.value = currentYear; draft.value = todayScope(); void applyFilters() }
const columns = computed(() => [
  { title: '月份', key: 'month', width: 160, fixed: 'left' as const },
  ...(data.value?.businesses || []).map(b => ({ title: b.label, children: [{ title: '票数', key: b.key + '-tickets', business: b.key, metric: 'tickets', width: 90 }, { title: '预估利润 / 元', key: b.key + '-profit', business: b.key, metric: 'profit', width: 155 }] })),
  { title: '核对金额合计 / 元', key: 'total', width: 165 }, { title: '快速筛选', key: 'action', width: 100, fixed: 'right' as const },
])
const trendOption = computed<EChartsCoreOption>(() => ({
  animation: false, color: (data.value?.businesses || []).map(b => colors[b.key]), tooltip: { trigger: 'axis' },
  legend: { top: 0, left: 0 }, grid: { left: 80, right: 20, top: 48, bottom: 40 },
  xAxis: { type: 'category', data: data.value?.months.map(month => month.month + (month.isPartial ? '（部分）' : '')) || [] },
  yAxis: { type: 'value', name: chartMetric.value === 'profit' ? '预估利润 / 元' : '票数' },
  series: (data.value?.businesses || []).map(b => ({ name: b.label, type: 'bar' as const, barMaxWidth: 25, data: data.value?.months.map(month => { const value = chartMetric.value === 'profit' ? month.metrics[b.key]?.estimatedProfit : month.metrics[b.key]?.ticketCount; return value == null ? null : Number(value) }) || [] })),
}))
onMounted(() => { void applyFilters() })
</script>

<style scoped>
.source-banner, .range-error { margin-bottom: 16px; border-radius: 10px; }
.scope-panel { padding: 18px 20px; margin-bottom: 14px; border: 1px solid #e4e9f0; border-radius: 12px; background: #fff; }
.section-heading, .scope-actions, .panel-title, .comparison-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading h2 { margin: 0; font-size: 14px; color: #26344b; }
.section-heading > span, .scope-actions > span, .panel-title small { color: #8995a7; font-size: 11px; }
.period-fields { margin: 16px 0; display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.date-fields { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; color: #6c7a91; font-size: 12px; }
.date-fields :deep(.ant-picker) { width: 142px; }
.filter-fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.filter-fields label { display: grid; gap: 7px; min-width: 0; color: #64728a; font-size: 12px; }
.filter-fields :deep(.ant-select) { width: 100%; }
.scope-actions { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf0f5; }
.scope-actions > div { display: flex; gap: 9px; }
.applied-scope { display: flex; justify-content: space-between; gap: 12px; margin: 15px 1px 5px; align-items: center; flex-wrap: wrap; color: #526079; font-size: 12px; }
.time-basis { margin: 0 0 16px; color: #8996a8; font-size: 11px; }
.summary-grid { display: grid; grid-template-columns: repeat(var(--card-count), minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }
.summary-total { padding: 20px; min-width: 0; border-radius: 12px; color: #fff; background: linear-gradient(135deg, #343b67, #6558a5); }
.summary-total > span { color: #dedbf3; font-size: 12px; }
.summary-total strong, .business-card > strong { display: block; margin: 20px 0 17px; font-size: clamp(18px, 1.7vw, 28px); letter-spacing: -.035em; white-space: nowrap; }
.summary-total em, .business-card em { margin-left: 5px; font-size: 11px; font-weight: 400; font-style: normal; }
.summary-total p, .summary-total small { color: #d1d0ec; font-size: 10px; }
.business-card { min-width: 0; padding: 18px 18px 14px; border: 1px solid #e4e9f0; border-top: 3px solid var(--business-color); border-radius: 12px; background: #fff; }
.business-heading { display: flex; justify-content: space-between; align-items: center; color: #56657d; font-size: 13px; }
.business-card > strong { color: #26354c; font-size: clamp(18px, 1.7vw, 26px); }
.business-count { display: flex; justify-content: space-between; padding-top: 11px; border-top: 1px solid #edf0f5; color: #919bac; font-size: 11px; }
.business-count b { color: #5a6a83; font-size: 14px; }
.missing-note { color: #b88635; font-size: 10px; margin: 8px 0; }
.analysis-panel { min-width: 0; margin-bottom: 16px; border: 1px solid #e4e9f0; border-radius: 12px; }
.analysis-panel :deep(.ant-card-head) { min-height: 56px; padding: 0 20px; border-color: #edf0f5; font-size: 14px; color: #2e3c52; }
.analysis-panel :deep(.ant-card-body) { padding: 16px 20px; }
.trend-panel :deep(.base-chart) { min-height: 300px; height: 300px; }
.chart-note { color: #97a2b3; font-size: 11px; line-height: 1.7; }
.monthly-table :deep(.ant-table-cell) { padding: 14px 10px; font-size: 12px; }
.monthly-table :deep(.ant-table-thead > tr > th) { color: #6e7d94; font-size: 11px; background: #f8fafc; }
.partial-tag { display: block; width: fit-content; margin-top: 6px; font-size: 10px; }
.profit-cell { display: grid; gap: 5px; }
.profit-cell small { color: #9ca7b7; font-size: 10px; }
.comparison-footer { flex-wrap: wrap; color: #8b98aa; font-size: 11px; }
.notes { display: flex; gap: 10px; padding: 10px 2px; color: #8293a9; font-size: 11px; line-height: 1.7; }
.notes p { margin: 5px 0; }
.negative { color: #c34b5b !important; }
@media (max-width: 1100px) { .summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } .summary-total { grid-column: 1 / -1; } }
@media (max-width: 800px) { .filter-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } .summary-grid { grid-template-columns: minmax(0, 1fr); } .section-heading, .scope-actions, .panel-title { flex-wrap: wrap; } }
@media (max-width: 560px) { .scope-panel { padding: 15px 12px; } .period-fields :deep(.ant-segmented) { max-width: 100%; overflow-x: auto; } .analysis-panel :deep(.ant-card-body) { padding: 14px 12px; } }
</style>
