<template>
  <div class="page-wrap smart-page">
    <PageHeader eyebrow="SMART DIMENSION ANALYSIS" title="维度分析" description="按一个或多个业务维度组合分析出票、智能参与、成功、使用和利润表现" />
    <SmartAnalysisFilters page="dimension" :loading="loading" @query="queryFromStart" @reset="resetPage" />
    <DataStateBar :label="stateLabel" :message="stateMessage" :freshness="data?.updatedAt || '尚未读取'" metric-state="分组后重新计算比率" />
    <a-alert v-if="data?.error" class="smart-alert" type="error" show-icon :message="data.error" />

    <a-card :bordered="false" class="panel-card smart-dimension-panel">
      <div class="dimension-toolbar">
        <label><span>分析维度</span><a-select v-model:value="groups" mode="multiple" :options="dimensionOptions" :max-tag-count="4" placeholder="至少选择一个维度" @change="queryFromStart" /></label>
        <label><span>排序指标</span><a-select v-model:value="sortBy" :options="sortOptions" @change="queryFromStart" /></label>
        <label><span>排序方向</span><a-select v-model:value="direction" :options="directionOptions" @change="queryFromStart" /></label>
        <a-button @click="openMetricModal"><SettingOutlined />显示指标</a-button>
        <a-button :loading="exporting" @click="exportRows"><DownloadOutlined />导出</a-button>
        <a-button type="primary" :loading="loading" @click="queryFromStart"><SearchOutlined />刷新分析</a-button>
      </div>

      <p class="dimension-hint">当前口径：{{ typeLabel }}；点击表格中的蓝色指标值，会带上当前日期、筛选和维度值进入出票明细。</p>

      <a-table :columns="columns" :data-source="tableRows" :loading="loading" row-key="key" :pagination="false" :scroll="{ x: tableWidth }" :row-class-name="(record: TableRow) => record.isTotal ? 'dimension-total-row' : ''" :locale="{ emptyText: '当前范围暂无维度组合记录' }">
        <template #bodyCell="{ column, record }">
          <template v-if="String(column.key).startsWith('dimension-')"><span class="dimension-value">{{ record.path[column.dimensionIndex]?.name || (record.isTotal && column.dimensionIndex === 0 ? '合计' : '') }}</span></template>
          <template v-else-if="column.metric">
            <button v-if="!record.isTotal && column.metric.stage" class="metric-link" @click="openMetricDetails(record.path, column.metric)">{{ formatMetric(metricValue(record.metrics, column.metric), column.metric.kind) }}</button>
            <span v-else :class="{ negative: column.metric.kind === 'money' && Number(metricValue(record.metrics, column.metric)) < 0 }">{{ formatMetric(metricValue(record.metrics, column.metric), column.metric.kind) }}</span>
          </template>
          <template v-else-if="column.key === 'action'"><a-button v-if="!record.isTotal" type="link" size="small" @click="openDetails(record.path)">查看票单 →</a-button></template>
        </template>
      </a-table>
      <div class="dimension-pagination">
        <span>共 {{ count(data?.total) }} 种组合；导出不受当前分页影响</span>
        <a-pagination v-model:current="page" v-model:pageSize="pageSize" :total="data?.total || 0" :page-size-options="['10','20','50','100']" show-size-changer @change="load" />
      </div>
    </a-card>

    <a-modal v-model:open="metricModalOpen" title="显示指标" width="780px" ok-text="应用指标" cancel-text="取消" @ok="applyMetrics">
      <div class="metric-modal-actions"><span>已选 {{ draftMetrics.length }} 项，导出与表格使用相同指标</span><div><a-button size="small" @click="selectDefaultMetrics">恢复默认</a-button><a-button size="small" @click="draftMetrics = metricOptions.map(item => item.key)">全选</a-button></div></div>
      <div class="metric-groups">
        <section v-for="group in metricGroups" :key="group.name"><h3>{{ group.name }}</h3><div><label v-for="metric in group.items" :key="metric.key"><input v-model="draftMetrics" type="checkbox" :value="metric.key">{{ metric.title }}</label></div></section>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message, Pagination as APagination } from 'ant-design-vue'
import { DownloadOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import SmartAnalysisFilters from '@/components/SmartAnalysisFilters.vue'
import { dimensionOptions, smartAnalysisApi, type SmartDimensionData, type SmartDimensionPath, type SmartFilters, type SmartMetrics, type SmartStage, type SmartType } from '@/api/smartAnalysis'
import { useSmartAnalysisStore } from '@/stores/smartAnalysis'

type MetricKind = 'count' | 'money' | 'rate'
interface MetricOption { key: string; title: string; group: string; path: string[]; kind: MetricKind; width: number; stage?: SmartStage; smartType?: SmartType }
type TableRow = SmartDimensionData['rows'][number] & { isTotal?: boolean }

const baseMetrics: MetricOption[] = [
  { key: 'ticketCount', title: '出票量', group: '基础指标', path: ['ticketCount'], kind: 'count', width: 100, stage: 'all' },
  { key: 'totalProfit', title: '全部预估利润', group: '基础指标', path: ['totalProfit'], kind: 'money', width: 135 },
  { key: 'segmentCount', title: '总航段数', group: '基础指标', path: ['segmentCount'], kind: 'count', width: 105 },
  { key: 'refundCount', title: '退票中/已退票量', group: '基础指标', path: ['refundCount'], kind: 'count', width: 135, stage: 'refund' },
  { key: 'perSegmentProfit', title: '单航段利润', group: '基础指标', path: ['perSegmentProfit'], kind: 'money', width: 125 },
]
function smartMetrics(prefix: 'smart' | 'down' | 'void', label: string, smartType: SmartType): MetricOption[] {
  return [
    [`${prefix}Participated`, '参与出票量', 'participatedCount', 'count', 'participation'],
    [`${prefix}Succeeded`, '成功出票量', 'succeededCount', 'count', 'success'],
    [`${prefix}Used`, '使用出票量', 'usedCount', 'count', 'use'],
    [`${prefix}ParticipationRate`, '参与率', 'participationRate', 'rate', ''],
    [`${prefix}SuccessRate`, '成功率', 'successRate', 'rate', ''],
    [`${prefix}AdoptionRate`, '成功使用率', 'adoptionRate', 'rate', ''],
    [`${prefix}ParticipationUseRate`, '参与使用率', 'participationUseRate', 'rate', ''],
    [`${prefix}UseRate`, '使用率', 'useRate', 'rate', ''],
    [`${prefix}Profit`, '智能利润', 'profit', 'money', 'use'],
    [`${prefix}AverageProfit`, '智能单张利润', 'averageProfit', 'money', ''],
  ].map(([key, title, path, kind, stage]) => ({ key, title: `${label}${title}`, group: label, path: [prefix, path], kind: kind as MetricKind, width: kind === 'money' ? 145 : 120, stage: stage as SmartStage || undefined, smartType }))
}
const metricOptions: MetricOption[] = [...baseMetrics, ...smartMetrics('smart', '智能整体', 'all'), ...smartMetrics('down', '智能降舱', 'down'), ...smartMetrics('void', '智能废票', 'void')]
const DEFAULT_METRICS = ['ticketCount', 'totalProfit', 'smartParticipated', 'smartSucceeded', 'smartUsed', 'smartUseRate', 'smartProfit', 'smartAverageProfit']
const store = useSmartAnalysisStore()
const pageState = store.pages.dimension
const router = useRouter()
const data = ref<SmartDimensionData>()
const loading = ref(false)
const exporting = ref(false)
const groups = ref<string[]>([...store.dimensionState.groups])
const selectedMetrics = ref<string[]>([...store.dimensionState.metrics])
const draftMetrics = ref<string[]>([...selectedMetrics.value])
const sortBy = ref(store.dimensionState.sortBy)
const direction = ref<'asc' | 'desc'>(store.dimensionState.direction)
const page = ref(store.dimensionState.page)
const pageSize = ref(store.dimensionState.pageSize)
const metricModalOpen = ref(false)
const integer = new Intl.NumberFormat('zh-CN')
const currency = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const sortOptions = [
  { label: '智能利润', value: 'smartProfit' }, { label: '智能使用出票量', value: 'usedCount' },
  { label: '全部出票量', value: 'ticketCount' }, { label: '全部预估利润', value: 'totalProfit' }, { label: '总航段数', value: 'segments' },
]
const directionOptions = [{ label: '降序', value: 'desc' }, { label: '升序', value: 'asc' }]
const typeLabel = computed(() => ({ all: '智能整体', down: '智能降舱', void: '智能废票' }[pageState.smartType]))
const count = (value: number | null | undefined) => value == null ? '—' : integer.format(value)
const stateLabel = computed(() => data.value?.available && data.value.hasData ? '真实MySQL数据' : data.value?.available ? '当前范围暂无数据' : '数据不可用')
const stateMessage = computed(() => data.value?.available && data.value.hasData ? `${data.value.source} · ${groups.value.map(key => dimensionOptions.find(item => item.value === key)?.label).join(' × ')}` : data.value?.error || '查询无记录不认定为真实零')
const activeMetricOptions = computed(() => selectedMetrics.value.map(key => metricOptions.find(item => item.key === key)).filter((item): item is MetricOption => Boolean(item)))
const metricGroups = computed(() => ['基础指标', '智能整体', '智能降舱', '智能废票'].map(name => ({ name, items: metricOptions.filter(item => item.group === name) })))
const tableRows = computed<TableRow[]>(() => {
  if (!data.value?.available || !data.value.hasData) return []
  return [{ key: '__total__', path: groups.value.map((key, index) => ({ key: key as keyof SmartFilters, label: '', value: '', name: index === 0 ? '合计' : '' })), metrics: data.value.totals, isTotal: true }, ...data.value.rows]
})
const columns = computed(() => [
  ...(data.value?.dimensions || groups.value.map(key => ({ key, label: dimensionOptions.find(item => item.value === key)?.label || key }))).map((item, index) => ({ title: item.label, key: `dimension-${item.key}`, dimensionIndex: index, width: 125, fixed: index === 0 ? 'left' as const : undefined })),
  ...activeMetricOptions.value.map(metric => ({ title: metric.title, key: metric.key, metric, width: metric.width })),
  { title: '明细', key: 'action', width: 110, fixed: 'right' as const },
])
const tableWidth = computed(() => columns.value.reduce((sum, column) => sum + Number(column.width || 100), 0))

function metricValue(metrics: SmartMetrics, metric: MetricOption) { return metric.path.reduce<unknown>((value, key) => typeof value === 'object' && value !== null ? (value as Record<string, unknown>)[key] : null, metrics) }
function formatMetric(value: unknown, kind: MetricKind) { if (value == null || value === '') return '—'; if (kind === 'rate') return `${(Number(value) * 100).toFixed(1)}%`; if (kind === 'money') return currency.format(Number(value)); return integer.format(Number(value)) }
function syncState() { store.dimensionState.groups = [...groups.value]; store.dimensionState.metrics = [...selectedMetrics.value]; store.dimensionState.sortBy = sortBy.value; store.dimensionState.direction = direction.value; store.dimensionState.page = page.value; store.dimensionState.pageSize = pageSize.value }
async function load() {
  if (!groups.value.length) { message.warning('请至少选择一个分析维度'); return }
  syncState(); loading.value = true
  try { data.value = await smartAnalysisApi.dimensions({ ...pageState.applied }, { groupBy: groups.value, smartType: pageState.smartType, sortBy: sortBy.value, direction: direction.value, page: page.value, pageSize: pageSize.value }) }
  catch (error) { data.value = undefined; message.error(error instanceof Error ? error.message : '维度分析加载失败') }
  finally { loading.value = false }
}
function queryFromStart() { page.value = 1; void load() }
function resetPage() { groups.value = ['airline', 'platform']; selectedMetrics.value = [...DEFAULT_METRICS]; sortBy.value = 'smartProfit'; direction.value = 'desc'; queryFromStart() }
function openMetricModal() { draftMetrics.value = [...selectedMetrics.value]; metricModalOpen.value = true }
function selectDefaultMetrics() { draftMetrics.value = [...DEFAULT_METRICS] }
function applyMetrics() { if (!draftMetrics.value.length) { message.warning('请至少选择一个指标'); return }; selectedMetrics.value = metricOptions.filter(item => draftMetrics.value.includes(item.key)).map(item => item.key); metricModalOpen.value = false; syncState() }
function beginDetails(path: SmartDimensionPath[], stage: SmartStage, metricLabel: string, smartType = pageState.smartType) {
  store.beginDrill({ sourcePath: '/smart-analysis/dimensions', sourceTitle: '维度分析', sourcePage: 'dimension', stage, smartType, path, tags: [...path.map(item => ({ label: item.label, value: item.name })), { label: '指标范围', value: metricLabel }] })
  void router.push({ path: '/smart-analysis/details', query: { stage, smartType, drill: '1' } })
}
function openDetails(path: SmartDimensionPath[]) { beginDetails(path, 'all', '全部出票') }
function openMetricDetails(path: SmartDimensionPath[], metric: MetricOption) { if (metric.stage) beginDetails(path, metric.stage, metric.title, metric.smartType || pageState.smartType) }
async function exportRows() { exporting.value = true; try { await smartAnalysisApi.exportDimensions({ ...pageState.applied }, { groupBy: groups.value, metrics: selectedMetrics.value, smartType: pageState.smartType, sortBy: sortBy.value, direction: direction.value }); message.success('导出文件已开始下载') } catch (error) { message.error(error instanceof Error ? error.message : '维度分析导出失败') } finally { exporting.value = false } }
onMounted(() => { void load() })
</script>

<style scoped>
.smart-alert { margin: 14px 0; }
.smart-dimension-panel { margin-top: 16px; }
.dimension-toolbar { display: grid; grid-template-columns: minmax(260px,1fr) 170px 110px auto auto auto; align-items: end; gap: 10px; margin-bottom: 12px; }
.dimension-toolbar label { display: grid; gap: 6px; color: #718096; font-size: 11px; }
.dimension-toolbar :deep(.ant-select) { width: 100%; }
.dimension-hint { margin: 0 0 14px; padding: 10px 12px; color: #6c7b90; font-size: 11px; border-radius: 7px; background: #f5f8fc; }
.dimension-value { color: #344258; font-weight: 600; }
.metric-link { padding: 0; color: #2471e8; border: 0; background: none; cursor: pointer; font: inherit; }
.metric-link:hover { text-decoration: underline; }
.negative { color: #c14f5e; }
:deep(.dimension-total-row td) { background: #f3f7fd !important; font-weight: 600; }
.dimension-pagination { padding-top: 16px; display: flex; align-items: center; justify-content: space-between; color: #7d8999; font-size: 11px; }
.metric-modal-actions { margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; color: #788598; font-size: 11px; }
.metric-modal-actions > div { display: flex; gap: 8px; }
.metric-groups { max-height: 560px; overflow: auto; }
.metric-groups section { padding: 13px 0; border-top: 1px solid #edf0f4; }
.metric-groups h3 { margin: 0 0 10px; color: #41516a; font-size: 12px; }
.metric-groups section > div { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 9px; }
.metric-groups label { display: flex; align-items: center; gap: 7px; color: #5f6d82; font-size: 11px; }
@media (max-width: 1180px) { .dimension-toolbar { grid-template-columns: 1fr 1fr 1fr; } }
@media (max-width: 700px) { .dimension-toolbar, .metric-groups section > div { grid-template-columns: 1fr; } .dimension-pagination, .metric-modal-actions { align-items: flex-start; flex-direction: column; gap: 12px; } }
</style>
