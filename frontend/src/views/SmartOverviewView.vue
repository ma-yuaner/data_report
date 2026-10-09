<template>
  <div class="page-wrap smart-page">
    <PageHeader eyebrow="SMART TICKETING INSIGHTS" title="智能总览" description="查看智能出票总体表现、环节转化和利润及业务规模趋势">
      <a-button @click="showDefinition"><InfoCircleOutlined />指标口径</a-button>
    </PageHeader>
    <SmartAnalysisFilters :loading="loading" @query="load" @reset="load" />
    <DataStateBar :label="stateLabel" :message="stateMessage" :freshness="data?.updatedAt || '尚未读取'" metric-state="智能出票指标 v2.1" />
    <a-alert v-if="data?.error" class="smart-alert" type="error" show-icon :message="data.error" />

    <a-spin :spinning="loading" tip="正在读取Hive智能指标">
      <template v-if="data?.available && data.hasData">
        <div class="smart-kpi-grid">
          <button class="smart-kpi-card" @click="openDetail('use')"><span>智能使用出票量</span><strong>{{ count(activeMetrics.usedCount) }}<small> 张</small></strong><p>全部出票 {{ count(data.metrics.ticketCount) }} 张</p></button>
          <button class="smart-kpi-card" @click="openDetail('use')"><span>智能使用率</span><strong>{{ percent(activeMetrics.useRate) }}</strong><p>使用智能出票量 / 全部出票量</p></button>
          <button class="smart-kpi-card is-hero" @click="openDetail('use')"><span>智能利润</span><strong>{{ money(activeMetrics.profit) }}<small> 元</small></strong><p>使用智能票单的预估利润</p></button>
          <button class="smart-kpi-card" @click="openDetail('use')"><span>智能单张利润</span><strong>{{ money(activeMetrics.averageProfit) }}<small> 元</small></strong><p>智能利润 / 智能使用出票量</p></button>
        </div>

        <a-card :bordered="false" class="panel-card smart-section">
          <template #title>智能环节表现</template>
          <template #extra><span class="panel-caption">点击数量查看对应票单</span></template>
          <div class="smart-stage-grid">
            <button v-for="stage in stages" :key="stage.key" @click="openDetail(stage.key)">
              <i>{{ stage.step }}</i><span>{{ stage.label }}</span><strong>{{ count(stage.value) }}<small> 张</small></strong><p>{{ stage.note }} <b>查看 →</b></p>
            </button>
          </div>
        </a-card>

        <a-card :bordered="false" class="panel-card smart-section">
          <template #title>每日智能利润与出票量</template>
          <template #extra><span class="panel-caption">按出票日期汇总</span></template>
          <BaseChart :option="dailyOption" chart-label="每日总出票量、智能使用出票量和智能利润趋势" />
        </a-card>
        <a-card :bordered="false" class="panel-card smart-section">
          <template #title>每月智能利润与出票量</template>
          <template #extra><span class="panel-caption">当前查询期间按月汇总</span></template>
          <BaseChart :option="monthlyOption" chart-label="每月总出票量、智能使用出票量和智能利润趋势" />
        </a-card>
      </template>
      <a-empty v-else-if="!loading" class="smart-empty" :description="data?.error ? 'Hive数据暂时不可用' : '当前范围没有可发布的智能指标记录'" />
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Empty as AEmpty, message, Modal } from 'ant-design-vue'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import type { EChartsCoreOption } from 'echarts/core'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import BaseChart from '@/components/BaseChart.vue'
import SmartAnalysisFilters from '@/components/SmartAnalysisFilters.vue'
import { smartAnalysisApi, type SmartOverviewData, type SmartStage } from '@/api/smartAnalysis'
import { useSmartAnalysisStore } from '@/stores/smartAnalysis'

const store = useSmartAnalysisStore()
const router = useRouter()
const data = ref<SmartOverviewData>()
const loading = ref(false)
const integer = new Intl.NumberFormat('zh-CN')
const currency = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const activeKey = computed(() => store.smartType === 'all' ? 'smart' : store.smartType)
const activeMetrics = computed(() => data.value?.metrics[activeKey.value] ?? {
  participatedCount: null, succeededCount: null, usedCount: null, profit: null,
  participationRate: null, successRate: null, adoptionRate: null,
  participationUseRate: null, useRate: null, averageProfit: null,
})
const typeLabel = computed(() => ({ all: '智能整体', down: '智能降舱', void: '智能废票' }[store.smartType]))
const count = (value: number | null | undefined) => value == null ? '—' : integer.format(value)
const money = (value: string | null | undefined) => value == null ? '—' : currency.format(Number(value))
const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const stateLabel = computed(() => data.value?.available && data.value.hasData ? '真实Hive数据' : data.value?.available ? '当前范围暂无数据' : '数据不可用')
const stateMessage = computed(() => data.value?.available && data.value.hasData ? `${typeLabel.value} · ${data.value.source}` : data.value?.error || '查询无记录不认定为真实零，请核对范围和调度状态')
const stages = computed(() => [
  { step: '01', key: 'all' as SmartStage, label: '全部出票', value: data.value?.metrics.ticketCount, note: '当前范围全部出票' },
  { step: '02', key: 'participation' as SmartStage, label: '参与智能', value: activeMetrics.value.participatedCount, note: `参与率 ${percent(activeMetrics.value.participationRate)}` },
  { step: '03', key: 'success' as SmartStage, label: '智能成功', value: activeMetrics.value.succeededCount, note: `成功率 ${percent(activeMetrics.value.successRate)}` },
  { step: '04', key: 'use' as SmartStage, label: '使用智能', value: activeMetrics.value.usedCount, note: `成功使用率 ${percent(activeMetrics.value.adoptionRate)}` },
])

function chartOption(rows: SmartOverviewData['dailyTrend'] | SmartOverviewData['monthlyTrend']): EChartsCoreOption {
  return {
    color: ['#cbdcf7', '#3178f6', '#ed9645'],
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, data: ['全部出票量', '智能使用出票量', '智能利润'] },
    grid: { left: 50, right: 58, top: 28, bottom: 58 },
    xAxis: { type: 'category', data: rows.map(row => row.period), axisLabel: { color: '#75839a' } },
    yAxis: [
      { type: 'value', name: '出票量 / 张', axisLabel: { color: '#75839a' }, splitLine: { lineStyle: { color: '#edf0f5' } } },
      { type: 'value', name: '智能利润 / 元', axisLabel: { color: '#75839a' }, splitLine: { show: false } },
    ],
    series: [
      { name: '全部出票量', type: 'bar', barMaxWidth: 24, data: rows.map(row => row.metrics.ticketCount ?? 0) },
      { name: '智能使用出票量', type: 'bar', barMaxWidth: 13, barGap: '-72%', data: rows.map(row => row.metrics[activeKey.value].usedCount ?? 0) },
      { name: '智能利润', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 6, data: rows.map(row => Number(row.metrics[activeKey.value].profit ?? 0)) },
    ],
  }
}
const dailyOption = computed(() => chartOption(data.value?.dailyTrend ?? []))
const monthlyOption = computed(() => chartOption(data.value?.monthlyTrend ?? []))

async function load() {
  loading.value = true
  try { data.value = await smartAnalysisApi.overview({ ...store.applied }) }
  catch (error) { data.value = undefined; message.error(error instanceof Error ? error.message : '智能总览加载失败') }
  finally { loading.value = false }
}
function openDetail(stage: SmartStage) {
  void router.push({ path: '/smart-analysis/details', query: { stage, smartType: store.smartType } })
}
function showDefinition() {
  Modal.info({
    title: '智能分析指标口径 · v2.1', width: 620,
    content: () => '参与、成功和使用量汇总日指标表中的对应字段；明细页的使用判定以 smart_confirm 为准。参与率=参与/全部，成功率=成功/参与，成功使用率=使用/成功，使用率=使用/全部。智能利润为使用智能票单的 issue_profit 之和，不是增量收益。',
  })
}
onMounted(load)
</script>

<style scoped>
.smart-alert { margin: 14px 0; }
.smart-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 16px 0; }
.smart-kpi-card { padding: 20px; display: grid; gap: 8px; text-align: left; border: 1px solid #e5eaf2; border-radius: 12px; background: #fff; box-shadow: 0 5px 18px rgba(28,45,72,.035); cursor: pointer; }
.smart-kpi-card:hover { border-color: #a9c8f7; transform: translateY(-1px); }
.smart-kpi-card > span, .smart-kpi-card p { color: #7b8798; font-size: 11px; }
.smart-kpi-card strong { color: #283750; font-size: 27px; }
.smart-kpi-card strong small { font-size: 12px; }
.smart-kpi-card p { margin: 0; }
.smart-kpi-card.is-hero { border-color: #2f72da; background: linear-gradient(135deg,#2f72da,#4388ef); }
.smart-kpi-card.is-hero > * { color: #fff; }
.smart-section { margin-bottom: 14px; }
.smart-section :deep(.base-chart) { height: 330px; }
.smart-stage-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 12px; }
.smart-stage-grid button { position: relative; padding: 18px; display: grid; gap: 8px; text-align: left; border: 1px solid #e5eaf2; border-radius: 10px; background: #fbfcfe; cursor: pointer; }
.smart-stage-grid button:hover { border-color: #9fc1f5; background: #f5f9ff; }
.smart-stage-grid i { color: #9aabc2; font-size: 11px; font-style: normal; }
.smart-stage-grid span { color: #6e7d92; font-size: 12px; }
.smart-stage-grid strong { color: #2c3c55; font-size: 24px; }
.smart-stage-grid strong small { font-size: 11px; }
.smart-stage-grid p { margin: 0; color: #7d899a; font-size: 10px; }
.smart-stage-grid p b { float: right; color: #3178f6; }
.smart-empty { margin: 38px 0; padding: 70px; border: 1px solid #e6eaf0; border-radius: 12px; background: #fff; }
@media (max-width: 1000px) { .smart-kpi-grid, .smart-stage-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (max-width: 600px) { .smart-kpi-grid, .smart-stage-grid { grid-template-columns: 1fr; } }
</style>
