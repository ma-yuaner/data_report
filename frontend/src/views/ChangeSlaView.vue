<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { TableColumnsType } from 'ant-design-vue'
import { http, type ApiEnvelope } from '@/api/http'
import FilterPanel from '@/components/FilterPanel.vue'
import PageHeader from '@/components/PageHeader.vue'
import ChangeSlaLimitsView from '@/views/ChangeSlaLimitsView.vue'
import { evaluateErpNodes, excluded, nodes, stats, timeout } from '@/features/change-sla/model'
import type { ErpRecord, ErpSnapshot, SlaRow } from '@/features/change-sla/model'

const labels = {
  platform: '平台', air: '航司', owner: '改期员', supplier: '供应商', shift: '班次',
  intake: '进单类型', exchange: '换开类型', kind: '改签性质',
} as const
type Dimension = keyof typeof labels
type Node = 'audit' | 'operation'
type DrillMode = 'all' | 'late' | 'backfill'
type ReportRow = SlaRow & Partial<Record<'platformName' | 'supplier' | 'intake' | 'exchange' | 'shift', string> & {
  businessAt: number | null
  reportMinutes: number | null
}>
type Filters = Partial<Record<Dimension, string>> & { dates?: [string, string]; id: string }
type Step = { key: Dimension; value: string; label: string }
type Drill = { steps: Step[]; mode: DrillMode; analysis: boolean; previous?: { drill: Drill; dimension: Dimension } }
type Snapshot = ErpSnapshot & { coverage?: { missingDates: string[]; latestCoveredDate: string | null } }
const dimensions: Dimension[] = ['platform', 'air', 'owner', 'supplier', 'shift', 'intake', 'exchange', 'kind']
const limitsOpen = ref(false)
const primaryDimensions = dimensions.slice(0, 5).map(key => ({ label: '按' + labels[key], value: key }))
const emptyFilters = (): Filters => ({ id: '' })
const newTab = () => ({
  draft: emptyFilters(),
  applied: emptyFilters(),
  data: null as Snapshot | null,
  loading: false,
  error: '',
  unit: 'minute' as 'minute' | 'hour' | 'day',
  period: 'day' as 'day' | 'month',
  summaryDimension: 'platform' as Dimension,
  drill: null as Drill | null,
  nextDimension: 'air' as Dimension,
})
const tabs = reactive({ audit: newTab(), operation: newTab() })
const active = ref<Node>('audit')
const view = computed(() => tabs[active.value])
const record = ref<ReportRow | null>(null)
const isAudit = computed(() => active.value === 'audit')
const currentNode = computed(() => isAudit.value ? nodes[0] : nodes[1])
const dateLabel = computed(() => isAudit.value ? '改签审核日期' : '改签日期')
const snapshot = computed(() => view.value.data)
const missingDates = computed(() => snapshot.value?.coverage?.missingDates ?? [])
const rules = computed(() => snapshot.value?.rules ?? [])
const currentRule = computed(() => rules.value.find(rule => rule.node === currentNode.value))
const evaluated = computed<ReportRow[]>(() => snapshot.value
  ? evaluateErpNodes(snapshot.value.records, rules.value, snapshot.value.snapshot).filter(row => row.node === currentNode.value)
  : [])
function valueFor(row: ReportRow, key: Dimension) {
  return row[key]?.trim() || (key === 'platform' ? '未知平台' : '未记录')
}
function displayFor(row: ReportRow, key: Dimension) {
  if (key === 'platform') return row.platformName?.trim() || valueFor(row, key)
  return valueFor(row, key)
}
const filterFields = computed(() => dimensions.map(key => {
  const options = new Map<string, string>()
  for (const row of evaluated.value) options.set(valueFor(row, key), displayFor(row, key))
  const selected = view.value.draft[key]
  if (selected && !options.has(selected)) options.set(selected, selected)
  return {
    key,
    options: [...options].map(([value, label]) => ({ value, label }))
      .sort((left, right) => left.label.localeCompare(right.label, 'zh-CN')),
  }
}))
const rows = computed(() => evaluated.value.filter(row => {
  const filters = view.value.applied
  return (!filters.id.trim() || row.id === filters.id.trim()) &&
    dimensions.every(key => !filters[key] || valueFor(row, key) === filters[key])
}))
const number = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })
const formatter = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
})
const clock = (value: number | null | undefined) => value == null ? '—' : formatter.format(value)
const unitOptions = [{ label: '分钟', value: 'minute' }, { label: '小时', value: 'hour' }, { label: '天', value: 'day' }]
const periods = [{ label: '按日', value: 'day' }, { label: '按月', value: 'month' }]
const sourceLabel = (source: ErpRecord['endSource']) => ({
  '': '—', latest_issue_time: '出票时间回填', ACCEPT: 'ACCEPT 状态历史', audit_operator_time: '审核操作时间',
}[source] || '—')
const isBackfill = (row: ReportRow) => row.endSource === 'latest_issue_time'
const lateRate = (judged: number, late: number) => judged ? (100 * late / judged).toFixed(1) + '%' : '—'
const reportDuration = (row: ReportRow) => row.reportMinutes ?? null
function ruleSource(row: ReportRow) {
  const source = row.ruleDecision?.source
  if (source === 'platform') return '平台时限'
  if (source === 'fallback') return '未命中兜底'
  if (source === 'pending') return '待确认'
  return '—'
}
function mean(data: ReportRow[], field: (row: ReportRow) => number | null) {
  let count = 0
  let total = 0
  for (const row of data) {
    const elapsed = field(row)
    if (elapsed === null || !Number.isFinite(elapsed) || elapsed < 0) continue
    count++
    total += elapsed
  }
  return count ? total / count : null
}
function formatAverage(minutes: number | null) {
  if (minutes === null) return '—'
  const unit = view.value.unit
  const divisor = unit === 'minute' ? 1 : unit === 'hour' ? 60 : 1440
  return number.format(minutes / divisor) + ' ' + unitOptions.find(option => option.value === unit)?.label
}
const summary = computed(() => {
  const data = rows.value
  const result = stats(data)
  return [
    { label: 'SLA 达标率', value: result.rate },
    { label: 'SLA 超时率', value: lateRate(result.judged, result.late) },
    { label: '平均 SLA 耗时', value: formatAverage(mean(data, row => row.end === null || excluded(row) ? null : row.elapsed)) },
    { label: '平均报表耗时', value: formatAverage(mean(data, reportDuration)) },
    { label: '记录量', value: data.length, mode: 'all' as const },
    { label: '超时数', value: result.late, mode: 'late' as const },
  ]
})
const trend = computed(() => {
  const buckets = new Map<string, ReportRow[]>()
  for (const row of rows.value) {
    if (!row.created) continue
    const date = view.value.period === 'month' ? row.created.slice(0, 7) : row.created
    const batch = buckets.get(date)
    if (batch) batch.push(row)
    else buckets.set(date, [row])
  }
  return [...buckets].sort(([a], [b]) => a.localeCompare(b)).map(([date, values]) => ({ date, count: values.length, ...stats(values) }))
})
function group(data: ReportRow[], key: Dimension) {
  const map = new Map<string, { step: Step; records: ReportRow[] }>()
  for (const row of data) {
    const value = valueFor(row, key)
    const found = map.get(value)
    if (found) found.records.push(row)
    else map.set(value, { step: { key, value, label: displayFor(row, key) }, records: [row] })
  }
  return [...map.values()].map(({ step, records }) => {
    const result = stats(records)
    return {
      id: step.value,
      step,
      label: step.label,
      total: records.length,
      judged: result.judged,
      late: result.late,
      rate: lateRate(result.judged, result.late),
      average: formatAverage(mean(records, reportDuration)),
      backfill: records.filter(isBackfill).length,
    }
  }).sort((a,b) => b.late-a.late || b.total-a.total || a.label.localeCompare(b.label, 'zh-CN'))
}
const dimensionSummary = computed(() => group(rows.value, view.value.summaryDimension))
const drill = computed(() => view.value.drill)
const drillRows = computed(() => {
  const current = drill.value
  if (!current) return []
  return rows.value.filter(row => current.steps.every(step => valueFor(row, step.key) === step.value) &&
    (current.mode === 'all' || (current.mode === 'late' ? timeout(row) : isBackfill(row))))
})
const nextOptions = computed(() => dimensions.filter(key => !drill.value?.steps.some(step => step.key === key)).map(key => ({ label: labels[key], value: key })))
const drillGroups = computed(() => drill.value?.analysis && nextOptions.value.length ? group(drillRows.value, view.value.nextDimension) : [])
const drillTitle = computed(() => ({
  all: '全部单据', late: '超时单据', backfill: '出票时间回填单据',
}[drill.value?.mode || 'all']))
function openDrill(mode: DrillMode, steps: Step[] = [], analysis = false, previous?: Drill) {
  record.value = null
  view.value.drill = { mode, steps, analysis, previous: previous && { drill: previous, dimension: view.value.nextDimension } }
  view.value.nextDimension = dimensions.find(key => !steps.some(step => step.key === key)) || 'platform'
}
function continueDrill(step: Step, analysis = true, mode?: DrillMode) {
  const current = drill.value
  if (!current) return
  openDrill(mode ?? current.mode, [...current.steps, step], analysis, current)
}
function openCurrentDetails() {
  const current = drill.value
  if (current) openDrill(current.mode, current.steps, false, current)
}
function backDrill() {
  const previous = drill.value?.previous
  if (previous) {
    record.value = null
    view.value.drill = previous.drill
    view.value.nextDimension = previous.dimension
  }
}
function closeDrill() {
  record.value = null
  view.value.drill = null
}
const groupColumns = computed(() => [
  { title: '分组', dataIndex: 'label', width: 130 },
  { title: '总量', key: 'total', width: 85, align: 'right' as const },
  { title: '平均报表耗时', dataIndex: 'average', width: 120, align: 'right' as const },
  { title: '超时率', dataIndex: 'rate', width: 90, align: 'right' as const },
  { title: '超时数', key: 'late', width: 90, align: 'right' as const },
  ...(!isAudit.value ? [{ title: '出票时间回填', key: 'backfill', width: 120, align: 'right' as const }] : []),
  { title: '操作', key: 'analyze', width: 180 },
])
const summaryColumns = computed(() => groupColumns.value.map(column => column.key === 'analyze'
  ? { ...column, width: 105 }
  : column))
const detailColumns = computed<TableColumnsType<ReportRow>>(() => [
  { title: 'ERP 单据 ID', key: 'id', dataIndex: 'id', width: 115 },
  { title: dateLabel.value, key: 'date', width: 156 },
  ...dimensions.map(key => ({ title: labels[key], key, width: key === 'air' ? 72 : 105 })),
  { title: '状态', dataIndex: 'state', width: 118 },
  { title: '报表耗时（分钟）', key: 'report', width: 130, align: 'right' },
  { title: 'SLA 耗时／目标（分钟）', key: 'elapsed', width: 170, align: 'right' },
  { title: '时限来源', key: 'ruleSource', width: 120 },
  { title: '结束时间来源', key: 'endSource', width: 135 },
])
async function query(node: Node = active.value) {
  const state = tabs[node]
  if (state.loading) return
  const requested = { ...state.draft }
  const dates = requested.dates
  state.loading = true
  state.error = ''
  try {
    const params = dates?.length ? { from: dates[0], to: dates[1], node } : { node }
    const response = await http.get<ApiEnvelope<Snapshot>>('/v1/analysis/change-sla', { params })
    state.data = response.data.data
    if (!dates?.length) state.draft.dates = state.data.dates
    state.applied = { ...requested, dates: state.data.dates }
    state.drill = null
    if (active.value === node) record.value = null
  } catch (error) {
    state.error = error instanceof Error ? error.message : '查询失败，请稍后重试'
  } finally {
    state.loading = false
  }
}
function reset() {
  if (view.value.loading) return
  view.value.draft = emptyFilters()
  void query()
}
function activate(key: string | number) {
  if (key !== 'audit' && key !== 'operation') return
  active.value = key
  record.value = null
  if (!tabs[key].data) void query(key)
}
function csvCell(value: string | number | null | undefined) {
  if (typeof value === 'number') return String(value)
  const text = value ?? ''
  const protectedText = /^[\s\uFEFF]*[=+\-@\t\r\n]|^\d{16,}$/.test(text) ? "'" + text : text
  return '"' + protectedText.replaceAll('"', '""') + '"'
}
function exportRows(data: ReportRow[], suffix: string) {
  if (!data.length) return
  const header = ['ERP 单据 ID', dateLabel.value, ...dimensions.map(key => labels[key]), '状态', '报表耗时（分钟）',
    'SLA 耗时（分钟）', '目标（分钟）', '结束时间来源', '时限来源', '规则说明', '规则版本']
  const content = data.map(row => [row.id, clock(row.businessAt), ...dimensions.map(key => displayFor(row, key)),
    row.state, reportDuration(row), row.elapsed, row.rule?.minutes, sourceLabel(row.endSource), ruleSource(row),
    row.ruleDecision?.detail, row.ruleDecision?.version || row.rule?.id])
  const csv = [header, ...content].map(values => values.map(csvCell).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = currentNode.value + suffix + '.csv'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onMounted(() => void query())
</script>

<template>
  <main class="page-wrap sla-review">
    <PageHeader eyebrow="业务分析 / 改签分析" title="客服改签 SLA 管理看板"
      :description="snapshot ? '数据时间 '+clock(snapshot.snapshot)+'（北京时间）' : '按审核和操作节点查看改签时效'">
      <a-button @click="limitsOpen=true">时限配置</a-button>
    </PageHeader>
    <a-drawer v-model:open="limitsOpen" title="时限配置" width="min(1200px,100vw)" destroy-on-close>
      <ChangeSlaLimitsView />
    </a-drawer>
    <a-tabs :active-key="active" @change="activate">
      <a-tab-pane key="audit" tab="改期审核" />
      <a-tab-pane key="operation" tab="改期操作" />
    </a-tabs>
    <FilterPanel stacked :instant="false" :loading="view.loading" @reset="reset">
      <template #period><label class="picker-label">{{dateLabel}} <a-range-picker v-model:value="view.draft.dates" value-format="YYYY-MM-DD" /></label></template>
      <label v-for="field in filterFields" :key="field.key">
        <span>{{labels[field.key]}}</span>
        <a-select v-model:value="view.draft[field.key]" :options="field.options" placeholder="全部" allow-clear show-search option-filter-prop="label" />
      </label>
      <label><span>ERP 单据 ID</span><a-input v-model:value="view.draft.id" allow-clear @press-enter="query()" /></label>
      <template #actions><a-button type="primary" :loading="view.loading" @click="query()">查询</a-button></template>
    </FilterPanel>
    <a-alert v-if="view.error" class="sla-section" type="error" show-icon :message="view.error" />
    <a-spin :spinning="view.loading">
      <div v-if="snapshot">
        <a-alert v-if="missingDates.length" class="sla-section" type="warning" show-icon
          :message="'以下 '+missingDates.length+' 个业务日尚无成功快照，统计仅覆盖已更新日期'"
          :description="missingDates.join('、')" />
        <div class="section-toolbar sla-section">
          <span>{{isAudit?'申请到审核同意或拒绝':'进入待操作到履约完成'}}</span>
          <a-tag>{{currentRule ? '平台规则优先 · 未命中 '+currentRule.minutes+' 分钟' : '时限待配置'}}</a-tag>
          <a-space class="toolbar-end"><span>耗时单位</span><a-segmented v-model:value="view.unit" :options="unitOptions" /></a-space>
        </div>
        <div class="sla-metrics">
          <a-card v-for="metric in summary" :key="metric.label" size="small">
            <div class="metric-label">{{metric.label}}</div>
            <a-button v-if="metric.mode && Number(metric.value)>0" class="metric-button" type="link" @click="openDrill(metric.mode)">{{metric.value}}</a-button>
            <strong v-else class="metric-value">{{metric.value}}</strong>
          </a-card>
        </div>
        <a-alert v-if="!rows.length" class="sla-section" type="info" show-icon message="当前查询无记录，请调整日期或筛选条件。" />

        <a-card class="sla-section" title="处理趋势" size="small">
          <template #extra><a-segmented v-model:value="view.period" :options="periods" /></template>
          <div v-for="item in trend" :key="item.date" class="sla-trend">
            <span>{{item.date}}</span>
            <a-progress :percent="parseFloat(item.rate)||0" :show-info="false" size="small" />
            <span>{{item.rate}}达标 · {{item.late}} 超时 / {{item.count}} 条</span>
          </div>
        </a-card>

        <a-card class="sla-section" title="维度统计" size="small">
          <div class="dimension-picker">
            <a-segmented v-model:value="view.summaryDimension" :options="primaryDimensions" aria-label="切换统计维度" />
          </div>
          <a-table :key="active + ':' + view.summaryDimension" :columns="summaryColumns" :data-source="dimensionSummary" row-key="id" size="small"
            :scroll="{x:744}" :pagination="dimensionSummary.length>8 ? {pageSize:8,showSizeChanger:false} : false">
            <template #bodyCell="{column,record:item}">
              <span v-if="column.key==='total' || column.key==='late' || column.key==='backfill'">{{item[column.key]}}</span>
              <a-button v-else-if="column.key==='analyze'" type="link" size="small" @click="openDrill('all',[item.step],true)">分析此项</a-button>
            </template>
          </a-table>
        </a-card>
      </div>
    </a-spin>

    <a-drawer :open="!!drill" width="min(1120px, 100vw)" :title="drill?.analysis?'维度分析':drillTitle" @close="closeDrill">
      <template #extra>
        <a-button v-if="drill && !drill.analysis" :disabled="!drillRows.length" @click="exportRows(drillRows,'下钻明细')">导出当前明细</a-button>
      </template>
      <a-space wrap>
        <a-tag v-for="step in drill?.steps" :key="step.key">{{labels[step.key]}} {{step.label}}</a-tag>
        <span>{{drill?.analysis ? '当前范围' : drillTitle}} · {{drillRows.length}} 条</span>
        <a-button v-if="drill?.previous" type="link" size="small" @click="backDrill">返回上一级</a-button>
      </a-space>
      <a-card v-if="drill?.analysis" class="sla-section" size="small" title="继续定位问题维度">
        <template #extra><a-button :disabled="!drillRows.length" @click="openCurrentDetails">查看当前明细</a-button></template>
        <div v-if="nextOptions.length" class="dimension-picker">
          <a-segmented v-model:value="view.nextDimension" :options="nextOptions" aria-label="选择下一维度" />
        </div>
        <a-alert v-else type="info" show-icon message="可用维度已全部限定，请查看当前明细。" />
        <a-table v-if="nextOptions.length" :columns="groupColumns" :data-source="drillGroups" row-key="id" size="small"
          :scroll="{x:815}" :pagination="drillGroups.length>8 ? {pageSize:8,showSizeChanger:false} : false">
          <template #bodyCell="{column,record:item}">
            <span v-if="column.key==='total'">{{item.total}}</span>
            <template v-else-if="column.key==='late' || column.key==='backfill'">
              <a-button v-if="item[column.key]" size="small" type="link" @click="continueDrill(item.step,false,column.key)">{{item[column.key]}}</a-button>
              <span v-else>0</span>
            </template>
            <a-space v-else-if="column.key==='analyze'" :size="4">
              <a-button v-if="nextOptions.length>1" type="link" size="small" @click="continueDrill(item.step)">继续分析</a-button>
              <a-button type="link" size="small" @click="continueDrill(item.step,false)">查看明细</a-button>
            </a-space>
          </template>
        </a-table>
      </a-card>
      <a-table v-else-if="drill" class="sla-section" :columns="detailColumns" :data-source="drillRows" row-key="index"
        :scroll="{x:1540}" size="small" :pagination="drillRows.length>10 ? {pageSize:10,showSizeChanger:false} : false">
        <template #bodyCell="{column,record:item}">
          <a-button v-if="column.key==='id'" type="link" size="small" @click="record=item">{{item.id}}</a-button>
          <span v-else-if="column.key==='date'">{{clock(item.businessAt)}}</span>
          <span v-else-if="column.key==='report'">{{reportDuration(item) ?? '—'}}</span>
          <span v-else-if="column.key==='elapsed'">{{item.elapsed===null?'—':number.format(item.elapsed)}} / {{item.rule?.minutes??'—'}}</span>
          <span v-else-if="column.key==='ruleSource'">{{ruleSource(item)}}</span>
          <span v-else-if="column.key==='endSource'">{{sourceLabel(item.endSource)}}</span>
          <span v-else-if="typeof column.key==='string' && column.key in labels">{{displayFor(item,column.key as Dimension)}}</span>
        </template>
      </a-table>
      <a-drawer :open="!!record" width="min(720px, 100vw)" title="节点判定证据" @close="record=null">
        <a-descriptions v-if="record" bordered size="small" :column="1">
          <a-descriptions-item label="ERP 单据 ID">{{record.id}}</a-descriptions-item>
          <a-descriptions-item :label="dateLabel">{{clock(record.businessAt)}}</a-descriptions-item>
          <a-descriptions-item label="节点与状态">{{record.node}} / {{record.state}}（{{record.sourceStatus}}）</a-descriptions-item>
          <a-descriptions-item v-for="key in dimensions" :key="key" :label="labels[key]">{{displayFor(record,key)}}</a-descriptions-item>
          <a-descriptions-item label="报表耗时（分钟）">{{reportDuration(record) ?? '—'}}</a-descriptions-item>
          <a-descriptions-item label="SLA 开始">{{clock(record.start)}}</a-descriptions-item>
          <a-descriptions-item label="SLA 完成">{{clock(record.end)}}</a-descriptions-item>
          <a-descriptions-item label="结束时间来源">{{sourceLabel(record.endSource)}}</a-descriptions-item>
          <a-descriptions-item label="SLA 到期">{{clock(record.due)}}</a-descriptions-item>
          <a-descriptions-item label="判定规则">{{record.rule ? [record.rule.id,record.rule.minutes+' 分钟'].join(' / ') : '—'}}</a-descriptions-item>
          <a-descriptions-item label="时限来源">{{ruleSource(record)}}</a-descriptions-item>
          <a-descriptions-item v-if="record.ruleDecision?.revision" label="时限配置版本">{{record.ruleDecision.revision}}</a-descriptions-item>
          <a-descriptions-item v-if="record.ruleDecision?.effectiveFromMs" label="配置生效时间">{{clock(record.ruleDecision.effectiveFromMs)}}</a-descriptions-item>
          <a-descriptions-item v-if="record.ruleDecision?.detail" label="规则说明">{{record.ruleDecision.detail}}</a-descriptions-item>
          <a-descriptions-item label="关联单据数">{{record.linked}}</a-descriptions-item>
        </a-descriptions>
      </a-drawer>
    </a-drawer>
  </main>
</template>

<style scoped>
.picker-label,.section-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.sla-section{margin-top:16px}
.dimension-picker{max-width:100%;overflow-x:auto;margin-bottom:12px}
.toolbar-end{margin-left:auto}
.sla-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:10px}
.metric-label{color:var(--platform-text-muted,#69768a);margin-bottom:6px}
.metric-value,.metric-button{font-size:23px;line-height:1.3;font-variant-numeric:tabular-nums}
.metric-button{padding:0;height:auto}
.sla-trend{display:grid;grid-template-columns:110px minmax(40px,1fr) auto;align-items:center;gap:10px}
</style>
