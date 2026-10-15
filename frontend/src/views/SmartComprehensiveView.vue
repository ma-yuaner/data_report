<template>
  <div class="page-wrap smart-comprehensive-page">
    <PageHeader eyebrow="SMART BUSINESS & PLACEMENT" title="智能综合分析" description="把智能经营表现、业务维度和投放任务放在同一条分析链路中">
      <a-button v-if="canOpenPlacement" @click="router.push('/smart-analysis/placement/policies')">投放任务</a-button>
    </PageHeader>

    <SmartAnalysisFilters page="comprehensive" :loading="loading" @query="queryFromStart" @reset="queryFromStart" />
    <DataStateBar :label="stateLabel" :message="stateMessage" :freshness="data?.overview.updatedAt || '尚未读取'" metric-state="智能指标 × 投放覆盖 v1.0" />
    <a-alert v-if="data?.overview.error" class="smart-alert" type="error" show-icon :message="data.overview.error" />
    <a-alert v-if="data?.placement.error" class="smart-alert" type="warning" show-icon message="投放联动暂不可用" :description="data.placement.error" />
    <a-alert v-else-if="data?.placement.truncated" class="smart-alert" type="warning" show-icon message="投放任务数量超过当前联动上限" description="当前只展示最近的1000个可见任务，请缩小日期或业务筛选范围后再判断覆盖情况。" />

    <a-spin :spinning="loading" tip="正在汇总智能表现和投放任务">
      <section class="summary-grid">
        <button @click="openTotalDetail('all')"><span>全部出票量</span><strong>{{ count(data?.overview.metrics.ticketCount) }}</strong><small>张 · {{ count(data?.overview.metrics.segmentCount) }} 航段</small></button>
        <button @click="openTotalDetail('participation')"><span>参与智能</span><strong>{{ count(activeMetrics.participatedCount) }}</strong><small>参与率 {{ percent(activeMetrics.participationRate) }}</small></button>
        <button @click="openTotalDetail('use')"><span>使用智能</span><strong>{{ count(activeMetrics.usedCount) }}</strong><small>使用率 {{ percent(activeMetrics.useRate) }}</small></button>
        <button class="profit-card" @click="openTotalDetail('use')"><span>智能利润</span><strong>{{ money(activeMetrics.profit) }}</strong><small>元 · 单张 {{ money(activeMetrics.averageProfit) }}</small></button>
        <div><span>监控中投放</span><strong>{{ count(data?.placement.summary.monitoringTaskCount) }}</strong><small>流程中 {{ count(data?.placement.summary.workflowTaskCount) }} 项</small></div>
        <div><span>任务命中记录</span><strong>{{ count(data?.placement.summary.matchedOrderCount) }}</strong><small>{{ data?.placement.available ? '按当前账号数据范围' : '投放数据未读取' }}</small></div>
      </section>

      <a-card :bordered="false" class="panel-card dimension-card">
        <template #title>维度经营表现与投放覆盖</template>
        <template #extra><span class="panel-caption">点击“分析此项”查看业务明细和关联投放</span></template>
        <div class="dimension-toolbar">
          <label><span>分析维度</span><a-select v-model:value="groupBy" :options="coverageDimensions" @change="queryFromStart" /></label>
          <label><span>排序指标</span><a-select v-model:value="sortBy" :options="sortOptions" @change="queryFromStart" /></label>
          <label><span>排序</span><a-select v-model:value="direction" :options="directionOptions" @change="queryFromStart" /></label>
          <a-button @click="queryFromStart">刷新分析</a-button>
        </div>
        <p class="coverage-note">任务未限制站点、航线、产品或订单来源时，代表覆盖该维度下的全部值；任务数不可跨行相加，命中记录也不是跨政策去重订单数。投放覆盖只映射平台、站点、航司、航线、产品和订单来源，其他筛选仅作用于智能指标。只有登记投放成功并进入监控，才标记为“监控中”。</p>

        <a-table :data-source="rows" :columns="columns" :pagination="false" row-key="key" size="middle" :scroll="{ x: 1290 }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'dimension'"><div class="dimension-name"><strong>{{ record.path[0]?.name }}</strong><small>{{ dimensionLabel }}</small></div></template>
            <template v-else-if="column.key === 'ticketCount'">{{ count(record.metrics.ticketCount) }}</template>
            <template v-else-if="column.key === 'segmentCount'">{{ count(record.metrics.segmentCount) }}</template>
            <template v-else-if="column.key === 'participated'">{{ count(metricSet(record.metrics).participatedCount) }}</template>
            <template v-else-if="column.key === 'used'">{{ count(metricSet(record.metrics).usedCount) }}</template>
            <template v-else-if="column.key === 'useRate'">{{ percent(metricSet(record.metrics).useRate) }}</template>
            <template v-else-if="column.key === 'profit'"><span :class="{ negative: Number(metricSet(record.metrics).profit || 0) < 0 }">{{ money(metricSet(record.metrics).profit) }}</span></template>
            <template v-else-if="column.key === 'coverage'">
              <div class="coverage-state"><a-tag :color="coverageMeta(record.relatedTasks).color">{{ coverageMeta(record.relatedTasks).label }}</a-tag><small>{{ record.relatedTasks.length }} 个关联任务</small></div>
            </template>
            <template v-else-if="column.key === 'matched'">{{ count(matchedOrders(record.relatedTasks)) }}</template>
            <template v-else-if="column.key === 'action'"><a-button type="link" size="small" @click="openAnalysis(record)">分析此项</a-button></template>
          </template>
          <template #emptyText><a-empty :description="data?.dimensions.available ? '当前范围暂无维度数据' : '维度数据不可用'" /></template>
        </a-table>
        <div class="pagination-row"><span>共 {{ data?.dimensions.total || 0 }} 项</span><a-pagination v-model:current="page" v-model:page-size="pageSize" :total="data?.dimensions.total || 0" :show-size-changer="true" :page-size-options="['10','20','50','100']" @change="load" @show-size-change="changePageSize" /></div>
      </a-card>
    </a-spin>

    <a-drawer v-model:open="analysisOpen" title="分析此项" width="min(760px, 94vw)" placement="right">
      <template v-if="selectedRow">
        <div class="drawer-heading"><div><span>{{ dimensionLabel }}</span><h2>{{ selectedRow.path[0]?.name }}</h2></div><a-tag :color="coverageMeta(selectedRow.relatedTasks).color">{{ coverageMeta(selectedRow.relatedTasks).label }}</a-tag></div>
        <section class="drawer-metrics">
          <div><span>出票量</span><strong>{{ count(selectedRow.metrics.ticketCount) }}</strong></div>
          <div><span>航段数</span><strong>{{ count(selectedRow.metrics.segmentCount) }}</strong></div>
          <div><span>智能参与</span><strong>{{ count(metricSet(selectedRow.metrics).participatedCount) }}</strong></div>
          <div><span>智能使用</span><strong>{{ count(metricSet(selectedRow.metrics).usedCount) }}</strong></div>
          <div><span>智能利润</span><strong>{{ money(metricSet(selectedRow.metrics).profit) }}</strong></div>
          <div><span>命中订单</span><strong>{{ count(matchedOrders(selectedRow.relatedTasks)) }}</strong></div>
        </section>
        <div class="drawer-actions"><a-button type="primary" @click="openRowDetails(selectedRow)">查看出票明细</a-button><a-button v-if="canCreatePlacement" @click="createPlacement(selectedRow)">创建投放机会</a-button></div>
        <section class="task-section">
          <header><div><h3>关联投放任务</h3><p>严格区分“已建任务”和“已投放监控”；草稿与审核中不会标记为投放成功。</p></div><a-tag>{{ selectedRow.relatedTasks.length }} 项</a-tag></header>
          <a-empty v-if="!selectedRow.relatedTasks.length" description="当前维度还没有可见的投放任务" />
          <article v-for="task in selectedRow.relatedTasks" :key="task.id" class="task-card">
            <div><strong>{{ task.opportunityName }}</strong><code>{{ task.taskNo }}</code><span>{{ task.platformName }} · {{ task.airlineCode }} · {{ routeName(task) }}</span></div>
            <div><a-tag :color="taskStatus(task.status).color">{{ taskStatus(task.status).label }}</a-tag><small>命中 {{ count(task.matchedOrderCount) }} 单</small><a-button v-if="canOpenPlacement" type="link" size="small" @click="openTask(task.id)">查看任务</a-button></div>
          </article>
        </section>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Empty as AEmpty, message } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import SmartAnalysisFilters from '@/components/SmartAnalysisFilters.vue'
import { smartAnalysisApi, type SmartComprehensiveData, type SmartDimensionData, type SmartMetrics, type SmartPlacementCoverageTask, type SmartStage } from '@/api/smartAnalysis'
import { useSmartAnalysisStore } from '@/stores/smartAnalysis'
import { useAuthStore } from '@/stores/auth'

type AnalysisRow = SmartDimensionData['rows'][number] & { relatedTasks: SmartPlacementCoverageTask[] }

const router = useRouter()
const store = useSmartAnalysisStore()
const authStore = useAuthStore()
const pageState = store.pages.comprehensive
const data = ref<SmartComprehensiveData>()
const loading = ref(false)
const groupBy = ref('platform')
const sortBy = ref('smartProfit')
const direction = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const pageSize = ref(20)
const analysisOpen = ref(false)
const selectedRow = ref<AnalysisRow>()
const integer = new Intl.NumberFormat('zh-CN')
const currency = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const coverageDimensions = [
  { label: 'OTA平台', value: 'platform' }, { label: '航司', value: 'airline' },
  { label: '航线', value: 'route' }, { label: 'OTA站点', value: 'site' },
  { label: '产品类型', value: 'productType' }, { label: '订单来源', value: 'orderSource' },
]
const sortOptions = [
  { label: '智能利润', value: 'smartProfit' }, { label: '智能使用出票量', value: 'usedCount' },
  { label: '全部出票量', value: 'ticketCount' }, { label: '总航段数', value: 'segments' },
  { label: '全部预估利润', value: 'totalProfit' },
]
const directionOptions = [{ label: '降序', value: 'desc' }, { label: '升序', value: 'asc' }]
const columns = computed(() => [
  { title: dimensionLabel.value, key: 'dimension', width: 150, fixed: 'left' as const },
  { title: '出票量', key: 'ticketCount', width: 100 }, { title: '航段数', key: 'segmentCount', width: 100 },
  { title: '智能参与', key: 'participated', width: 110 }, { title: '智能使用', key: 'used', width: 110 },
  { title: '使用率', key: 'useRate', width: 100 }, { title: '智能利润', key: 'profit', width: 130 },
  { title: '投放覆盖', key: 'coverage', width: 180 }, { title: '命中记录', key: 'matched', width: 100 },
  { title: '操作', key: 'action', width: 105, fixed: 'right' as const },
])
const activeKey = computed(() => pageState.smartType === 'all' ? 'smart' : pageState.smartType)
const emptySmartMetrics = { participatedCount: null, succeededCount: null, usedCount: null, profit: null, participationRate: null, successRate: null, adoptionRate: null, participationUseRate: null, useRate: null, averageProfit: null }
const activeMetrics = computed(() => data.value?.overview.metrics[activeKey.value] ?? emptySmartMetrics)
const dimensionLabel = computed(() => coverageDimensions.find(item => item.value === groupBy.value)?.label || '分析维度')
const canCreatePlacement = computed(() => Boolean(authStore.user?.isAdmin || authStore.user?.permissions?.includes('smart_placement.create')))
const canOpenPlacement = computed(() => Boolean(authStore.user?.isAdmin || authStore.user?.menuCodes?.includes('smart.placement.policies')))
const stateLabel = computed(() => loading.value ? '分析读取中' : data.value?.overview.available && data.value.overview.hasData ? '真实MySQL数据' : data.value?.overview.available ? '当前范围暂无数据' : '数据不可用')
const stateMessage = computed(() => data.value?.overview.hasData ? `${data.value.overview.source} · 投放任务按当前账号数据范围联动` : data.value?.overview.error || '查询无记录不认定为真实零')
const rows = computed<AnalysisRow[]>(() => (data.value?.dimensions.rows || []).map(row => ({ ...row, relatedTasks: relatedTasks(row) })))

function metricSet(metrics: SmartMetrics) { return metrics[activeKey.value] }
function count(value: number | null | undefined) { return value == null ? '—' : integer.format(Number(value)) }
function money(value: string | null | undefined) { return value == null ? '—' : currency.format(Number(value)) }
function percent(value: number | null | undefined) { return value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%` }
function routeName(task: SmartPlacementCoverageTask) { return task.routeText || [task.departureCode, task.arrivalCode].filter(Boolean).join('-') || '全部航线' }
function taskValue(task: SmartPlacementCoverageTask) {
  const values: Record<string, string | null> = { platform: task.platformName, site: task.siteName, airline: task.airlineCode, route: routeName(task) === '全部航线' ? null : routeName(task), productType: task.productType, orderSource: task.orderSource }
  return values[groupBy.value] || null
}
function relatedTasks(row: SmartDimensionData['rows'][number]) {
  const expected = row.path[0]?.value
  return (data.value?.placement.rows || []).filter(task => {
    const actual = taskValue(task)
    if (!actual) return ['site', 'route', 'productType', 'orderSource'].includes(groupBy.value)
    return expected === '__NULL__' ? !actual : actual === row.path[0]?.name
  })
}
function matchedOrders(tasks: SmartPlacementCoverageTask[]) { return tasks.reduce((sum, task) => sum + Number(task.matchedOrderCount || 0), 0) }
function coverageMeta(tasks: SmartPlacementCoverageTask[]) {
  if (tasks.some(task => task.status === 'MONITORING')) return { label: '监控中', color: 'green' }
  if (tasks.some(task => ['PENDING_DATA_REVIEW', 'PENDING_POLICY_REVIEW', 'CLAIMABLE', 'IN_PROGRESS'].includes(task.status))) return { label: '流程中', color: 'blue' }
  if (tasks.some(task => task.status === 'DRAFT')) return { label: '草稿', color: 'orange' }
  if (tasks.length) return { label: '已停止/结束', color: 'default' }
  return { label: '未投递', color: 'red' }
}
function taskStatus(status: string) {
  const values: Record<string, { label: string; color: string }> = {
    DRAFT: { label: '草稿', color: 'default' }, PENDING_DATA_REVIEW: { label: '待数据审核', color: 'orange' },
    PENDING_POLICY_REVIEW: { label: '待政策审核', color: 'gold' }, CLAIMABLE: { label: '待认领', color: 'blue' },
    IN_PROGRESS: { label: '投放中', color: 'cyan' }, MONITORING: { label: '监控中', color: 'green' },
    FAILED: { label: '投放失败', color: 'red' }, REJECTED: { label: '已驳回', color: 'red' },
    CLOSED: { label: '已作废', color: 'default' }, ENDED: { label: '已结束', color: 'default' },
  }
  return values[status] || { label: status, color: 'default' }
}

async function load() {
  loading.value = true
  try {
    data.value = await smartAnalysisApi.comprehensive({ ...pageState.applied }, { groupBy: groupBy.value, smartType: pageState.smartType, sortBy: sortBy.value, direction: direction.value, page: page.value, pageSize: pageSize.value })
  } catch (error) {
    data.value = undefined
    message.error(error instanceof Error ? error.message : '智能综合分析加载失败')
  } finally { loading.value = false }
}
function queryFromStart() { page.value = 1; void load() }
function changePageSize(_current: number, size: number) { pageSize.value = size; page.value = 1; void load() }
function openAnalysis(row: AnalysisRow) { selectedRow.value = row; analysisOpen.value = true }
function openTotalDetail(stage: SmartStage) {
  if (!data.value?.overview.hasData) return
  store.beginDrill({ sourcePath: '/smart-analysis/comprehensive', sourceTitle: '智能综合分析', sourcePage: 'comprehensive', stage, tags: [{ label: '指标范围', value: stage === 'all' ? '全部出票' : stage === 'participation' ? '参与智能' : '使用智能' }] })
  void router.push({ path: '/smart-analysis/details', query: { stage, smartType: pageState.smartType, drill: '1' } })
}
function openRowDetails(row: AnalysisRow) {
  store.beginDrill({ sourcePath: '/smart-analysis/comprehensive', sourceTitle: '智能综合分析', sourcePage: 'comprehensive', stage: 'all', path: row.path, tags: row.path.map(item => ({ label: item.label, value: item.name })) })
  void router.push({ path: '/smart-analysis/details', query: { stage: 'all', smartType: pageState.smartType, drill: '1' } })
}
function createPlacement(row: AnalysisRow) {
  const path = row.path[0]
  const routeParts = groupBy.value === 'route' && path?.value !== '__NULL__' ? String(path.name).split('-', 2) : []
  const filters = pageState.applied
  const analysisStartDate = filters.startDate || filters.orderStart || filters.firstDepStart
  const analysisEndDate = filters.endDate || filters.orderEnd || filters.firstDepEnd
  void router.push({ path: '/smart-analysis/placement/policies', query: {
    create: '1', opportunityName: `${path?.name || dimensionLabel.value}智能投放机会`, opportunitySource: 'AUTO_ANALYSIS', analysisRuleCode: 'SMART_COMPREHENSIVE_V1', analysisStartDate, analysisEndDate,
    platformName: groupBy.value === 'platform' ? path?.name : filters.platform,
    siteName: groupBy.value === 'site' ? path?.name : filters.site,
    airlineCode: groupBy.value === 'airline' ? path?.name : filters.airline,
    departureCode: routeParts[0] || '', arrivalCode: routeParts[1] || '',
    productType: groupBy.value === 'productType' ? path?.name : filters.productType,
    orderSource: groupBy.value === 'orderSource' ? path?.name : filters.orderSource,
    historicalTicketCount: String(row.metrics.ticketCount ?? ''), historicalProfitCny: String(row.metrics.totalProfit ?? ''),
  } })
}
function openTask(taskId: number) { void router.push({ path: '/smart-analysis/placement/policies', query: { taskId: String(taskId) } }) }

onMounted(load)
</script>

<style scoped>
.smart-alert { margin: 14px 0; }
.summary-grid { display: grid; grid-template-columns: repeat(6,minmax(0,1fr)); gap: 12px; margin: 16px 0; }
.summary-grid > button,.summary-grid > div { min-height: 116px; padding: 18px; display: grid; gap: 8px; text-align: left; border: 1px solid #e3e9f2; border-radius: 12px; background: #fff; box-shadow: 0 6px 18px rgba(27,44,72,.04); }
.summary-grid > button { cursor: pointer; }.summary-grid > button:hover { border-color: #a8c8f8; transform: translateY(-1px); }
.summary-grid span,.summary-grid small { color: #7b8798; font-size: 11px; }.summary-grid strong { color: #253650; font-size: 25px; }.summary-grid .profit-card { border-color: #2f72da; background: linear-gradient(135deg,#2f72da,#4388ef); }.summary-grid .profit-card > * { color: #fff; }
.dimension-card { margin-bottom: 16px; }.dimension-toolbar { display: grid; grid-template-columns: 210px 200px 120px auto; align-items: end; gap: 10px; margin-bottom: 12px; }.dimension-toolbar label { display: grid; gap: 6px; color: #718096; font-size: 11px; }.dimension-toolbar :deep(.ant-select) { width: 100%; }
.coverage-note { margin: 0 0 14px; padding: 10px 12px; color: #65758b; font-size: 11px; line-height: 1.7; border-radius: 8px; background: #f5f8fc; }
.dimension-name { display: grid; gap: 3px; }.dimension-name strong { color: #304158; }.dimension-name small { color: #8c98a8; font-size: 10px; }.negative { color: #c44f5b; }.coverage-state { display: flex; align-items: center; gap: 7px; }.coverage-state small { color: #8491a3; font-size: 10px; }.pagination-row { padding-top: 15px; display: flex; align-items: center; justify-content: space-between; color: #7d8999; font-size: 11px; }
.drawer-heading { padding: 4px 0 16px; display: flex; align-items: flex-start; justify-content: space-between; border-bottom: 1px solid #edf0f4; }.drawer-heading span { color: #3178f6; font-size: 10px; font-weight: 600; letter-spacing: .1em; }.drawer-heading h2 { margin: 5px 0 0; color: #203047; font-size: 22px; }.drawer-metrics { margin: 16px 0; display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 10px; }.drawer-metrics div { padding: 14px; display: grid; gap: 6px; border: 1px solid #e6ebf2; border-radius: 9px; background: #fbfcfe; }.drawer-metrics span { color: #8491a3; font-size: 10px; }.drawer-metrics strong { color: #2c3c54; font-size: 18px; }.drawer-actions { display: flex; gap: 9px; margin-bottom: 20px; }
.task-section { border-top: 1px solid #edf0f4; padding-top: 18px; }.task-section > header { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; }.task-section h3 { margin: 0 0 4px; color: #26354b; font-size: 15px; }.task-section p { margin: 0; color: #7c899b; font-size: 11px; }.task-card { padding: 14px 0; display: flex; justify-content: space-between; gap: 14px; border-top: 1px solid #edf0f4; }.task-card:first-of-type { border-top: 0; }.task-card > div { display: grid; gap: 4px; }.task-card > div:last-child { justify-items: end; }.task-card strong { color: #304158; }.task-card code,.task-card span,.task-card small { color: #8390a2; font-size: 10px; }
@media(max-width:1200px){.summary-grid{grid-template-columns:repeat(3,minmax(0,1fr));}} @media(max-width:760px){.summary-grid,.drawer-metrics{grid-template-columns:repeat(2,minmax(0,1fr));}.dimension-toolbar{grid-template-columns:1fr 1fr}.pagination-row,.task-card{align-items:flex-start;flex-direction:column}.task-card>div:last-child{justify-items:start}} @media(max-width:520px){.summary-grid,.drawer-metrics,.dimension-toolbar{grid-template-columns:1fr}}
</style>
