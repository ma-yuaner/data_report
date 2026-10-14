<template>
  <div class="page-wrap governance-page">
    <PageHeader eyebrow="RESOURCE GOVERNANCE" title="GDS/OTA资源治理" description="查询、验价、生单与实际有效PNR的分层分析">
      <a-tag color="blue">实际数据 · MySQL ADS</a-tag>
    </PageHeader>

    <a-alert class="source-banner" type="info" show-icon
      :message="`${data?.source || 'MySQL · sibebid'} · ${data?.table || 'bi_ota_gds_request_day'}`"
      :description="`OTA与GDS独立计算，不跨层相加。${data?.summary.sourceUpdatedAt ? ' 数据更新：' + data.summary.sourceUpdatedAt : ''}`" />

    <section class="scope-panel">
      <div class="section-heading">
        <div><h2>统计范围</h2><span>默认本月 · 先选分析层，再按业务维度下钻</span></div>
        <a-segmented v-model:value="draft.dataSource" :options="layerOptions" :disabled="loading" @change="changeLayer" />
      </div>
      <div class="period-line">
        <a-segmented v-model:value="preset" :options="periodOptions" :disabled="loading" @change="applyPreset" />
        <div class="date-fields">
          <a-date-picker v-model:value="draft.startDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" @change="preset = 'custom'" />
          <span>至</span>
          <a-date-picker v-model:value="draft.endDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" @change="preset = 'custom'" />
        </div>
      </div>
      <div class="filter-grid">
        <label><span>平台</span><a-select v-model:value="draft.platform" allow-clear show-search placeholder="全部平台" :options="selectOptions(data?.options.platform)" /></label>
        <label><span>站点</span><a-select v-model:value="draft.site" allow-clear show-search placeholder="全部站点" :options="selectOptions(data?.options.site)" /></label>
        <label v-if="draft.dataSource === 'gds'"><span>GDS</span><a-select v-model:value="draft.gds" allow-clear show-search placeholder="全部GDS" :options="selectOptions(data?.options.gds)" /></label>
        <label v-if="draft.dataSource === 'gds'"><span>PCC</span><a-select v-model:value="draft.pcc" allow-clear show-search placeholder="全部PCC" :options="selectOptions(data?.options.pcc)" /></label>
        <label><span>接口分组</span><a-select v-model:value="draft.apiGroup" allow-clear show-search placeholder="全部接口分组" :options="selectOptions(data?.options.apiGroup)" /></label>
      </div>
      <div class="scope-actions">
        <span>{{ pending ? '筛选条件已变更，点击查询后生效' : `当前为${layerLabel(applied.dataSource)}分析层` }}</span>
        <div><a-button :disabled="loading" @click="resetFilters">重置</a-button><a-button type="primary" :loading="loading" data-telemetry-code="governance-query" @click="applyFilters">查询</a-button></div>
      </div>
    </section>

    <div class="applied-scope">
      <strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong>
      <div><a-tag color="blue">{{ layerLabel(applied.dataSource) }}</a-tag><a-tag v-for="tag in appliedTags" :key="tag">{{ tag }}</a-tag></div>
    </div>
    <a-alert v-if="error || data?.error" class="state-alert" type="error" show-icon :message="error || data?.error" />
    <a-alert v-else-if="data?.available && !data.pnrColumnAvailable" class="state-alert" type="warning" show-icon
      message="有效PNR字段尚未接入" description="当前页面已展示查询、验价和生单接口指标；在bi_ota_gds_request_day增加pnr_count并完成同步后，查定比自动生效。" />
    <a-alert v-else-if="data?.available && data.pnrColumnAvailable && !data.pnrDataAvailable" class="state-alert" type="warning" show-icon
      message="pnr_count字段已存在，但所选范围尚未同步有效PNR" description="有效PNR显示为—，不会使用order_request_success替代，也不会把缺失数据当成0。" />

    <a-spin :spinning="loading" tip="正在查询GDS/OTA资源指标">
      <section class="governance-hero">
        <div class="hero-copy">
          <span>{{ layerLabel(applied.dataSource) }} LAYER · {{ data?.period.startDate || applied.startDate }} 至 {{ data?.period.endDate || applied.endDate }}</span>
          <h2>{{ heroTitle }}</h2>
          <p>{{ heroDescription }}</p>
        </div>
        <div class="hero-ratio">
          <small>当前查定比</small>
          <strong :class="ratioTone">{{ ratioText(data?.summary) }}</strong>
          <span>目标 ≤ {{ integer(data?.targetRatio) }} : 1</span>
        </div>
      </section>

      <div class="kpi-grid">
        <article><span>查询请求量</span><strong>{{ compact(data?.summary.searchRequests) }}</strong><small>不区分白名单的查询调用</small></article>
        <article><span>实际有效PNR</span><strong>{{ nullableCount(data?.summary.pnrCount) }}</strong><small>正式查定比分母</small></article>
        <article><span>超额查询量</span><strong class="orange">{{ nullableCount(data?.summary.excessQueryCount) }}</strong><small>查询量 − PNR × 目标值</small></article>
        <article><span>查询成功率</span><strong>{{ percent(data?.summary.searchSuccessRate) }}</strong><small>{{ integer(data?.summary.searchSuccess) }} 次成功</small></article>
        <article><span>验价成功率</span><strong>{{ percent(data?.summary.verifySuccessRate) }}</strong><small>{{ integer(data?.summary.verifyRequests) }} 次验价调用</small></article>
        <article><span>生单接口成功</span><strong>{{ integer(data?.summary.orderSuccess) }}</strong><small>接口成功，不等同有效PNR</small></article>
      </div>

      <div class="charts-grid">
        <a-card :bordered="false" class="analysis-panel">
          <template #title><div class="panel-title"><div><strong>请求量与查定比趋势</strong><small>按日汇总基础数量后重新计算</small></div><a-tag>{{ layerLabel(applied.dataSource) }}</a-tag></div></template>
          <BaseChart v-if="data?.available && data.trend.length" :option="trendOption" chart-label="GDS或OTA请求量与查定比日趋势" />
          <a-empty v-else description="所选范围暂无趋势数据" />
        </a-card>
        <a-card :bordered="false" class="analysis-panel">
          <template #title><div class="panel-title"><div><strong>接口链路转化</strong><small>接口成功与实际PNR分开展示</small></div></div></template>
          <div class="funnel-list">
            <div v-for="stage in funnel" :key="stage.label" class="funnel-row">
              <div><span>{{ stage.label }}</span><strong>{{ nullableCount(stage.value) }}</strong></div>
              <a-progress :percent="stage.percent" :show-info="false" :stroke-color="stage.color" />
              <small>{{ stage.note }}</small>
            </div>
          </div>
        </a-card>
      </div>

      <a-card :bordered="false" class="analysis-panel dimension-panel">
        <template #title>
          <div class="dimension-header">
            <div><strong>维度资源对比</strong><small>默认按查询请求量降序，展示全部结果并分页</small></div>
            <a-segmented v-model:value="draftGroup" :options="dimensionOptions" :disabled="loading" data-telemetry-code="governance-dimension" @change="changeDimension" />
          </div>
        </template>
        <a-table :columns="dimensionColumns" :data-source="data?.dimension.rows || []" row-key="value"
          :pagination="{ pageSize: 20, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'], showTotal: (total: number) => `共 ${total} 项` }"
          :scroll="{ x: 1120 }" :locale="{ emptyText: '所选维度暂无数据' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'"><div class="resource-name"><strong>{{ record.name }}</strong><small>{{ data?.dimension.label }}</small></div></template>
            <template v-else-if="column.key === 'ratio'"><strong :class="ratioClass(record)">{{ ratioText(record) }}</strong></template>
            <template v-else-if="column.key === 'search'">{{ integer(record.searchRequests) }}</template>
            <template v-else-if="column.key === 'pnr'">{{ nullableCount(record.pnrCount) }}</template>
            <template v-else-if="column.key === 'excess'">{{ nullableCount(record.excessQueryCount) }}</template>
            <template v-else-if="column.key === 'searchRate'">{{ percent(record.searchSuccessRate) }}</template>
            <template v-else-if="column.key === 'verifyRate'">{{ percent(record.verifySuccessRate) }}</template>
            <template v-else-if="column.key === 'orderRate'">{{ percent(record.orderSuccessRate) }}</template>
            <template v-else-if="column.key === 'action'"><a-button type="link" size="small" @click="openAnalysis(record)">分析此项</a-button></template>
          </template>
        </a-table>
      </a-card>
    </a-spin>

    <div class="notes"><InfoCircleOutlined /><div><strong>当前版本边界</strong><p v-for="note in data?.notes || []" :key="note">{{ note }}</p></div></div>

    <a-drawer v-model:open="drawerOpen" width="980" :title="drawerTitle">
      <a-alert v-if="drawerError" class="state-alert" type="error" show-icon :message="drawerError" />
      <a-spin :spinning="drawerLoading" tip="正在分析该资源">
        <div class="drawer-scope"><span>{{ analysisData?.period.startDate }} 至 {{ analysisData?.period.endDate }}</span><strong>{{ drawerScope }}</strong></div>
        <div class="drawer-kpis">
          <article><span>查询量</span><strong>{{ integer(analysisData?.summary.searchRequests) }}</strong></article>
          <article><span>有效PNR</span><strong>{{ nullableCount(analysisData?.summary.pnrCount) }}</strong></article>
          <article><span>查定比</span><strong :class="ratioClass(analysisData?.summary)">{{ ratioText(analysisData?.summary) }}</strong></article>
          <article><span>超额查询</span><strong>{{ nullableCount(analysisData?.summary.excessQueryCount) }}</strong></article>
        </div>
        <a-table class="daily-table" :columns="dailyColumns" :data-source="analysisData?.trend || []" row-key="date" :pagination="{ pageSize: 20 }" :scroll="{ x: 880 }" :locale="{ emptyText: '该资源暂无每日数据' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'search'">{{ integer(record.searchRequests) }}</template>
            <template v-else-if="column.key === 'pnr'">{{ nullableCount(record.pnrCount) }}</template>
            <template v-else-if="column.key === 'ratio'"><strong :class="ratioClass(record)">{{ ratioText(record) }}</strong></template>
            <template v-else-if="column.key === 'verify'">{{ integer(record.verifyRequests) }} / {{ percent(record.verifySuccessRate) }}</template>
            <template v-else-if="column.key === 'order'">{{ integer(record.orderSuccess) }} / {{ percent(record.orderSuccessRate) }}</template>
            <template v-else-if="column.key === 'excess'">{{ nullableCount(record.excessQueryCount) }}</template>
          </template>
        </a-table>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { InfoCircleOutlined } from '@ant-design/icons-vue'
import type { EChartsCoreOption } from 'echarts/core'
import BaseChart from '@/components/BaseChart.vue'
import PageHeader from '@/components/PageHeader.vue'
import {
  fetchResourceGovernance,
  type GovernanceData,
  type GovernanceDimension,
  type GovernanceLayer,
  type GovernanceMetric,
  type GovernanceScope,
} from '@/api/resourceGovernance'

const shanghaiDate = (value = new Date()) => value.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const today = shanghaiDate()
const monthStart = `${today.slice(0, 7)}-01`
const emptyScope = (): GovernanceScope => ({ startDate: monthStart, endDate: today, dataSource: 'gds', groupBy: 'gds', platform: '', site: '', gds: '', pcc: '', apiGroup: '' })
const draft = ref<GovernanceScope>(emptyScope())
const applied = ref<GovernanceScope>({ ...draft.value })
const preset = ref('month')
const draftGroup = ref<GovernanceDimension>('gds')
const data = ref<GovernanceData>()
const loading = ref(false)
const error = ref('')
let requestId = 0

const layerOptions = [{ label: 'GDS资源层', value: 'gds' }, { label: 'OTA渠道层', value: 'ota' }]
const periodOptions = [{ label: '今日', value: 'today' }, { label: '近7天', value: 'seven' }, { label: '本月', value: 'month' }, { label: '自定义', value: 'custom' }]
const gdsDimensions = [{ label: 'GDS', value: 'gds' }, { label: 'PCC', value: 'pcc' }, { label: '平台', value: 'platform' }, { label: '站点', value: 'site' }, { label: '接口分组', value: 'apiGroup' }]
const otaDimensions = [{ label: '平台', value: 'platform' }, { label: '站点', value: 'site' }, { label: '接口分组', value: 'apiGroup' }]
const dimensionOptions = computed(() => draft.value.dataSource === 'gds' ? gdsDimensions : otaDimensions)
const pending = computed(() => JSON.stringify(draft.value) !== JSON.stringify(applied.value))
const layerLabel = (layer: GovernanceLayer) => layer === 'gds' ? 'GDS资源层' : 'OTA渠道层'
const selectOptions = (values?: string[]) => (values || []).map(value => ({ label: value, value }))
const integer = (value?: number | null) => value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value)
const compact = (value?: number | null) => value == null ? '—' : new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
const nullableCount = (value?: number | null) => value == null ? '—' : integer(value)
const percent = (value?: string | null) => value == null ? '—' : `${Number(value).toFixed(2)}%`
const ratioText = (metric?: GovernanceMetric) => metric?.ratioInfinite ? '∞' : metric?.queryToPnrRatio == null ? '—' : `${integer(Math.round(Number(metric.queryToPnrRatio)))} : 1`
const ratioClass = (metric?: GovernanceMetric) => ({ danger: Boolean(metric?.ratioInfinite || (metric?.queryToPnrRatio != null && Number(metric.queryToPnrRatio) > (data.value?.targetRatio || 4000))), healthy: Boolean(metric?.queryToPnrRatio != null && Number(metric.queryToPnrRatio) <= (data.value?.targetRatio || 4000)) })
const ratioTone = computed(() => ratioClass(data.value?.summary))
const appliedTags = computed(() => [
  applied.value.platform && `平台：${applied.value.platform}`,
  applied.value.site && `站点：${applied.value.site}`,
  applied.value.gds && `GDS：${applied.value.gds}`,
  applied.value.pcc && `PCC：${applied.value.pcc}`,
  applied.value.apiGroup && `接口组：${applied.value.apiGroup}`,
].filter(Boolean) as string[])
const heroTitle = computed(() => {
  const summary = data.value?.summary
  if (!summary || summary.status === 'no_records') return '当前范围暂无资源调用数据'
  if (summary.status === 'pnr_field_missing' || summary.status === 'pnr_data_missing') return '查询链路已接入，有效PNR待补齐'
  if (summary.ratioInfinite) return '存在查询但没有实际有效PNR'
  if (Number(summary.queryToPnrRatio) > (data.value?.targetRatio || 4000)) return '当前查定比高于阶段治理目标'
  return '当前查定比处于阶段目标范围内'
})
const heroDescription = computed(() => {
  const summary = data.value?.summary
  if (!summary?.queryToPnrRatio) return '页面不会使用直连生单接口成功量替代有效PNR。'
  const gap = Math.round(Number(summary.queryToPnrRatio) - (data.value?.targetRatio || 4000))
  return gap > 0 ? `每个有效PNR仍需多消耗约 ${integer(gap)} 次查询，优先从下方高查询量资源开始下钻。` : `当前低于目标约 ${integer(Math.abs(gap))} 次查询，请继续观察有效PNR与业务量是否稳定。`
})

const funnel = computed(() => {
  const summary = data.value?.summary
  const base = Math.max(summary?.searchRequests || 0, 1)
  return [
    { label: '查询调用', value: summary?.searchRequests ?? 0, percent: 100, color: '#3278c8', note: `成功率 ${percent(summary?.searchSuccessRate)}` },
    { label: '验价调用', value: summary?.verifyRequests ?? 0, percent: Math.min(100, Math.round((summary?.verifyRequests || 0) / base * 100)), color: '#e19337', note: `成功率 ${percent(summary?.verifySuccessRate)}` },
    { label: '生单接口调用', value: summary?.orderRequests ?? 0, percent: Math.min(100, Math.round((summary?.orderRequests || 0) / base * 100)), color: '#8067c9', note: `接口成功 ${integer(summary?.orderSuccess)}` },
    { label: '实际有效PNR', value: summary?.pnrCount, percent: summary?.pnrCount == null ? 0 : Math.min(100, Math.max(1, Math.round(summary.pnrCount / base * 100))), color: '#2a9b78', note: '最终业务结果 · 正式分母' },
  ]
})

const trendOption = computed<EChartsCoreOption>(() => ({
  color: ['#4b85d1', '#d66a67', '#2a9b78'],
  tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => integer(Number(value)) },
  legend: { top: 2, data: ['查询请求量', '查定比', '目标值'] },
  grid: { left: 64, right: 72, top: 44, bottom: 34 },
  xAxis: { type: 'category', data: data.value?.trend.map(item => item.date.slice(5)) || [], axisLabel: { color: '#8090a5' } },
  yAxis: [
    { type: 'value', name: '请求量', axisLabel: { formatter: (value: number) => compact(value), color: '#8090a5' }, splitLine: { lineStyle: { color: '#edf1f6' } } },
    { type: 'value', name: '查定比', axisLabel: { formatter: (value: number) => integer(value), color: '#8090a5' }, splitLine: { show: false } },
  ],
  series: [
    { name: '查询请求量', type: 'bar', barMaxWidth: 20, data: data.value?.trend.map(item => item.searchRequests) || [], itemStyle: { borderRadius: [4, 4, 0, 0] } },
    { name: '查定比', type: 'line', yAxisIndex: 1, smooth: true, connectNulls: false, data: data.value?.trend.map(item => item.ratioInfinite ? null : item.queryToPnrRatio == null ? null : Number(item.queryToPnrRatio)) || [], symbolSize: 7 },
    { name: '目标值', type: 'line', yAxisIndex: 1, symbol: 'none', lineStyle: { type: 'dashed', width: 1.5 }, data: data.value?.trend.map(() => data.value?.targetRatio || 4000) || [] },
  ],
}))

const dimensionColumns = [
  { title: '资源', key: 'name', fixed: 'left' as const, width: 170 },
  { title: '查询请求量', key: 'search', width: 130, sorter: (a: GovernanceMetric, b: GovernanceMetric) => a.searchRequests - b.searchRequests },
  { title: '有效PNR', key: 'pnr', width: 110 },
  { title: '查定比', key: 'ratio', width: 125 },
  { title: '超额查询', key: 'excess', width: 130 },
  { title: '查询成功率', key: 'searchRate', width: 120 },
  { title: '验价成功率', key: 'verifyRate', width: 120 },
  { title: '生单成功率', key: 'orderRate', width: 120 },
  { title: '操作', key: 'action', fixed: 'right' as const, width: 100 },
]
const dailyColumns = [
  { title: '日期', dataIndex: 'date', width: 120, fixed: 'left' as const },
  { title: '查询请求量', key: 'search', width: 130 },
  { title: '有效PNR', key: 'pnr', width: 110 },
  { title: '查定比', key: 'ratio', width: 130 },
  { title: '验价量 / 成功率', key: 'verify', width: 160 },
  { title: '生单成功 / 成功率', key: 'order', width: 170 },
  { title: '超额查询', key: 'excess', width: 130 },
]

function applyPreset(value: string | number) {
  const selected = String(value)
  if (selected === 'custom') return
  const end = new Date(`${today}T12:00:00+08:00`)
  if (selected === 'today') draft.value.startDate = today
  if (selected === 'seven') { const start = new Date(end); start.setDate(start.getDate() - 6); draft.value.startDate = shanghaiDate(start) }
  if (selected === 'month') draft.value.startDate = monthStart
  draft.value.endDate = today
}
function changeLayer(value: string | number) {
  const layer = String(value) as GovernanceLayer
  draft.value.groupBy = layer === 'gds' ? 'gds' : 'platform'
  draftGroup.value = draft.value.groupBy
  draft.value.gds = ''
  draft.value.pcc = ''
}
function resetFilters() { const layer = draft.value.dataSource; draft.value = { ...emptyScope(), dataSource: layer, groupBy: layer === 'gds' ? 'gds' : 'platform' }; draftGroup.value = draft.value.groupBy; preset.value = 'month' }
function applyFilters() { draft.value.groupBy = draftGroup.value; void load({ ...draft.value }) }
function changeDimension(value: string | number) { draft.value.groupBy = String(value) as GovernanceDimension; void load({ ...draft.value }) }
async function load(scope: GovernanceScope) {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const result = await fetchResourceGovernance(scope)
    if (id !== requestId) return
    data.value = result
    applied.value = { ...scope, groupBy: result.dimension.key }
    draft.value = { ...applied.value }
    draftGroup.value = result.dimension.key
  } catch (failure) { if (id === requestId) error.value = failure instanceof Error ? failure.message : '资源治理查询失败' }
  finally { if (id === requestId) loading.value = false }
}

const drawerOpen = ref(false)
const drawerLoading = ref(false)
const drawerError = ref('')
const drawerTitle = ref('资源日汇总')
const drawerScope = ref('')
const analysisData = ref<GovernanceData>()
let drawerRequestId = 0
async function openAnalysis(record: { value: string; name: string }) {
  const id = ++drawerRequestId
  const dimension = applied.value.groupBy
  const scope = { ...applied.value, [dimension]: record.value }
  drawerTitle.value = `${record.name} · ${data.value?.dimension.label || '资源'}分析`
  drawerScope.value = `${layerLabel(scope.dataSource)} · ${data.value?.dimension.label}：${record.name}`
  drawerOpen.value = true
  drawerLoading.value = true
  drawerError.value = ''
  analysisData.value = undefined
  try { const result = await fetchResourceGovernance(scope); if (id === drawerRequestId) { analysisData.value = result; drawerError.value = result.error } }
  catch (failure) { if (id === drawerRequestId) drawerError.value = failure instanceof Error ? failure.message : '资源分析失败' }
  finally { if (id === drawerRequestId) drawerLoading.value = false }
}

onMounted(() => { void load({ ...draft.value }) })
</script>

<style scoped>
.governance-page { padding-bottom: 34px; }
.source-banner, .state-alert { margin-bottom: 15px; border-radius: 10px; }
.scope-panel { margin-bottom: 14px; padding: 18px 20px; border: 1px solid #e3e9f1; border-radius: 13px; background: #fff; box-shadow: 0 6px 20px rgb(38 61 91 / 4%); }
.section-heading, .section-heading > div, .scope-actions, .scope-actions > div, .period-line, .date-fields, .applied-scope, .dimension-header, .panel-title { display: flex; align-items: center; gap: 12px; }
.section-heading, .scope-actions, .applied-scope, .dimension-header, .panel-title { justify-content: space-between; }
.section-heading h2 { margin: 0; color: #26354b; font-size: 15px; }
.section-heading span, .scope-actions > span, .panel-title small, .dimension-header small { color: #8c98aa; font-size: 11px; }
.period-line { margin: 17px 0; flex-wrap: wrap; }
.date-fields { color: #7a8799; font-size: 12px; }
.date-fields :deep(.ant-picker) { width: 145px; }
.filter-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; }
.filter-grid label { display: grid; gap: 7px; color: #63728a; font-size: 12px; }
.filter-grid :deep(.ant-select) { width: 100%; }
.scope-actions { margin-top: 17px; padding-top: 14px; border-top: 1px solid #edf1f5; }
.applied-scope { margin: 13px 2px; flex-wrap: wrap; color: #4d5d75; font-size: 12px; }
.applied-scope > div { display: flex; gap: 6px; flex-wrap: wrap; }
.governance-hero { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 22px; align-items: center; margin-bottom: 14px; padding: 24px 26px; overflow: hidden; border-radius: 14px; color: #fff; background: linear-gradient(125deg, #17375f, #275f9f 68%, #2c7a8e); box-shadow: 0 12px 32px rgb(27 63 106 / 18%); }
.hero-copy span, .hero-ratio small, .hero-ratio span { color: #c8dbf2; font-size: 10px; letter-spacing: .08em; }
.hero-copy h2 { margin: 9px 0 7px; font-size: 21px; }
.hero-copy p { margin: 0; color: #d7e4f3; font-size: 12px; }
.hero-ratio { min-width: 200px; padding-left: 24px; border-left: 1px solid rgb(255 255 255 / 20%); text-align: right; }
.hero-ratio strong { display: block; margin: 5px 0; font-size: 30px; letter-spacing: -.04em; }
.hero-ratio strong.danger { color: #ffd0c7; }
.hero-ratio strong.healthy { color: #bff4db; }
.kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 11px; margin-bottom: 15px; }
.kpi-grid article { min-width: 0; padding: 16px; border: 1px solid #e3e9f1; border-radius: 11px; background: #fff; }
.kpi-grid span, .kpi-grid small { display: block; color: #8a96a8; font-size: 10px; }
.kpi-grid strong { display: block; margin: 12px 0 10px; color: #25364e; font-size: clamp(18px, 1.7vw, 25px); white-space: nowrap; }
.kpi-grid strong.orange { color: #c8782c; }
.charts-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(320px, .85fr); gap: 15px; margin-bottom: 15px; }
.analysis-panel { min-width: 0; border: 1px solid #e3e9f1; border-radius: 12px; }
.analysis-panel :deep(.ant-card-head) { min-height: 58px; border-color: #edf1f5; }
.analysis-panel :deep(.ant-card-body) { padding: 18px 20px; }
.panel-title > div, .dimension-header > div { display: grid; gap: 4px; }
.charts-grid :deep(.base-chart) { min-height: 300px; height: 300px; }
.funnel-list { display: grid; gap: 18px; padding: 7px 2px; }
.funnel-row > div { display: flex; justify-content: space-between; gap: 10px; color: #52617a; font-size: 12px; }
.funnel-row small { color: #929dae; font-size: 10px; }
.funnel-row :deep(.ant-progress) { margin: 5px 0 2px; }
.dimension-panel { margin-bottom: 15px; }
.dimension-header { width: 100%; }
.resource-name { display: grid; gap: 3px; }
.resource-name strong { color: #254a78; }
.resource-name small { color: #98a3b3; font-size: 10px; }
.danger { color: #c44752 !important; }
.healthy { color: #218365 !important; }
.notes { display: flex; gap: 10px; padding: 17px 2px; color: #8291a6; font-size: 11px; line-height: 1.7; }
.notes p { margin: 4px 0 0; }
.drawer-scope { display: flex; justify-content: space-between; gap: 14px; margin-bottom: 14px; padding: 13px 15px; border-radius: 9px; color: #728096; background: #f5f8fb; font-size: 11px; }
.drawer-scope strong { color: #34465f; }
.drawer-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 15px; }
.drawer-kpis article { padding: 15px; border: 1px solid #e3e9f1; border-radius: 10px; }
.drawer-kpis span { display: block; color: #8b97a8; font-size: 10px; }
.drawer-kpis strong { display: block; margin-top: 9px; color: #2c3d55; font-size: 20px; }
.daily-table { border: 1px solid #e5eaf1; border-radius: 10px; overflow: hidden; }
@media (max-width: 1250px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } .filter-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 900px) { .charts-grid { grid-template-columns: 1fr; } .filter-grid { grid-template-columns: repeat(2, 1fr); } .dimension-header { align-items: flex-start; flex-direction: column; } .governance-hero { grid-template-columns: 1fr; } .hero-ratio { padding: 15px 0 0; border-top: 1px solid rgb(255 255 255 / 20%); border-left: 0; text-align: left; } }
@media (max-width: 600px) { .scope-panel { padding: 15px 12px; } .section-heading, .scope-actions { align-items: flex-start; flex-direction: column; } .filter-grid, .kpi-grid, .drawer-kpis { grid-template-columns: 1fr 1fr; } .date-fields :deep(.ant-picker) { width: 126px; } }
</style>
