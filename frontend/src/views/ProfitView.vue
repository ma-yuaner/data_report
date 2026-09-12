<template>
  <div class="page-wrap issue-analysis-page">
    <PageHeader eyebrow="ISSUE PROFIT ANALYSIS" title="出票利润分析" description="从利润结果定位平台、航司、供应商和组织差异，同时检查分析字段是否齐全">
      <a-button :loading="loading" @click="loadData"><ReloadOutlined />刷新数据</a-button>
    </PageHeader>

    <DataStateBar
      :label="data?.mode === 'live' ? 'Hive实际数据' : '演示数据'"
      :message="data?.source ?? '正在连接出票利润数据集'"
      :freshness="data ? `查询时间 ${data.generatedAt.slice(11, 19)}` : '查询中'"
      metric-state="业务估算口径"
    />

    <div class="profit-filter">
      <div class="profit-filter-fields">
        <a-segmented v-model:value="periodPreset" :options="periodOptions" @change="applyPreset" />
        <span class="filter-label">出票日期</span>
        <a-date-picker v-model:value="startDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
        <span class="date-separator">至</span>
        <a-date-picker v-model:value="endDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
        <a-button type="primary" :loading="loading" @click="loadData"><SearchOutlined />查询</a-button>
      </div>
      <span class="filter-tip">与经营总览保持同一出票过滤口径</span>
    </div>

    <a-alert v-if="error" type="error" show-icon :message="error" class="section-gap" />

    <a-spin :spinning="loading">
      <template v-if="data?.available && data.summary">
        <div class="issue-summary-grid">
          <a-card v-for="item in summaryCards" :key="item.label" class="issue-summary-card" :bordered="false">
            <span>{{ item.label }}</span>
            <strong :class="{ negative: item.negative }">{{ item.value }}</strong>
            <small>{{ item.description }}</small>
          </a-card>
        </div>

        <div class="dashboard-grid issue-main-grid">
          <a-card class="panel-card" :bordered="false" title="出票利润趋势">
            <template #extra><span class="panel-caption">{{ data.trend.granularity === 'month' ? '按月' : '按日' }}汇总</span></template>
            <BaseChart :option="trendOption" chart-label="出票利润与出票数趋势" />
          </a-card>
          <a-card class="panel-card coverage-overview-card" :bordered="false" title="数据齐全度">
            <div class="coverage-score">
              <a-progress type="dashboard" :percent="data.coverageSummary?.averageRate ?? 0" :stroke-color="coverageColor" />
              <div><strong>{{ data.coverageSummary?.ready ?? 0 }}</strong><span>个字段达到95%</span></div>
            </div>
            <div class="coverage-state-row">
              <span><i class="state-ready" />齐全 {{ data.coverageSummary?.ready ?? 0 }}</span>
              <span><i class="state-partial" />需补 {{ data.coverageSummary?.partial ?? 0 }}</span>
              <span><i class="state-missing" />缺失 {{ data.coverageSummary?.missing ?? 0 }}</span>
            </div>
            <p>齐全度表示当前出票范围内字段非空比例，不代表字段口径已经获得财务确认。</p>
          </a-card>
        </div>

        <div class="dimension-profit-grid">
          <a-card v-for="item in dimensionPanels" :key="item.key" class="panel-card" :bordered="false" :title="item.title">
            <template #extra><span class="panel-caption">按利润绝对值 Top 8</span></template>
            <BaseChart :option="dimensionOption(item.key)" :chart-label="`${item.title}图`" />
          </a-card>
        </div>

        <a-card class="panel-card field-coverage-card" :bordered="false" title="关键分析字段体检">
          <template #extra><span class="panel-caption">共 {{ data.completeness.length }} 个首批字段</span></template>
          <a-table :columns="coverageColumns" :data-source="data.completeness" :pagination="false" row-key="field" size="middle" :scroll="{ x: 860 }">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'field'">
                <div class="field-name"><strong>{{ record.label }}</strong><code>{{ record.field }}</code></div>
              </template>
              <template v-else-if="column.key === 'coverage'">
                <div class="field-progress"><a-progress :percent="record.rate" :stroke-color="stateColor(record.state)" size="small" /><span>{{ formatCount(record.nonNullCount) }} / {{ formatCount(record.totalCount) }}</span></div>
              </template>
              <template v-else-if="column.key === 'state'">
                <a-tag :color="stateTag(record.state).color">{{ stateTag(record.state).label }}</a-tag>
              </template>
            </template>
          </a-table>
        </a-card>
      </template>

      <a-empty v-else-if="data && !loading" description="出票利润分析暂不可用">
        <a-alert type="error" show-icon :message="data.error ?? '请检查Hive连接和字段配置'" />
      </a-empty>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { getIssueProfitAnalysis, type FieldCompletenessItem, type IssueProfitAnalysisData } from '@/api/dashboard'
import BaseChart from '@/components/BaseChart.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import PageHeader from '@/components/PageHeader.vue'

type DimensionKey = 'platform' | 'airline' | 'supplier' | 'organization'

const formatDate = (value: Date) => {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const now = new Date()
const startDate = ref(formatDate(now))
const endDate = ref(formatDate(now))
const periodPreset = ref('today')
const data = ref<IssueProfitAnalysisData>()
const loading = ref(false)
const error = ref('')

const periodOptions = [
  { label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' },
  { label: '本月', value: 'month' }, { label: '本年', value: 'year' },
  { label: '自定义', value: 'custom' },
]

const dimensionPanels: Array<{ key: DimensionKey; title: string }> = [
  { key: 'platform', title: '平台利润贡献' }, { key: 'airline', title: '航司利润贡献' },
  { key: 'supplier', title: '供应商利润贡献' }, { key: 'organization', title: '组织利润贡献' },
]

const coverageColumns = [
  { title: '分析维度', key: 'field', width: 190 },
  { title: '业务用途', dataIndex: 'usage', key: 'usage', width: 210 },
  { title: '非空率', key: 'coverage', width: 360 },
  { title: '判断', key: 'state', width: 100 },
]

const money = (value: number) => `${new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)} 元`
const formatCount = (value: number) => new Intl.NumberFormat('zh-CN').format(value)
const percentage = (value: number) => `${value.toFixed(2)}%`

const summaryCards = computed(() => {
  const summary = data.value?.summary
  if (!summary) return []
  return [
    { label: '出票预估利润', value: money(summary.profit), description: 'issue_profit 汇总', negative: summary.profit < 0 },
    { label: '出票数', value: formatCount(summary.issueCount), description: '符合当前出票口径', negative: false },
    { label: '航段数', value: formatCount(summary.segmentCount), description: 'segment_num 汇总', negative: false },
    { label: '单票利润', value: money(summary.averageProfit), description: '利润 ÷ 出票数', negative: summary.averageProfit < 0 },
    { label: '亏损记录', value: formatCount(summary.lossCount), description: `占比 ${percentage(summary.lossRate)}`, negative: summary.lossCount > 0 },
  ]
})

const trendOption = computed<EChartsCoreOption>(() => {
  const items = data.value?.trend.items ?? []
  return {
    color: ['#3178f6', '#8fa4bf'], tooltip: { trigger: 'axis' },
    legend: { data: ['出票利润', '出票数'], top: 0, right: 0 },
    grid: { left: 66, right: 55, top: 46, bottom: 28 },
    xAxis: { type: 'category', data: items.map(item => item.period), axisLine: { lineStyle: { color: '#d7deea' } } },
    yAxis: [
      { type: 'value', name: '利润', splitLine: { lineStyle: { color: '#edf0f5' } }, axisLabel: { formatter: (value: number) => `${Math.round(value / 10000)}万` } },
      { type: 'value', name: '出票数', splitLine: { show: false }, axisLabel: { formatter: (value: number) => `${Math.round(value / 10000)}万` } },
    ],
    series: [
      { name: '出票利润', type: 'bar', barMaxWidth: 28, data: items.map(item => ({ value: item.profit, itemStyle: { color: item.profit < 0 ? '#d65a64' : '#2f9b78', borderRadius: item.profit < 0 ? [0, 0, 4, 4] : [4, 4, 0, 0] } })) },
      { name: '出票数', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6, data: items.map(item => item.count) },
    ],
  }
})

const dimensionOption = (key: DimensionKey): EChartsCoreOption => {
  const items = [...(data.value?.dimensions[key] ?? [])].reverse()
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (value: number) => money(value) },
    grid: { left: 110, right: 26, top: 10, bottom: 24 },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf0f5' } }, axisLabel: { formatter: (value: number) => `${Math.round(value / 10000)}万` } },
    yAxis: { type: 'category', data: items.map(item => item.name), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { width: 88, overflow: 'truncate' } },
    series: [{ type: 'bar', barMaxWidth: 16, data: items.map(item => ({ value: item.profit, itemStyle: { color: item.profit < 0 ? '#d65a64' : '#2f9b78', borderRadius: 3 } })) }],
  }
}

const coverageColor = computed(() => {
  const rate = data.value?.coverageSummary?.averageRate ?? 0
  return rate >= 95 ? '#2f9b78' : rate >= 80 ? '#e49a35' : '#d65a64'
})

const stateColor = (state: FieldCompletenessItem['state']) => state === 'ready' ? '#2f9b78' : state === 'partial' ? '#e49a35' : '#d65a64'
const stateTag = (state: FieldCompletenessItem['state']) => ({
  ready: { color: 'success', label: '齐全' }, partial: { color: 'warning', label: '需补' }, missing: { color: 'error', label: '缺失严重' },
}[state])

const applyPreset = (value: string | number) => {
  const preset = String(value)
  const today = new Date()
  let start = today
  let end = today
  if (preset === 'yesterday') { start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1); end = start }
  else if (preset === 'month') start = new Date(today.getFullYear(), today.getMonth(), 1)
  else if (preset === 'year') start = new Date(today.getFullYear(), 0, 1)
  else if (preset === 'custom') return
  startDate.value = formatDate(start)
  endDate.value = formatDate(end)
  loadData()
}

const markCustom = () => { periodPreset.value = 'custom' }

const loadData = async () => {
  loading.value = true
  error.value = ''
  try { data.value = await getIssueProfitAnalysis({ startDate: startDate.value, endDate: endDate.value }) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '出票利润分析加载失败' }
  finally { loading.value = false }
}

onMounted(loadData)
</script>
