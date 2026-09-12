<template>
  <div class="page-wrap business-profit-page">
    <PageHeader :eyebrow="`${meta.en} PROFIT ANALYSIS`" :title="`${meta.name}利润分析`" :description="meta.description">
      <a-button :loading="loading" @click="loadData"><ReloadOutlined />刷新数据</a-button>
    </PageHeader>

    <DataStateBar
      :label="data?.mode === 'live' ? 'Hive实际数据' : '演示数据'"
      :message="data?.source ?? `正在连接${meta.name}利润数据集`"
      :freshness="data ? `查询时间 ${data.generatedAt.slice(11, 19)}` : '查询中'"
      metric-state="业务估算口径"
    />

    <div class="profit-filter">
      <div class="profit-filter-fields">
        <a-segmented v-model:value="periodPreset" :options="periodOptions" @change="applyPreset" />
        <span class="filter-label">{{ meta.name }}日期</span>
        <a-date-picker v-model:value="startDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
        <span class="date-separator">至</span>
        <a-date-picker v-model:value="endDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
        <a-button type="primary" :loading="loading" @click="loadData"><SearchOutlined />查询</a-button>
      </div>
      <span class="filter-tip">默认查看今日，可切换本月、本年或任意时间范围</span>
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

        <div class="dashboard-grid business-analysis-grid">
          <a-card class="panel-card" :bordered="false" :title="`${meta.name}利润趋势`">
            <template #extra><span class="panel-caption">{{ data.trend.granularity === 'month' ? '按月' : '按日' }}汇总</span></template>
            <BaseChart :option="trendOption" :chart-label="`${meta.name}利润与业务量趋势`" />
          </a-card>
          <a-card class="panel-card business-scope-card" :bordered="false" title="当前统计口径">
            <dl>
              <div><dt>数据来源</dt><dd>{{ data.source }}</dd></div>
              <div><dt>时间字段</dt><dd><code>{{ data.business.timeField }}</code></dd></div>
              <div><dt>利润字段</dt><dd><code>{{ data.business.profitField }}</code></dd></div>
              <div><dt>业务条件</dt><dd>{{ data.business.conditionLabel }}</dd></div>
              <div><dt>查询范围</dt><dd>{{ data.period.startDate }} 至 {{ data.period.endDate }}</dd></div>
            </dl>
            <p>当前展示业务结果和趋势；原因拆解待发现明确问题后再补充。</p>
          </a-card>
        </div>
      </template>

      <a-empty v-else-if="data && !loading" :description="`${meta.name}利润分析暂不可用`">
        <a-alert type="error" show-icon :message="data.error ?? '请检查Hive连接和字段配置'" />
      </a-empty>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { getBusinessProfitAnalysis, type BusinessProfitAnalysisData, type BusinessProfitType } from '@/api/dashboard'
import BaseChart from '@/components/BaseChart.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import PageHeader from '@/components/PageHeader.vue'

const props = defineProps<{ businessType: BusinessProfitType }>()
const definitions = {
  refund: { name: '退票', en: 'REFUND', description: '查看有效退票记录的利润结果和变化趋势，先回答规模与利润是否异常' },
  change: { name: '改签', en: 'CHANGE', description: '查看改签业务的利润结果和变化趋势，先建立稳定的业务事实入口' },
  ancillary: { name: '增值', en: 'ANCILLARY', description: '查看已购买增值业务的数量、航段和利润趋势' },
} as const
const meta = computed(() => definitions[props.businessType])

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
const data = ref<BusinessProfitAnalysisData>()
const loading = ref(false)
const error = ref('')
const periodOptions = [
  { label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' },
  { label: '本月', value: 'month' }, { label: '本年', value: 'year' },
  { label: '自定义', value: 'custom' },
]

const money = (value: number) => `${new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)} 元`
const count = (value: number) => new Intl.NumberFormat('zh-CN').format(value)

const summaryCards = computed(() => {
  const summary = data.value?.summary
  if (!summary) return []
  const cards = [
    { label: `${meta.value.name}利润`, value: money(summary.profit), description: `${data.value?.business.profitField} 汇总`, negative: summary.profit < 0 },
    { label: data.value?.business.countLabel ?? `${meta.value.name}数`, value: count(summary.count), description: '符合当前业务口径', negative: false },
  ]
  if (data.value?.business.segmentLabel && summary.segmentCount !== null) {
    cards.push({ label: data.value.business.segmentLabel, value: count(summary.segmentCount), description: 'flight_num 汇总', negative: false })
  }
  cards.push(
    { label: '单笔利润', value: money(summary.averageProfit), description: '利润 ÷ 业务记录数', negative: summary.averageProfit < 0 },
    { label: '负利润记录', value: count(summary.negativeCount), description: `占比 ${summary.negativeRate.toFixed(2)}%`, negative: summary.negativeCount > 0 },
  )
  return cards
})

const trendOption = computed<EChartsCoreOption>(() => {
  const items = data.value?.trend.items ?? []
  return {
    color: ['#2f9b78', '#7e95b3'], tooltip: { trigger: 'axis' },
    legend: { data: [`${meta.value.name}利润`, data.value?.business.countLabel ?? `${meta.value.name}数`], top: 0, right: 0 },
    grid: { left: 66, right: 55, top: 46, bottom: 28 },
    xAxis: { type: 'category', data: items.map(item => item.period), axisLine: { lineStyle: { color: '#d7deea' } } },
    yAxis: [
      { type: 'value', name: '利润', splitLine: { lineStyle: { color: '#edf0f5' } }, axisLabel: { formatter: (value: number) => `${Math.round(value / 10000)}万` } },
      { type: 'value', name: '业务量', splitLine: { show: false } },
    ],
    series: [
      { name: `${meta.value.name}利润`, type: 'bar', barMaxWidth: 28, data: items.map(item => ({ value: item.profit, itemStyle: { color: item.profit < 0 ? '#d65a64' : '#2f9b78', borderRadius: item.profit < 0 ? [0, 0, 4, 4] : [4, 4, 0, 0] } })) },
      { name: data.value?.business.countLabel ?? `${meta.value.name}数`, type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6, data: items.map(item => item.count) },
    ],
  }
})

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
  try { data.value = await getBusinessProfitAnalysis(props.businessType, { startDate: startDate.value, endDate: endDate.value }) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : `${meta.value.name}利润分析加载失败` }
  finally { loading.value = false }
}

watch(() => props.businessType, () => { data.value = undefined; loadData() })
onMounted(loadData)
</script>
