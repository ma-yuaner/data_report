<template>
  <div class="page-wrap smart-page">
    <PageHeader eyebrow="SMART TICKETING INSIGHTS" title="智能总览" description="查看智能出票总体表现、环节转化和利润及业务规模趋势">
      <a-button @click="showDefinition"><InfoCircleOutlined />指标口径</a-button>
    </PageHeader>
    <SmartAnalysisFilters page="overview" :loading="loading" @query="load" @reset="load" />
    <DataStateBar :label="stateLabel" :message="stateMessage" :freshness="data?.updatedAt || '尚未读取'" metric-state="智能出票指标 v2.1" />
    <a-alert v-if="data?.error" class="smart-alert" type="error" show-icon :message="data.error" />

    <a-spin :spinning="loading" tip="正在读取MySQL智能指标">
      <div class="smart-kpi-grid">
        <button class="smart-kpi-card" :disabled="!data?.hasData" @click="openDetail('use')"><span>智能使用出票量</span><strong>{{ count(activeMetrics.usedCount) }}<small> 张</small></strong><p>全部出票 {{ count(data?.metrics.ticketCount) }} 张</p></button>
        <button class="smart-kpi-card" :disabled="!data?.hasData" @click="openDetail('use')"><span>智能使用率</span><strong>{{ percent(activeMetrics.useRate) }}</strong><p>使用智能出票量 / 全部出票量</p></button>
        <button class="smart-kpi-card is-hero" :disabled="!data?.hasData" @click="openDetail('use')"><span>智能利润</span><strong>{{ money(activeMetrics.profit) }}<small> 元</small></strong><p>使用智能票单的预估利润</p></button>
        <button class="smart-kpi-card" :disabled="!data?.hasData" @click="openDetail('use')"><span>智能单张利润</span><strong>{{ money(activeMetrics.averageProfit) }}<small> 元</small></strong><p>智能利润 / 智能使用出票量</p></button>
      </div>

      <a-card :bordered="false" class="panel-card smart-section">
        <template #title>智能环节表现</template>
        <template #extra><span class="panel-caption">点击数量查看对应票单</span></template>
        <div class="smart-stage-grid">
          <button v-for="stage in stages" :key="stage.key" :disabled="!data?.hasData" @click="openDetail(stage.key)">
            <i>{{ stage.step }}</i><span>{{ stage.label }}</span><strong>{{ count(stage.value) }}<small> 张</small></strong><p>{{ stage.note }} <b>查看 →</b></p>
          </button>
        </div>
        <a-empty v-if="!loading && data?.available && !data.hasData" class="section-empty" description="当前筛选范围暂无总览指标" />
      </a-card>
    </a-spin>

    <div class="trend-toolbar">
      <div><strong>趋势统计日期</strong><span>{{ trendRangeDescription }}</span></div>
      <a-select v-model:value="store.trendDate" :options="trendDateOptions" @change="loadTrends" />
    </div>
    <a-alert v-if="trendData?.error" class="smart-alert" type="error" show-icon :message="trendData.error" />

    <a-card :bordered="false" class="panel-card smart-section trend-card">
      <template #title>近30天每日智能利润与出票量</template>
      <template #extra><div class="chart-extra"><span class="panel-caption">按{{ trendLabel }}汇总 · 截止 {{ trendCutoff }}</span><a-button size="small" :disabled="!trendData?.hasData" :loading="exporting === 'daily'" @click="exportTrend('daily')"><DownloadOutlined />导出</a-button></div></template>
      <a-spin :spinning="trendLoading" tip="正在读取日趋势">
        <BaseChart v-if="trendData?.dailyTrend.length" :option="dailyOption" chart-label="每日总出票量、智能使用出票量和智能利润趋势" />
        <a-empty v-else-if="!trendLoading" class="chart-empty" description="当前筛选范围暂无每日趋势数据" />
        <div v-else class="chart-placeholder" />
        <div v-if="dailyReadout" class="chart-readout">{{ dailyReadout }}</div>
        <p class="chart-note">{{ chartNote('day') }}</p>
      </a-spin>
    </a-card>
    <a-card :bordered="false" class="panel-card smart-section trend-card">
      <template #title>近12个月智能利润与出票量</template>
      <template #extra><div class="chart-extra"><span class="panel-caption">按{{ trendLabel }}汇总</span><a-button size="small" :disabled="!trendData?.hasData" :loading="exporting === 'monthly'" @click="exportTrend('monthly')"><DownloadOutlined />导出</a-button></div></template>
      <a-spin :spinning="trendLoading" tip="正在读取月趋势">
        <BaseChart v-if="trendData?.monthlyTrend.length" :option="monthlyOption" chart-label="每月总出票量、智能使用出票量和智能利润趋势" />
        <a-empty v-else-if="!trendLoading" class="chart-empty" description="当前筛选范围暂无每月趋势数据" />
        <div v-else class="chart-placeholder" />
        <div v-if="monthlyReadout" class="chart-readout">{{ monthlyReadout }}</div>
        <p class="chart-note">{{ chartNote('month') }}</p>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Empty as AEmpty, message, Modal } from 'ant-design-vue'
import { DownloadOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import type { EChartsCoreOption } from 'echarts/core'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import BaseChart from '@/components/BaseChart.vue'
import SmartAnalysisFilters from '@/components/SmartAnalysisFilters.vue'
import { smartAnalysisApi, type SmartOverviewData, type SmartStage } from '@/api/smartAnalysis'
import { useSmartAnalysisStore } from '@/stores/smartAnalysis'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import { guardSmartExport } from '@/utils/smartExportGuard'

const store = useSmartAnalysisStore()
const exportTasks = useComprehensiveExportStore()
const pageState = store.pages.overview
const router = useRouter()
const data = ref<SmartOverviewData>()
const trendData = ref<SmartOverviewData>()
const loading = ref(false)
const trendLoading = ref(false)
const exporting = ref<'' | 'daily' | 'monthly'>('')
const trendDateOptions = [
  { label: '出票日期', value: 'issue' }, { label: '首段起飞日期', value: 'departure' }, { label: '进单日期', value: 'order' },
]
const integer = new Intl.NumberFormat('zh-CN')
const currency = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const activeKey = computed(() => pageState.smartType === 'all' ? 'smart' : pageState.smartType)
const emptySmartMetrics = { participatedCount: null, succeededCount: null, usedCount: null, profit: null, participationRate: null, successRate: null, adoptionRate: null, participationUseRate: null, useRate: null, averageProfit: null }
const activeMetrics = computed(() => data.value?.metrics[activeKey.value] ?? emptySmartMetrics)
const typeLabel = computed(() => ({ all: '智能整体', down: '智能降舱', void: '智能废票' }[pageState.smartType]))
const trendLabel = computed(() => trendData.value?.trend.dateLabel || trendDateOptions.find(item => item.value === store.trendDate)?.label || '出票日期')
const trendCutoff = computed(() => trendData.value?.trend.cutoffDate || pageState.applied.endDate)
const trendRangeDescription = computed(() => {
  const trend = trendData.value?.trend
  if (!trend) return '日趋势显示截止日往前30天，月趋势显示截止月在内的最近12个月'
  return `日趋势 ${trend.dailyStartDate} 至 ${trend.cutoffDate}；月趋势 ${trend.monthlyStartDate.slice(0, 7)} 至 ${trend.cutoffDate.slice(0, 7)}；截止日来自${trend.cutoffSource}。`
})
const count = (value: number | null | undefined) => value == null ? '—' : integer.format(value)
const money = (value: string | null | undefined) => value == null ? '—' : currency.format(Number(value))
const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const stateLabel = computed(() => loading.value ? '指标读取中' : data.value?.available && data.value.hasData ? '真实MySQL数据' : data.value?.available ? '当前范围暂无数据' : '数据不可用')
const stateMessage = computed(() => loading.value ? '总览指标与趋势分开加载，趋势查询不会阻塞指标展示' : data.value?.available && data.value.hasData ? `${typeLabel.value} · ${data.value.source}` : data.value?.error || '查询无记录不认定为真实零，请核对范围和调度状态')
const stages = computed(() => [
  { step: '01', key: 'all' as SmartStage, label: '全部出票', value: data.value?.metrics.ticketCount, note: '当前范围全部出票' },
  { step: '02', key: 'participation' as SmartStage, label: '参与智能', value: activeMetrics.value.participatedCount, note: `参与率 ${percent(activeMetrics.value.participationRate)}` },
  { step: '03', key: 'success' as SmartStage, label: '智能成功', value: activeMetrics.value.succeededCount, note: `成功率 ${percent(activeMetrics.value.successRate)}` },
  { step: '04', key: 'use' as SmartStage, label: '使用智能', value: activeMetrics.value.usedCount, note: `成功使用率 ${percent(activeMetrics.value.adoptionRate)}` },
])

function trendReadout(rows: SmartOverviewData['dailyTrend'] | SmartOverviewData['monthlyTrend']) {
  const row = rows.at(-1)
  if (!row) return ''
  const metrics = row.metrics[activeKey.value]
  return `${row.period} ｜ 总出票数 ${count(row.metrics.ticketCount)} 张 ｜ ${typeLabel.value}使用出票数 ${count(metrics.usedCount)} 张 ｜ ${typeLabel.value}利润 ¥${money(metrics.profit)} ｜ 使用率 ${percent(metrics.useRate)}`
}
const dailyReadout = computed(() => trendReadout(trendData.value?.dailyTrend ?? []))
const monthlyReadout = computed(() => trendReadout(trendData.value?.monthlyTrend ?? []))
function chartNote(granularity: 'day' | 'month') {
  const unit = granularity === 'day' ? '当日' : '当月'
  const freshness = trendData.value?.updatedAt ? `，${unit}数据按MySQL调度更新，当前数据时间 ${trendData.value.updatedAt}` : ''
  return `浅色宽柱为总出票数，深色窄柱为其中使用${typeLabel.value}的票数，共用数量轴、不相加${freshness}。`
}

function chartOption(rows: SmartOverviewData['dailyTrend'] | SmartOverviewData['monthlyTrend']): EChartsCoreOption {
  return {
    color: ['#cbdcf7', '#3178f6', '#ed9645'], tooltip: { trigger: 'axis' }, legend: { bottom: 0, data: ['全部出票量', '智能使用出票量', '智能利润'] }, grid: { left: 50, right: 58, top: 28, bottom: 58 },
    xAxis: { type: 'category', data: rows.map(row => row.period), axisLabel: { color: '#75839a' } },
    yAxis: [{ type: 'value', name: '出票量 / 张', axisLabel: { color: '#75839a' }, splitLine: { lineStyle: { color: '#edf0f5' } } }, { type: 'value', name: '智能利润 / 元', axisLabel: { color: '#75839a' }, splitLine: { show: false } }],
    series: [
      { name: '全部出票量', type: 'bar', barMaxWidth: 24, data: rows.map(row => row.metrics.ticketCount ?? 0) },
      { name: '智能使用出票量', type: 'bar', barMaxWidth: 13, barGap: '-72%', data: rows.map(row => row.metrics[activeKey.value].usedCount ?? 0) },
      { name: '智能利润', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6, data: rows.map(row => Number(row.metrics[activeKey.value].profit ?? 0)) },
    ],
  }
}
const dailyOption = computed(() => chartOption(trendData.value?.dailyTrend ?? []))
const monthlyOption = computed(() => chartOption(trendData.value?.monthlyTrend ?? []))

async function loadOverview() { loading.value = true; try { data.value = await smartAnalysisApi.overview({ ...pageState.applied }, store.trendDate) } catch (error) { data.value = undefined; message.error(error instanceof Error ? error.message : '智能总览加载失败') } finally { loading.value = false } }
async function loadTrends() { trendLoading.value = true; try { trendData.value = await smartAnalysisApi.trends({ ...pageState.applied }, store.trendDate) } catch (error) { trendData.value = undefined; message.error(error instanceof Error ? error.message : '智能趋势加载失败') } finally { trendLoading.value = false } }
function load() { void loadOverview(); void loadTrends() }
function openDetail(stage: SmartStage) { if (!data.value?.hasData) return; const label = stages.value.find(item => item.key === stage)?.label || '全部出票'; store.beginDrill({ sourcePath: '/smart-analysis/overview', sourceTitle: '智能总览', sourcePage: 'overview', stage, tags: [{ label: '票单范围', value: label }] }); void router.push({ path: '/smart-analysis/details', query: { stage, smartType: pageState.smartType, drill: '1' } }) }
async function runTrendExport(kind: 'daily' | 'monthly') { exporting.value = kind; try { const task = await exportTasks.createBackground(kind === 'daily' ? 'smart_trend_daily' : 'smart_trend_monthly', { ...pageState.applied, smartType: pageState.smartType, trendDate: store.trendDate }); message.success(task.reused ? '相同条件的任务正在进行，已打开导出任务' : '已加入导出任务，可在页头查看进度') } catch (error) { message.error(error instanceof Error ? error.message : '趋势导出失败') } finally { exporting.value = '' } }
function exportTrend(kind: 'daily' | 'monthly') {
  const total = kind === 'daily' ? trendData.value?.dailyTrend.length : trendData.value?.monthlyTrend.length
  guardSmartExport(total ?? 0, () => runTrendExport(kind))
}
function showDefinition() { Modal.info({ title: '智能分析指标口径 · v2.1', width: 620, content: () => '参与、成功和使用量汇总日指标表中的对应字段；明细页的使用判定以 smart_confirm 为准。参与率=参与/全部，成功率=成功/参与，成功使用率=使用/成功，使用率=使用/全部。智能利润为使用智能票单的 issue_profit 之和，不是增量收益。' }) }
onMounted(load)
</script>

<style scoped>
.smart-alert { margin: 14px 0; }
.smart-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 16px 0; }
.smart-kpi-card { min-height: 132px; padding: 20px; display: grid; gap: 8px; text-align: left; border: 1px solid #e5eaf2; border-radius: 12px; background: #fff; box-shadow: 0 5px 18px rgba(28,45,72,.035); cursor: pointer; }
.smart-kpi-card:hover:not(:disabled) { border-color: #a9c8f7; transform: translateY(-1px); }
.smart-kpi-card:disabled { cursor: default; }
.smart-kpi-card > span, .smart-kpi-card p { color: #7b8798; font-size: 11px; }
.smart-kpi-card strong { color: #283750; font-size: 27px; }
.smart-kpi-card strong small { font-size: 12px; }
.smart-kpi-card p { margin: 0; }
.smart-kpi-card.is-hero { border-color: #2f72da; background: linear-gradient(135deg,#2f72da,#4388ef); }
.smart-kpi-card.is-hero > * { color: #fff; }
.smart-section { margin-bottom: 14px; }
.trend-toolbar { margin: 14px 0; padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border: 1px solid #dfe8f5; border-radius: 10px; background: #f7faff; }
.trend-toolbar > div { display: grid; gap: 3px; }
.trend-toolbar strong { color: #35465f; font-size: 13px; }
.trend-toolbar span { color: #7d8a9d; font-size: 11px; }
.trend-toolbar :deep(.ant-select) { width: 180px; }
.chart-extra { display: flex; align-items: center; gap: 12px; }
.trend-card :deep(.base-chart), .chart-placeholder, .chart-empty { height: 330px; }
.chart-readout { margin: 10px 0 0; padding: 10px 14px; color: #506787; font-size: 13px; font-variant-numeric: tabular-nums; border-radius: 6px; background: #f5f8fd; }
.chart-note { margin: 10px 0 0; color: #78879b; font-size: 11px; line-height: 1.7; }
.chart-empty, .section-empty { display: flex; align-items: center; justify-content: center; }
.section-empty { margin-top: 12px; padding-top: 12px; border-top: 1px solid #edf0f4; }
.smart-stage-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 12px; }
.smart-stage-grid button { position: relative; min-height: 139px; padding: 18px; display: grid; gap: 8px; text-align: left; border: 1px solid #e5eaf2; border-radius: 10px; background: #fbfcfe; cursor: pointer; }
.smart-stage-grid button:hover:not(:disabled) { border-color: #9fc1f5; background: #f5f9ff; }
.smart-stage-grid button:disabled { cursor: default; }
.smart-stage-grid i { color: #9aabc2; font-size: 11px; font-style: normal; }
.smart-stage-grid span { color: #6e7d92; font-size: 12px; }
.smart-stage-grid strong { color: #2c3c55; font-size: 24px; }
.smart-stage-grid strong small { font-size: 11px; }
.smart-stage-grid p { margin: 0; color: #7d899a; font-size: 10px; }
.smart-stage-grid p b { float: right; color: #3178f6; }
@media (max-width: 1000px) { .smart-kpi-grid, .smart-stage-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (max-width: 600px) { .smart-kpi-grid, .smart-stage-grid { grid-template-columns: 1fr; } .trend-toolbar { align-items: stretch; flex-direction: column; } .trend-toolbar :deep(.ant-select) { width: 100%; } .chart-extra { align-items: flex-end; flex-direction: column; } }
</style>
