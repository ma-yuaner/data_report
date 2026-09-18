<template>
  <div class="page-wrap comprehensive-page">
    <PageHeader eyebrow="BUSINESS PERFORMANCE" title="综合分析" description="从经营结果到维度对比，再定位出、退、改、增的具体业务">
      <a-tag color="gold" class="preview-tag"><ExperimentOutlined />界面预览</a-tag>
    </PageHeader>
    <a-alert class="preview-banner" type="warning" show-icon message="演示数据 · 未连接 MySQL / Hive"
      description="本页仅用于确认布局与交互；所有金额、数量和产品分类均为示例，不能作为公司经营结论。原有页面和数据口径不变。" />

    <section class="scope-panel" aria-label="综合分析筛选">
      <div class="section-heading"><h2>统计范围</h2><span>默认今日 · 各业务按自身发生时间统计</span></div>
      <div class="period-fields">
        <a-segmented v-model:value="draft.preset" :options="periodOptions" @change="applyPreset" />
        <div class="date-fields">
          <span>统计期间</span>
          <a-date-picker v-model:value="draft.startDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" placeholder="开始日期" @change="draft.preset = 'custom'" />
          <span>至</span>
          <a-date-picker v-model:value="draft.endDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" placeholder="结束日期" @change="draft.preset = 'custom'" />
        </div>
      </div>
      <div class="dimension-fields">
        <label v-for="dimension in dimensions" :key="dimension.key">
          <span>{{ dimension.label }}<small v-if="dimension.key === 'product'">分类待确认</small></span>
          <a-select v-model:value="draft[dimension.key]" :aria-label="dimension.label + '筛选'"
            :options="filterOptions(dimension.key)" :show-search="true" option-filter-prop="label" />
        </label>
      </div>
      <div class="scope-actions">
        <span>{{ hasPendingChanges ? '条件已变更，点击查询后生效' : '五个维度可组合筛选；结束日期包含当天' }}</span>
        <div><a-button @click="resetFilters"><UndoOutlined />重置</a-button><a-button type="primary" @click="applyFilters"><SearchOutlined />查询</a-button></div>
      </div>
      <a-alert v-if="rangeError" type="error" show-icon :message="rangeError" class="range-error" />
    </section>

    <div class="applied-scope">
      <div><span class="scope-label">当前已查询</span><strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong></div>
      <div class="scope-tags">
        <a-tag v-if="!scopeItems.length" color="blue">全部范围（演示）</a-tag>
        <a-tag v-for="item in scopeItems" :key="item.key" color="blue" closable @close="removeDimension(item.key)">{{ item.label }}：{{ applied[item.key] }}</a-tag>
      </div>
    </div>

    <div class="summary-grid">
      <section class="summary-total" :data-total-cents="hasDemoRecords ? totalCents : undefined">
        <span>总业务估算利润<small>演示</small></span>
        <strong>{{ hasDemoRecords ? money(totalCents) : '—' }}<em v-if="hasDemoRecords">元</em></strong>
        <p>出票 + 退票 + 改签 + 增值</p><small>CNY · 不含风控核对区重复汇总</small>
      </section>
      <section v-for="business in businesses" :key="business.key" class="business-card" :style="{ '--business-color': business.color }">
        <div class="business-heading"><span>{{ business.label }}利润</span><i :style="{ background: business.color }" /></div>
        <strong :class="{ negative: metrics[business.key].profitCents < 0 }" :data-profit-cents="hasDemoRecords ? metrics[business.key].profitCents : undefined">{{ hasDemoRecords ? money(metrics[business.key].profitCents) : '—' }}<em v-if="hasDemoRecords">元</em></strong>
        <div class="business-count"><span>{{ business.countLabel }}</span><b>{{ hasDemoRecords ? count(metrics[business.key].count) : '—' }}</b></div>
        <button type="button" class="business-preview-link" :disabled="!hasDemoRecords" @click="openPreview(business.key)">业务下钻预览<ArrowRightOutlined /></button>
      </section>
    </div>

    <div class="charts-grid">
      <a-card :bordered="false" class="analysis-panel trend-panel">
        <template #title><div class="panel-title"><span>经营利润趋势</span><small>演示 · {{ monthlyTrend ? '按月' : '按日' }}</small></div></template>
        <BaseChart v-if="hasDemoRecords" :option="trendOption" chart-label="演示：出退改增利润及合计趋势" />
        <a-empty v-else description="所选期间或条件没有演示记录" />
      </a-card>
      <a-card :bordered="false" class="analysis-panel composition-panel">
        <template #title><div class="panel-title"><span>四类业务利润构成</span><small>演示 · 元</small></div></template>
        <BaseChart v-if="hasDemoRecords" :option="compositionOption" chart-label="演示：四类业务利润构成" />
        <a-empty v-else description="真实数据尚未接入" />
        <p class="composition-note">利润可以合计，四类业务数量分别列示，不合并为“总票数”。</p>
      </a-card>
    </div>

    <a-card :bordered="false" class="analysis-panel comparison-panel">
      <template #title><div class="panel-title"><span>维度经营对比</span><small>演示 · 由粗到细</small></div></template>
      <div class="comparison-toolbar">
        <a-segmented v-model:value="groupDimension" :options="dimensionOptions" />
        <span>点击合计利润可排序；选择某项后，可继续切换其他维度</span>
      </div>
      <a-table class="dimension-table" :columns="comparisonColumns" :data-source="dimensionRows" row-key="name"
        :pagination="false" :scroll="{ x: 1120 }" size="middle"
        :locale="{ emptyText: '所选期间或条件没有演示记录；真实数据尚未接入' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'"><strong class="dimension-name">{{ record.name }}</strong></template>
          <template v-else-if="isBusinessKey(column.key)">
            <div class="metric-cell"><strong :class="{ negative: record.metrics[column.key].profitCents < 0 }">{{ money(record.metrics[column.key].profitCents) }}<small>元</small></strong><span>{{ count(record.metrics[column.key].count) }} {{ businessMeta(column.key).unit }}</span></div>
          </template>
          <template v-else-if="column.key === 'total'"><strong class="row-total" :class="{ negative: record.totalCents < 0 }">{{ money(record.totalCents) }}<small>元</small></strong></template>
          <template v-else-if="column.key === 'action'">
            <div class="row-actions"><a-button type="link" size="small" :disabled="Boolean(applied[groupDimension])" @click="drillDimension(record)">分析此项</a-button><a-button type="link" size="small" @click="openPreview(undefined, record)">业务预览</a-button></div>
          </template>
        </template>
        <template #footer>
          <div class="comparison-footer"><span>当前范围共 {{ dimensionRows.length }} 个{{ groupLabel }} · 完整列示，不截取 Top N</span><span>合计利润：<strong>{{ hasDemoRecords ? money(totalCents) + ' 元' : '—' }}</strong></span></div>
        </template>
      </a-table>
    </a-card>

    <div class="handoff-note"><InfoCircleOutlined /><div><strong>先确认布局，再补齐数据</strong><p>下一步接入部门与产品归属、联合日汇总及原始明细。本页未计算真实退票率、亏损票数、已结算利润，也不自动判断亏损原因。</p></div></div>

    <a-drawer v-model:open="drawerOpen" :title="drawerTitle" :width="drawerWidth" class="comprehensive-drawer">
      <a-alert type="warning" show-icon message="下钻布局预览 · 全部为演示数据" />
      <div class="drawer-scope"><strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong><p>{{ drawerScopeLabel }}</p></div>
      <a-table :columns="drawerColumns" :data-source="drawerRows" row-key="key" :pagination="false" :scroll="{ x: 480 }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'count'">{{ count(record.count) }} {{ record.unit }}</template>
          <template v-else-if="column.key === 'profit'"><strong :class="{ negative: record.profitCents < 0 }">{{ money(record.profitCents) }} 元</strong></template>
        </template>
      </a-table>
      <div class="detail-heading"><h3>订单 / 业务明细</h3><a-tag>待接入</a-tag></div>
      <a-table :columns="detailColumns" :data-source="[]" :pagination="false" :scroll="{ x: 700 }" :locale="{ emptyText: '真实订单明细待接入，不生成模拟订单和原因结论' }" />
      <p class="drawer-note">正式接入后，将把当前时间与维度条件带到对应业务分析、问题记录和订单明细，不跳回全公司范围。增值服务类别将在增值专题单独展示。</p>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { DatePicker as ADatePicker, Drawer as ADrawer, Empty as AEmpty } from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { ArrowRightOutlined, ExperimentOutlined, InfoCircleOutlined, SearchOutlined, UndoOutlined } from '@ant-design/icons-vue'
import type { EChartsCoreOption } from 'echarts/core'
import PageHeader from '@/components/PageHeader.vue'
import BaseChart from '@/components/BaseChart.vue'
import {
  aggregate, businesses, dimensions, formatDate, generateDemoFacts, groupFacts, matchesScope,
  periodOptions, sumProfit, todayScope,
  type BusinessKey, type DimensionKey, type DimensionRow, type FilterScope, type PeriodPreset,
} from '@/demo/comprehensiveProfit'

const demoFacts = generateDemoFacts()
const draft = ref<FilterScope>(todayScope())
const applied = ref<FilterScope>({ ...draft.value })
const groupDimension = ref<DimensionKey>('platform')
const rangeError = ref('')
const drawerOpen = ref(false)
const drawerBusiness = ref<BusinessKey>()
const drawerDimension = ref<{ key: DimensionKey; name: string }>()
const drawerWidth = 'min(780px, 100vw)'
const hasPendingChanges = computed(() => JSON.stringify(draft.value) !== JSON.stringify(applied.value))
const scopeItems = computed(() => dimensions.filter(dimension => applied.value[dimension.key]))
const filteredFacts = computed(() => demoFacts.filter(fact => matchesScope(fact, applied.value)))
const hasDemoRecords = computed(() => filteredFacts.value.length > 0)
const metrics = computed(() => aggregate(filteredFacts.value))
const totalCents = computed(() => sumProfit(metrics.value))
const dimensionRows = computed(() => groupFacts(filteredFacts.value, groupDimension.value))
const groupLabel = computed(() => dimensions.find(dimension => dimension.key === groupDimension.value)!.label)
const dimensionOptions = dimensions.map(dimension => ({ label: '按' + dimension.label, value: dimension.key }))
const money = (cents: number) => new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(cents / 100)
const count = (value: number) => new Intl.NumberFormat('zh-CN').format(value)
const businessMeta = (key: BusinessKey) => businesses.find(business => business.key === key)!
const isBusinessKey = (key: unknown): key is BusinessKey => businesses.some(business => business.key === key)
const filterOptions = (key: DimensionKey) => [
  { label: '全部' + dimensions.find(dimension => dimension.key === key)!.label, value: '' },
  ...[...new Set(demoFacts.map(fact => fact[key]))].map(value => ({ label: value, value })),
]

function applyFilters() {
  const start = new Date(draft.value.startDate + 'T00:00:00')
  const end = new Date(draft.value.endDate + 'T00:00:00')
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end < start) {
    rangeError.value = '请选择有效的起止日期，结束日期不能早于开始日期。'
    return
  }
  if ((end.getTime() - start.getTime()) / 86400000 > 365) {
    rangeError.value = '单次统计期间不能超过366天。'
    return
  }
  rangeError.value = ''
  applied.value = { ...draft.value }
  drawerOpen.value = false
}
function applyPreset(value: string | number) {
  const preset = String(value) as PeriodPreset
  if (preset === 'custom') return
  const today = new Date()
  let start = today
  let end = today
  if (preset === 'yesterday') {
    start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1)
    end = start
  } else if (preset === 'month') {
    start = new Date(today.getFullYear(), today.getMonth(), 1)
  } else if (preset === 'year') {
    start = new Date(today.getFullYear(), 0, 1)
  }
  draft.value = { ...draft.value, preset, startDate: formatDate(start), endDate: formatDate(end) }
  applyFilters()
}
function resetFilters() {
  draft.value = todayScope()
  groupDimension.value = 'platform'
  applyFilters()
}
function removeDimension(key: DimensionKey) {
  draft.value = { ...applied.value, [key]: '' }
  applyFilters()
}
function drillDimension(row: DimensionRow) {
  draft.value = { ...applied.value, [groupDimension.value]: row.name }
  applyFilters()
  const next = dimensions.find(dimension => !applied.value[dimension.key])
  if (next) groupDimension.value = next.key
}
const comparisonColumns = computed(() => [
  { title: groupLabel.value, key: 'name', width: 155, fixed: 'left' as const },
  ...businesses.map(business => ({ title: business.label + '利润 / ' + business.countLabel, key: business.key, width: 165 })),
  { title: '合计利润', key: 'total', width: 145, sorter: (left: DimensionRow, right: DimensionRow) => left.totalCents - right.totalCents },
  { title: '继续分析', key: 'action', width: 160, fixed: 'right' as const },
])
const monthlyTrend = computed(() => (new Date(applied.value.endDate).getTime() - new Date(applied.value.startDate).getTime()) / 86400000 > 62)
const trendRows = computed(() => {
  const periods = new Map<string, typeof filteredFacts.value>()
  for (const fact of filteredFacts.value) {
    const period = monthlyTrend.value ? fact.date.slice(0, 7) : fact.date
    if (!periods.has(period)) periods.set(period, [])
    periods.get(period)!.push(fact)
  }
  return [...periods.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([period, facts]) => ({ period, metrics: aggregate(facts) }))
})
const trendOption = computed<EChartsCoreOption>(() => ({
  color: businesses.map(business => business.color),
  tooltip: { trigger: 'axis', valueFormatter: (value: number) => money(Math.round(value * 100)) + ' 元' },
  legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: '#758297', fontSize: 11 } },
  grid: { left: 56, right: 14, top: 48, bottom: 30 },
  xAxis: { type: 'category', data: trendRows.value.map(row => row.period), axisLine: { lineStyle: { color: '#dce3ed' } }, axisTick: { show: false }, axisLabel: { color: '#8a96a7', fontSize: 10 } },
  yAxis: { type: 'value', name: '利润 / 元', nameTextStyle: { color: '#8a96a7', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf1f6' } }, axisLabel: { formatter: (value: number) => Number((value / 10000).toFixed(1)) + '万', color: '#8a96a7', fontSize: 10 } },
  series: [
    ...businesses.map(business => ({ name: business.label, type: 'bar' as const, barMaxWidth: 18, data: trendRows.value.map(row => row.metrics[business.key].profitCents / 100) })),
    { name: '合计', type: 'line', itemStyle: { color: '#263d63' }, lineStyle: { width: 2 }, symbolSize: 5, data: trendRows.value.map(row => sumProfit(row.metrics) / 100) },
  ],
}))
const compositionOption = computed<EChartsCoreOption>(() => ({
  tooltip: { trigger: 'axis', valueFormatter: (value: number) => money(Math.round(value * 100)) + ' 元' },
  grid: { left: 42, right: 55, top: 28, bottom: 32 },
  xAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf1f6' } }, axisLabel: { color: '#8a96a7', fontSize: 10, formatter: (value: number) => Number((value / 10000).toFixed(1)) + '万' } },
  yAxis: { type: 'category', inverse: true, data: businesses.map(business => business.label), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#536176', fontSize: 12 } },
  series: [{ type: 'bar', barMaxWidth: 17, data: businesses.map(business => ({ value: metrics.value[business.key].profitCents / 100, itemStyle: { color: business.color, borderRadius: 3 } })) }],
}))
function openPreview(business?: BusinessKey, row?: DimensionRow) {
  drawerBusiness.value = business
  drawerDimension.value = row ? { key: groupDimension.value, name: row.name } : undefined
  drawerOpen.value = true
}
const drawerTitle = computed(() => (drawerDimension.value?.name ?? '当前范围') + ' · ' + (drawerBusiness.value ? businessMeta(drawerBusiness.value).label : '出退改增') + '下钻预览')
const drawerScopeLabel = computed(() => {
  const scope = { ...applied.value }
  if (drawerDimension.value) scope[drawerDimension.value.key] = drawerDimension.value.name
  return dimensions.filter(dimension => scope[dimension.key]).map(dimension => dimension.label + '：' + scope[dimension.key]).join(' · ') || '全部范围（演示）'
})
const drawerRows = computed(() => {
  const facts = filteredFacts.value.filter(fact => !drawerDimension.value || fact[drawerDimension.value.key] === drawerDimension.value.name)
  const summary = aggregate(facts)
  return businesses.filter(business => !drawerBusiness.value || business.key === drawerBusiness.value).map(business => ({ ...business, ...summary[business.key] }))
})
const drawerColumns = [
  { title: '业务类型', dataIndex: 'label', key: 'business' }, { title: '业务数量', key: 'count' }, { title: '业务估算利润（演示）', key: 'profit' },
]
const detailColumns = [
  { title: '发生时间', key: 'date', width: 120 }, { title: '订单 / 业务单号', key: 'order', width: 160 },
  { title: '航司', key: 'airline', width: 70 }, { title: '产品', key: 'product', width: 100 },
  { title: '业务估算利润', key: 'profit', width: 130 }, { title: '原因 / 证据', key: 'reason', width: 120 },
]
</script>

<style scoped>
.comprehensive-page { padding-bottom: 32px; }
.preview-tag { padding: 5px 10px; border-radius: 7px; }
.preview-tag :deep(.anticon) { margin-right: 6px; }
.preview-banner { margin-bottom: 16px; border-radius: 10px; }
.preview-banner :deep(.ant-alert-description) { font-size: 12px; }
.scope-panel { padding: 18px 20px; margin-bottom: 14px; border: 1px solid #e4e9f0; border-radius: 12px; background: #fff; }
.section-heading, .scope-actions, .comparison-toolbar, .comparison-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading h2 { margin: 0; color: #26344b; font-size: 14px; font-weight: 600; }
.section-heading > span, .scope-actions > span, .comparison-toolbar > span { color: #8995a7; font-size: 11px; }
.period-fields { margin: 16px 0; display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.date-fields { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; color: #6c7a91; font-size: 12px; }
.date-fields :deep(.ant-picker) { width: 142px; }
.dimension-fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.dimension-fields label { display: grid; gap: 7px; min-width: 0; }
.dimension-fields label > span { display: flex; justify-content: space-between; color: #64728a; font-size: 12px; }
.dimension-fields small { color: #a4aebe; font-size: 10px; }
.dimension-fields :deep(.ant-select) { width: 100%; }
.scope-actions { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf0f5; }
.scope-actions > div { display: flex; gap: 9px; }
.range-error { margin-top: 12px; }
.applied-scope, .scope-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.applied-scope { justify-content: space-between; margin: 15px 1px; }
.applied-scope > div:first-child { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: #526079; }
.scope-label { color: #8a96a8; }
.scope-tags :deep(.ant-tag) { margin-inline-end: 0; }
.summary-grid { display: grid; grid-template-columns: 1.2fr repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-total { min-width: 0; padding: 20px; border-radius: 12px; color: #fff; background: linear-gradient(135deg, #183359, #2b67bf); box-shadow: 0 8px 22px #25599a14; }
.summary-total > span { display: flex; justify-content: space-between; gap: 5px; color: #d2e2fb; font-size: 12px; }
.summary-total > span small { padding: 1px 5px; border-radius: 4px; background: #ffffff15; font-size: 9px; }
.summary-total strong { display: block; margin: 20px 0 11px; font-size: clamp(20px, 1.8vw, 29px); font-weight: 650; letter-spacing: -.035em; white-space: nowrap; }
.summary-total em, .business-card em { margin-left: 5px; font-size: 11px; font-style: normal; font-weight: 400; }
.summary-total p { margin: 0 0 6px; color: #cbddf6; font-size: 10px; }
.summary-total > small { color: #adcaee; font-size: 9px; }
.business-card { min-width: 0; padding: 18px 16px 10px; border: 1px solid #e4e9f0; border-top: 3px solid var(--business-color); border-radius: 12px; background: #fff; }
.business-heading { display: flex; justify-content: space-between; align-items: center; color: #56657d; font-size: 12px; }
.business-heading i { width: 7px; height: 7px; border-radius: 50%; }
.business-card > strong { display: block; margin: 19px 0 17px; color: #26354c; font-size: clamp(18px, 1.55vw, 24px); font-weight: 650; letter-spacing: -.04em; white-space: nowrap; }
.business-count { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding-top: 11px; border-top: 1px solid #edf0f5; }
.business-count span { color: #919bac; font-size: 10px; }
.business-count b { color: #5a6a83; font-size: 12px; font-weight: 600; }
.business-preview-link { width: 100%; margin-top: 9px; padding: 4px 0; display: flex; align-items: center; justify-content: space-between; border: 0; background: none; color: #8a99ae; font: inherit; font-size: 10px; cursor: pointer; }
.business-preview-link:hover { color: #3178f6; }
.business-preview-link:disabled { color: #b9c1cd; cursor: not-allowed; }
.charts-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(0, 1fr); gap: 16px; margin-bottom: 16px; }
.analysis-panel { min-width: 0; border: 1px solid #e4e9f0; border-radius: 12px; }
.analysis-panel :deep(.ant-card-head) { min-height: 56px; padding: 0 20px; border-color: #edf0f5; }
.analysis-panel :deep(.ant-card-body) { padding: 16px 20px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.panel-title > span { font-size: 14px; color: #2e3c52; }
.panel-title > small { color: #9aa5b4; font-size: 10px; font-weight: 400; }
.trend-panel :deep(.base-chart) { height: 292px; min-height: 292px; }
.composition-panel :deep(.base-chart) { height: 253px; min-height: 253px; }
.composition-note { margin: 8px 0 0; color: #97a2b3; font-size: 10px; line-height: 1.7; }
.charts-grid :deep(.ant-empty) { min-height: 230px; display: flex; flex-direction: column; justify-content: center; }
.comparison-toolbar { margin-bottom: 17px; flex-wrap: wrap; }
.dimension-name { color: #41516b; font-size: 12px; font-weight: 600; }
.dimension-table :deep(.ant-table-thead > tr > th) { color: #7b8799; font-size: 11px; font-weight: 500; background: #f8fafc; }
.dimension-table :deep(.ant-table-cell) { padding: 15px 12px; }
.metric-cell { display: grid; gap: 6px; }
.metric-cell strong { color: #42536d; font-size: 12px; font-weight: 600; white-space: nowrap; }
.metric-cell > span { color: #9ca7b7; font-size: 10px; }
.metric-cell strong > small, .row-total > small { margin-left: 4px; color: #a2acba; font-size: 9px; font-weight: 400; }
.row-total { color: #274d89; font-size: 12px; white-space: nowrap; }
.row-actions { display: flex; align-items: center; }
.row-actions :deep(.ant-btn) { padding-inline: 4px; font-size: 11px; }
.comparison-footer { flex-wrap: wrap; color: #8b98aa; font-size: 11px; }
.comparison-footer strong { color: #4d627f; font-size: 12px; }
.handoff-note { display: flex; align-items: flex-start; gap: 10px; padding: 15px 2px; color: #98a4b5; }
.handoff-note > :deep(.anticon) { margin-top: 2px; color: #7e99bb; }
.handoff-note strong { color: #72839b; font-size: 11px; font-weight: 500; }
.handoff-note p { margin: 5px 0 0; font-size: 11px; line-height: 1.7; }
.negative { color: #c34b5b !important; }
.drawer-scope { margin: 20px 0; color: #586b86; font-size: 12px; }
.drawer-scope p { margin: 8px 0; color: #8b98ab; line-height: 1.7; }
.detail-heading { margin: 28px 0 14px; display: flex; align-items: center; justify-content: space-between; }
.detail-heading h3 { margin: 0; color: #455772; font-size: 14px; }
.drawer-note { margin-top: 20px; color: #8c99ac; font-size: 12px; line-height: 1.8; }
@media (max-width: 1200px) {
  .summary-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .summary-total { grid-column: 1 / -1; }
  .summary-total strong { margin: 12px 0; font-size: 30px; }
  .charts-grid { grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); }
}
@media (max-width: 900px) {
  .dimension-fields, .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .charts-grid { grid-template-columns: minmax(0, 1fr); }
  .section-heading, .scope-actions { align-items: flex-start; flex-wrap: wrap; }
  .scope-actions > div { margin-left: auto; }
}
@media (max-width: 560px) {
  .scope-panel { padding: 15px 12px; }
  .period-fields { gap: 12px; }
  .date-fields { gap: 7px; }
  .date-fields > span:first-child { width: 100%; }
  .date-fields :deep(.ant-picker) { width: 124px; }
  .dimension-fields { gap: 12px; }
  .analysis-panel :deep(.ant-card-body) { padding: 14px 12px; }
  .business-card { padding-inline: 12px; }
  .business-card > strong { font-size: 18px; }
}
</style>
