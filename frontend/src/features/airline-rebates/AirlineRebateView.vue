<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal, Statistic } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import FormDialog from '@/components/FormDialog.vue'
import FormGrid from '@/components/FormGrid.vue'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
import { ApiError } from '@/api/http'
import {
  airlineRebates, type RebateCondition, type RebateRouteDay, type RebateRouteCategory, type RebateDetailRow,
  type RebatePolicy, type RebateNumber, type RebateProgress, type RebateRule, type RebateTask, type RebateVersion,
} from '@/api/airlineRebates'
import { useAuthStore } from '@/stores/auth'
import { formatHiveMapping } from './hiveMappingDisplay'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const isPolicies = computed(() => route.name === 'airline-rebate-policies')
const confirmedCheck = ref(false)
const runningTrial = ref(false)
const canManage = computed(() => Boolean(auth.user?.isAdmin || auth.user?.permissions?.includes('airline_rebates.manage')))
const policies = ref<RebatePolicy[]>([])
const tasks = ref<RebateTask[]>([])
const taskQuery = ref('')
const airlineFilter = ref<string>()
const refreshFilter = ref<RebateTask['refreshStatus']>()
const airlineOptions = computed(() => [...new Set(tasks.value.map(item => item.airline).filter(Boolean))]
  .sort().map(value => ({ value, label: value })))
const filteredTasks = computed(() => {
  const query = taskQuery.value.trim().toLowerCase()
  return tasks.value.filter(item =>
    (!airlineFilter.value || item.airline === airlineFilter.value)
    && (!refreshFilter.value || item.refreshStatus === refreshFilter.value)
    && (!query || [item.name, item.policyName, item.owner].some(value => value?.toLowerCase().includes(query))),
  )
})
function resetTaskFilters() {
  taskQuery.value = ''
  airlineFilter.value = undefined
  refreshFilter.value = undefined
}
const loading = ref(false)
const listError = ref('')
const notice = ref('')
const uploadInput = ref<HTMLInputElement>()
const file = ref<File>()
const uploading = ref(false)
const drawer = ref<'policy' | 'create' | 'details' | 'edit' | 'analysis'>()
const drawerBusy = ref(false)
const saving = ref(false)
const drawerError = ref('')
const activePolicy = ref<RebatePolicy>()
const task = ref<RebateTask>()
const policyRules = ref<RebateRule[]>([])
const versions = ref<RebateVersion[]>([])
const selectedVersion = ref<number>()
const draft = ref<RebateRule[]>([])
const reason = ref('')
const taskName = ref('')
const owner = ref('')
const initialCreateValues = ref('')
const createDirty = computed(() => createValues() !== initialCreateValues.value)
const createReady = computed(() => !!activePolicy.value && !!taskName.value.trim() && !!owner.value.trim() && !drawerBusy.value)
const createValues = () => JSON.stringify([activePolicy.value?.id, taskName.value, owner.value])
const progress = ref<RebateProgress>()
const dailyPage = ref(1)
const routeScope = ref<{ category: RebateRouteCategory; runId: string }>()
const routeDays = ref<RebateRouteDay[]>([])
const day = ref<RebateRouteDay>()
const exporting = ref(false)
const detailRows = ref<RebateDetailRow[]>([])
const detailPage = ref(1)
const detailQuery = ref('')
const detailTotal = ref(0)
let listRequest: AbortController | undefined
let drawerRequest: AbortController | undefined

const currentVersion = computed(() => versions.value[0])
const viewedVersion = computed(() => versions.value.find(item => item.version === selectedVersion.value))
const previousVersion = computed(() => versions.value.find(item => item.version < (viewedVersion.value?.version ?? 0)))
const readyPolicies = computed(() => policies.value.filter(item => item.status === 'ready' && item.confirmed))
const ruleGroups = computed(() => drawer.value === 'policy' ? policyRules.value : drawer.value === 'edit' ? draft.value : viewedVersion.value?.rules ?? [])
const drawerTitle = computed(() => {
  if (drawer.value === 'policy') return '解析结果 · ' + (activePolicy.value?.name ?? '')
  if (drawer.value === 'create') return '新建后返任务'
  const label = drawer.value === 'analysis'
    ? (day.value ? '当日明细' : routeScope.value ? '航线类型逐日数据' : '分析此项')
    : drawer.value === 'edit' ? '编辑规则' : '任务详情'
  return label + ' · ' + (task.value?.name ?? '')
})
const policyColumns = [
  { title: '文件', dataIndex: 'name', width: 310 }, { title: '航司', dataIndex: 'airline', width: 105 },
  { title: '政策期', dataIndex: 'period', width: 195 }, { title: '解析状态', key: 'status', width: 160 },
  { title: '操作', key: 'action', width: 140 },
]
const taskColumns = [
  { title: '任务名称', key: 'name', width: 205 },
  { title: '航司 / 负责人', key: 'owner', width: 116 },
  { title: '政策期', dataIndex: 'period', width: 165 },
  { title: '计量进度（试算）', key: 'progress', width: 196, align: 'right' as const },
  { title: '预计后返（试算）', key: 'reward', width: 160, align: 'right' as const },
  { title: '数据更新', key: 'asOf', width: 226 },
  { title: '操作', key: 'action', width: 176 },
]
const taskPagination = { defaultPageSize: 10, showSizeChanger: false, showTotal: (total: number) => `共 ${total} 条` }
const detailColumns = [
  { title: '订单号', dataIndex: 'orderNo', width: 145 },
  { title: '票号', dataIndex: 'ticketNo', width: 145 },
  { title: '航程', dataIndex: 'route', width: 175 },
  { title: '航段计划起飞日', key: 'segmentDates', width: 155 },
  { title: '实际舱位', key: 'segmentCabins', width: 95 },
  { title: '销售航司', key: 'segmentCarriers', width: 105 },
  { title: '币种', dataIndex: 'currency', width: 68 },
  { title: '整票票面价', key: 'ticketFare', width: 135, align: 'right' as const },
  { title: '计量金额', key: 'amount', width: 135, align: 'right' as const },
  { title: '批次费率', key: 'rate', width: 96, align: 'right' as const },
  { title: '本票预计后返', key: 'reward', width: 135, align: 'right' as const },
  { title: '订单已算后返（全批）', key: 'orderReward', width: 170, align: 'right' as const },
  { title: '匹配结果', dataIndex: 'result', width: 145 },
]
function segmentField(row: RebateDetailRow, key: 'date' | 'cabin' | 'marketingAirline') {
  return row.segmentDecisions?.map(segment => segment[key] || '—').join(' / ') || '—'
}
const statusText = { pending: '尚未产出', ready: '刷新成功', failed: '刷新失败' }
const statusColors = { pending: 'default', ready: 'green', failed: 'red' }
const refreshOptions = (['pending', 'ready', 'failed'] as const).map(value => ({ value, label: statusText[value] }))
const refreshModes = { scheduled: '定时刷新', manual: '手动刷新' }
const operators = [['eq', '等于'], ['in', '属于'], ['not_in', '排除'], ['gte', '大于等于'], ['gt', '大于'], ['lte', '小于等于'], ['review', '待确认']]
  .map(([value, label]) => ({ value, label }))
const number = (value: number | string) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const money = (value: RebateNumber, currency = '') => value == null ? '—' : [currency, number(value)].filter(Boolean).join(' ')
const percent = (value: RebateNumber) => value == null ? '—' : number(value) + '%'
const displayValue = (value: RebateCondition['value']) => Array.isArray(value) ? value.join(', ') : String(value)
const rateMatrix = computed(() => ruleGroups.value.filter(group => group.id.startsWith('tier-')).flatMap(group => {
  const value = (id: string) => group.conditions.find(condition => condition.id === id)?.value
  const groups = ruleGroups.value.find(rule => rule.id === 'routes')?.conditions
  const upper = value('maximum')
  const lower = Number(value('minimum')) / 10_000
  const threshold = upper ? `${lower} < T ≤ ${Number(upper) / 10_000}` : `T > ${lower}`
  return ['group_a', 'group_b'].map((id, index) => ({
    id: group.id + '-' + id, threshold, cabin: index === 0 ? 'A 组' : 'B 组',
    codes: groups?.find(condition => condition.id === id)?.value ?? '',
    rates: (value(id) as string[] | undefined) ?? [],
    sourceText: group.conditions.find(condition => condition.id === id)?.sourceText,
  }))
}))
const rebateRouteLabels = ['国际远程', '国际非远程', '地区非指定', '地区指定', '异地始发']
const policyOperatorLabels: Record<string, string> = {
  between: '介于（含首尾）',
  unrestricted: '不限',
  all: '同时满足',
  applies: '按政策执行',
}
const operatorLabel = (code: string) => policyOperatorLabels[code] ?? operators.find(item => item.value === code)?.label ?? code

function explain(error: unknown) {
  if (error instanceof ApiError && [404, 501, 503].includes(error.status ?? 0)) return '航司后返服务尚未接通或暂不可用。'
  if (error instanceof ApiError && error.status === 409) return '规则版本已变化，请重新打开任务后再编辑。'
  return error instanceof Error ? error.message : '请求失败，请重试。'
}

async function load() {
  listRequest?.abort()
  const request = new AbortController()
  listRequest = request
  loading.value = true
  listError.value = ''
  try {
    if (isPolicies.value) {
      const rows = await airlineRebates.listPolicies(request.signal)
      if (!request.signal.aborted) policies.value = rows
    } else {
      const rows = await airlineRebates.listTasks(request.signal)
      if (!request.signal.aborted) tasks.value = rows
    }
  } catch (error) {
    if (!request.signal.aborted) listError.value = explain(error)
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}
function closeDrawer() {
  if (saving.value) return
  drawerRequest?.abort()
  drawer.value = undefined
  routeScope.value = undefined
  day.value = undefined
  drawerBusy.value = false
}
function requestClose() {
  if (saving.value) return
  const dirty = drawer.value === 'edit' && (hasRuleChanges.value || !!reason.value.trim())
  if (dirty) {
    Modal.confirm({ title: '放弃未保存的修改？', okText: '放弃修改', cancelText: '继续编辑', onOk: closeDrawer })
  } else closeDrawer()
}
watch(() => route.name, () => {
  closeDrawer()
  notice.value = ''
  file.value = undefined
  void load()
}, { immediate: true })
onBeforeUnmount(() => { listRequest?.abort(); drawerRequest?.abort() })

async function loadDrawer(action: (signal: AbortSignal) => Promise<void>) {
  drawerRequest?.abort()
  const request = new AbortController()
  drawerRequest = request
  drawerError.value = ''
  drawerBusy.value = true
  try { await action(request.signal) }
  catch (error) { if (!request.signal.aborted) drawerError.value = explain(error) }
  finally { if (!request.signal.aborted) drawerBusy.value = false }
}
function selectFile(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = input.files?.[0]
  input.value = ''
  if (selected && !selected.name.toLowerCase().endsWith('.pdf')) {
    notice.value = '请选择 PDF 文件。'
    return
  }
  file.value = selected
  notice.value = ''
}
async function upload() {
  if (!file.value || uploading.value || !canManage.value) return
  uploading.value = true
  try {
    const policy = await airlineRebates.upload(file.value)
    file.value = undefined
    if (isPolicies.value) { notice.value = '已提交：' + policy.name; await load() }
  } catch (error) { if (isPolicies.value) notice.value = explain(error) }
  finally { uploading.value = false }
}
function openPolicy(policy: RebatePolicy) {
  activePolicy.value = policy
  confirmedCheck.value = false
  policyRules.value = []
  drawer.value = 'policy'
  void loadDrawer(async signal => {
    const rules = await airlineRebates.readPolicy(policy.id, signal)
    if (!signal.aborted) policyRules.value = rules
  })
}
async function confirmPolicy() {
  const item = activePolicy.value
  if (!item || !confirmedCheck.value || drawerBusy.value || saving.value) return
  saving.value = true
  drawerError.value = ''
  try {
    const confirmed = await airlineRebates.confirmPolicy(item.id)
    if (activePolicy.value?.id === item.id) {
      activePolicy.value = confirmed
      saving.value = false
      await router.push({ name: 'airline-rebate-tasks', query: { policy: confirmed.id } })
    }
    void load()
  } catch (error) { drawerError.value = explain(error) }
  finally { saving.value = false }
}
async function runTrial() {
  const item = task.value
  if (!item || runningTrial.value) return
  runningTrial.value = true
  drawerError.value = ''
  try {
    const data = await airlineRebates.run(item.id)
    if (drawer.value === 'analysis' && task.value?.id === item.id) progress.value = data
  } catch (error) {
    if (drawer.value === 'analysis' && task.value?.id === item.id && !day.value) {
      await loadDrawer(async signal => {
        const latest = await airlineRebates.progress(item.id, signal)
        if (!signal.aborted) {
          progress.value = latest
          drawerError.value = latest.status === 'failed' ? '' : explain(error)
        }
      })
    }
  } finally {
    runningTrial.value = false
    if (!isPolicies.value) void load()
  }
}
function openCreate() {
  if (!canManage.value) return
  activePolicy.value = undefined
  taskName.value = ''
  owner.value = auth.user?.displayName || auth.user?.username || ''
  initialCreateValues.value = createValues()
  drawer.value = 'create'
  void loadDrawer(async signal => {
    const rows = await airlineRebates.listPolicies(signal)
    if (signal.aborted) return
    policies.value = rows
    const policyId = route.query.policy
    const policy = readyPolicies.value.find(item => item.id === policyId)
    if (policy && createValues() === initialCreateValues.value) {
      selectPolicy(policy.id)
      initialCreateValues.value = createValues()
    }
  })
}
watch(() => route.query.policy, policy => {
  if (!isPolicies.value && typeof policy === 'string') openCreate()
}, { immediate: true })
function selectPolicy(id: string) {
  activePolicy.value = readyPolicies.value.find(item => item.id === id)
  taskName.value = activePolicy.value?.name ?? ''
}
async function create() {
  if (!activePolicy.value || !canManage.value || saving.value || !createReady.value) return
  saving.value = true
  drawerError.value = ''
  try {
    const created = await airlineRebates.createTask({ policyId: activePolicy.value.id, name: taskName.value.trim(), owner: owner.value.trim() })
    notice.value = '任务已建档'
    openTask(created, 'details')
    void load()
  } catch (error) { drawerError.value = explain(error) }
  finally { saving.value = false }
}
function openTask(item: RebateTask, mode: 'details' | 'edit' | 'analysis') {
  if (mode === 'edit' && (!canManage.value || item.editable === false)) return
  task.value = item
  drawer.value = mode
  day.value = undefined
  routeScope.value = undefined
  dailyPage.value = 1
  progress.value = undefined
  versions.value = []
  draft.value = []
  reason.value = ''
  void loadDrawer(async signal => {
    if (mode === 'analysis') {
      const result = await airlineRebates.progress(item.id, signal)
      if (!signal.aborted) progress.value = result
      return
    }
    const result = await airlineRebates.versions(item.id, signal)
    if (signal.aborted) return
    versions.value = [...result].sort((a, b) => b.version - a.version)
    selectedVersion.value = currentVersion.value?.version
    if (mode === 'edit' && currentVersion.value) draft.value = JSON.parse(JSON.stringify(currentVersion.value.rules))
  })
}
function changeValue(condition: RebateCondition, text: string) {
  const existing = condition.value
  if (typeof existing === 'number') condition.value = text.trim() === '' ? Number.NaN : Number(text)
  else if (Array.isArray(existing)) {
    const values = text.split(',').map(item => item.trim())
    condition.value = typeof existing[0] === 'number'
      ? values.map(item => item === '' ? Number.NaN : Number(item))
      : values
  } else condition.value = text
}
function preceding(group: RebateRule, condition: RebateCondition) {
  const old = previousVersion.value?.rules.find(item => item.id === group.id)?.conditions.find(item => item.id === condition.id)
  return old && (old.operator !== condition.operator || displayValue(old.value) !== displayValue(condition.value))
    ? operatorLabel(old.operator) + ' ' + displayValue(old.value) : ''
}
const hasRuleChanges = computed(() => Boolean(currentVersion.value) && JSON.stringify(draft.value) !== JSON.stringify(currentVersion.value?.rules))
const validDraft = computed(() => draft.value.every(group => group.conditions.every(condition => {
  const values = Array.isArray(condition.value) ? condition.value : [condition.value]
  return values.length > 0 && values.every(value => typeof value === 'number' ? Number.isFinite(value) : Boolean(value.trim()))
})))
async function save() {
  if (!task.value || !currentVersion.value || !canManage.value || saving.value || !hasRuleChanges.value || !validDraft.value || !reason.value.trim()) return
  saving.value = true
  drawerError.value = ''
  try {
    const saved = await airlineRebates.saveVersion(task.value.id, currentVersion.value.version, reason.value.trim(), draft.value)
    versions.value.unshift(saved)
    selectedVersion.value = saved.version
    drawer.value = 'details'
    notice.value = '已保存规则 V' + saved.version
  } catch (error) { drawerError.value = explain(error) }
  finally { saving.value = false }
}
function openRouteCategory(category: RebateRouteCategory) {
  const runId = progress.value?.runId
  const item = task.value
  if (!item || !runId || runningTrial.value) return
  routeScope.value = { category, runId }
  routeDays.value = []
  dailyPage.value = 1
  void loadDrawer(async signal => {
    const points = await airlineRebates.routeDays(item.id, runId, category.id, signal)
    if (!signal.aborted) routeDays.value = points
  })
}
async function exportRoute(dayDate?: string) {
  const scope = routeScope.value
  const item = task.value
  if (!item || !scope || exporting.value) return
  exporting.value = true
  try {
    const { data } = await airlineRebates.exportRoute(item.id, scope.runId, scope.category.id, dayDate)
    const url = URL.createObjectURL(data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `后返-${scope.category.name}-${dayDate || '全期'}.xlsx`
    anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    message.success('已生成导出文件')
  } catch (error) {
    message.error(explain(error))
  } finally {
    exporting.value = false
  }
}
function showDay(point: RebateRouteDay, page = 1) {
  const item = task.value
  const scope = routeScope.value
  if (!item || !scope) return
  if (day.value?.id !== point.id) detailQuery.value = ''
  day.value = point
  detailPage.value = page
  detailRows.value = []
  detailTotal.value = 0
  void loadDrawer(async signal => {
    const rows = await airlineRebates.details(item.id, point.id, scope.category.id, page, signal, detailQuery.value.trim())
    if (!signal.aborted) { detailRows.value = rows.items; detailTotal.value = rows.total }
  })
}
function backToProgress() {
  drawerRequest?.abort()
  if (day.value) day.value = undefined
  else routeScope.value = undefined
  drawerError.value = ''
  drawerBusy.value = false
}
</script>

<template>
  <div class="page-wrap">
    <PageHeader eyebrow="后返管理" :title="isPolicies ? '政策解析' : '任务管理'"
      :description="isPolicies ? '上传政策 PDF，查看解析初版及字段来源。' : '查看航司后返任务、规则版本与每日进度。'">
      <a-space>
        <a-button :loading="loading" @click="load">刷新</a-button>
        <a-button v-if="!isPolicies && canManage" type="primary" @click="openCreate">新建任务</a-button>
      </a-space>
    </PageHeader>
    <a-alert v-if="listError" type="warning" :message="listError" show-icon class="section" />
    <a-alert v-if="notice" type="info" :message="notice" show-icon class="section" />
    <template v-if="isPolicies">
      <a-card v-if="canManage" title="上传政策" class="section">
        <a-space wrap>
          <input ref="uploadInput" type="file" accept=".pdf,application/pdf" hidden @change="selectFile">
          <a-button :disabled="uploading || !!listError || loading" @click="uploadInput?.click()">选择 PDF</a-button>
          <span v-if="file">{{ file.name }}</span>
          <a-button type="primary" :loading="uploading" :disabled="!file || !!listError || loading" @click="upload">提交解析</a-button>
        </a-space>
      </a-card>
      <a-card title="解析文件" class="section">
        <a-table :data-source="policies" :columns="policyColumns" :loading="loading" row-key="id" :scroll="{ x: 865 }">
          <template #emptyText><a-empty :description="listError ? '解析文件暂不可用' : '暂无解析文件'" /></template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-tag :color="record.status === 'failed' ? 'red' : record.status === 'ready' ? 'green' : 'default'">{{ { pending: '解析中', ready: '已解析', failed: '解析失败' }[record.status as RebatePolicy['status']] }}</a-tag>
              <div v-if="record.errorMessage" class="muted">{{ record.errorMessage }}</div>
            </template>
            <a-button v-else-if="column.key === 'action'" type="link" :disabled="record.status !== 'ready'" @click="openPolicy(record)">查看解析结果</a-button>
          </template>
        </a-table>
      </a-card>
    </template>
    <template v-else>
      <FilterPanel :loading="loading" @reset="resetTaskFilters">
        <label for="rebate-task-query"><span>关键词</span>
          <a-input id="rebate-task-query" v-model:value="taskQuery" allow-clear placeholder="任务名称、政策文件或负责人" />
        </label>
        <label for="rebate-task-airline"><span>航司</span>
          <a-select id="rebate-task-airline" v-model:value="airlineFilter" :options="airlineOptions" allow-clear placeholder="全部航司" />
        </label>
        <label for="rebate-task-status"><span>更新状态</span>
          <a-select id="rebate-task-status" v-model:value="refreshFilter" :options="refreshOptions" allow-clear placeholder="全部状态" />
        </label>
      </FilterPanel>
      <a-card class="section task-card">
      <a-table :data-source="filteredTasks" :columns="taskColumns" :loading="loading" row-key="id"
        size="small" :scroll="{ x: 1244 }" sticky :pagination="taskPagination">
        <template #emptyText><a-empty :description="listError ? '任务暂不可用' : tasks.length ? '没有符合筛选条件的任务' : '暂无后返任务'" /></template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a-button type="link" class="task-name two-lines" @click="openTask(record, 'details')">{{ record.name }}</a-button>
            <div class="muted two-lines">{{ record.policyName || '—' }}</div>
          </template>
          <template v-else-if="column.key === 'owner'">
            <div>{{ record.airline || '—' }}</div>
            <div class="muted two-lines">{{ record.owner || '—' }}</div>
          </template>
          <template v-else-if="column.key === 'progress'">
            <strong>{{ money(record.actual, record.currency) }}</strong>
            <div class="muted">首档门槛 {{ money(record.target, record.currency) }}</div>
            <div class="muted">门槛进度 {{ percent(record.completionRate) }}</div>
          </template>
          <template v-else-if="column.key === 'reward'">
            <strong>{{ money(record.estimatedReward ?? null, record.currency) }}</strong>
            <div class="muted">档位 {{ record.tier || '—' }}</div>
          </template>
          <template v-else-if="column.key === 'asOf'">
            <a-tag :color="record.refreshStatus ? statusColors[record.refreshStatus as keyof typeof statusColors] : 'default'">
              {{ record.refreshStatus ? statusText[record.refreshStatus as keyof typeof statusText] : '状态未知' }}
            </a-tag>
            <div class="muted">最晚计划起飞日 {{ record.dataAsOf || '—' }}</div>
            <div class="muted">快照更新 {{ formatDateTimeDisplay(record.refreshedAt) }}</div>
            <div v-if="record.refreshMode" class="muted">{{ refreshModes[record.refreshMode as keyof typeof refreshModes] }}</div>
            <div v-if="record.refreshStatus === 'failed'" class="muted">{{ record.refreshedAt || record.actual != null ? '当前展示最近成功快照' : '暂无成功快照' }}</div>
          </template>
          <a-space v-else-if="column.key === 'action'" :size="4" wrap>
            <a-button type="link" size="small" @click="openTask(record, 'analysis')">分析此项</a-button>
            <a-button v-if="canManage && record.editable !== false" type="link" size="small" @click="openTask(record, 'edit')">编辑规则</a-button>
          </a-space>
        </template>
      </a-table>
      </a-card>
    </template>

    <FormDialog :open="drawer === 'create'" title="新建后返任务" :width="760"
      :busy="saving" :dirty="createDirty" :error="drawerError" :submit-disabled="!createReady"
      ok-text="确认建档" @submit="create" @cancel="closeDrawer">
      <a-alert v-if="!drawerError && !drawerBusy && !readyPolicies.length" message="请先在政策解析中确认政策，再创建任务。" type="info" show-icon class="section" />
      <a-form layout="vertical" :disabled="saving" @finish="create">
        <FormGrid>
          <a-form-item label="政策文件" html-for="rebate-create-policy" required class="form-span">
            <a-select id="rebate-create-policy" :value="activePolicy?.id" :loading="drawerBusy"
              :options="readyPolicies.map(item => ({ value: item.id, label: item.name }))"
              placeholder="选择已确认的政策" @change="(value: string) => selectPolicy(value)" />
          </a-form-item>
          <a-form-item label="任务名称" html-for="rebate-create-name" required>
            <a-input id="rebate-create-name" v-model:value="taskName" :maxlength="200" />
          </a-form-item>
          <a-form-item label="负责人" html-for="rebate-create-owner" required>
            <a-input id="rebate-create-owner" v-model:value="owner" :maxlength="100" />
          </a-form-item>
        </FormGrid>
      </a-form>
    </FormDialog>

    <a-drawer :open="!!drawer && drawer !== 'create'" :title="drawerTitle" placement="right" width="min(1280px, 100vw)"
      :closable="!saving" :keyboard="!saving" :mask-closable="!saving && drawer !== 'edit'" @close="requestClose">
      <a-alert v-if="drawerError" :message="drawerError" type="warning" show-icon class="section" />
      <a-spin :spinning="drawerBusy || saving">
        <template v-if="drawer === 'policy' || drawer === 'details' || drawer === 'edit'">
          <a-space v-if="drawer === 'policy' && activePolicy" wrap class="section">
            <a-tag>{{ activePolicy.confirmed ? '已确认' : '解析初版' }}</a-tag>{{ activePolicy.airline || '—' }} · {{ activePolicy.period || '—' }}
            <a-button :href="'/api/v1/airline-rebates/policies/' + encodeURIComponent(activePolicy.id) + '/original'">下载原件</a-button>
            <a-button v-if="canManage && activePolicy.confirmed && !drawerBusy && !drawerError" type="primary"
              @click="router.push({ name: 'airline-rebate-tasks', query: { policy: activePolicy.id } })">去任务管理建档</a-button>
          </a-space>
          <a-space v-if="task && drawer !== 'policy'" wrap class="section">
            <strong class="task-full-name">{{ task.name }}</strong>
            <span>{{ task.airline }} · {{ task.period }}</span><span>负责人 {{ task.owner || '—' }}</span><span>政策文件 {{ task.policyName }}</span>
            <a-select v-if="drawer === 'details'" v-model:value="selectedVersion" aria-label="规则版本"
              :options="versions.map(item => ({ value: item.version, label: 'V' + item.version + (item === currentVersion ? ' · 当前' : ' · 历史') }))" />
            <a-tag v-else-if="currentVersion">基于 V{{ currentVersion.version }} 编辑</a-tag>
          </a-space>
          <p v-if="drawer === 'details' && viewedVersion" class="muted section">{{ formatDateTimeDisplay(viewedVersion.savedAt) }} {{ viewedVersion.reason }}</p>
          <a-empty v-if="!drawerBusy && !drawerError && !ruleGroups.length" description="暂无规则" />
          <section v-if="drawer !== 'edit' && rateMatrix.length" class="section rule-group">
            <h3>航线奖励费率 <small class="muted">· 第 2 页 · 累计收入单位为万 HKD</small></h3>
            <a-table :data-source="rateMatrix" row-key="id" :pagination="false" size="small" :scroll="{ x: 780 }">
              <a-table-column title="累计收入档位" data-index="threshold" />
              <a-table-column title="舱位组" :width="190">
                <template #default="{ record }">{{ record.cabin }}<div class="muted">{{ displayValue(record.codes) }}</div></template>
              </a-table-column>
              <template #expandedRowRender="{ record }"><p v-if="record.sourceText" class="muted">{{ record.sourceText }}</p></template>
              <a-table-column v-for="(label, index) in rebateRouteLabels" :key="label" :title="label">
                <template #default="{ record }">{{ record.rates[index] == null ? '—' : record.rates[index] + '%' }}</template>
              </a-table-column>
            </a-table>
          </section>
          <section v-for="group in ruleGroups.filter(item => drawer === 'edit' || !item.id.startsWith('tier-'))" :key="group.id" class="section rule-group">
            <h3>{{ group.name }} <small v-if="group.sourcePage" class="muted">· {{ group.sourcePage }}</small></h3>
            <a-table :data-source="group.conditions" row-key="id" :pagination="false" size="small" :scroll="{ x: 845 }">
              <a-table-column title="字段" data-index="fieldLabel" :width="155" />
              <a-table-column title="运算符" :width="145">
                <template #default="{ record }">
                  <a-select v-if="drawer === 'edit'" v-model:value="record.operator" :options="operators" class="operator" :aria-label="record.fieldLabel + '运算符'" />
                  <span v-else>{{ operatorLabel(record.operator) }}</span>
                </template>
              </a-table-column>
              <a-table-column title="值" :width="235">
                <template #default="{ record }">
                  <a-input v-if="drawer === 'edit'" :default-value="displayValue(record.value)" :aria-label="record.fieldLabel + '规则值'" @change="(event: Event) => changeValue(record, (event.target as HTMLInputElement).value)" />
                  <template v-else>{{ displayValue(record.value) }}<details v-if="record.sourceText" class="muted"><summary>查看合同原文</summary>{{ record.sourceText }}</details><div v-if="drawer === 'details' && preceding(group, record)" class="muted">上版 {{ preceding(group, record) }}</div></template>
                </template>
              </a-table-column>
              <a-table-column title="Hive 字段及口径" :width="310">
                <template #default="{ record }">{{ formatHiveMapping(record.mapping) }}</template>
              </a-table-column>
            </a-table>
          </section>
          <a-space v-if="drawer === 'policy' && activePolicy && !activePolicy.confirmed && ruleGroups.length && canManage" wrap>
            <a-checkbox v-model:checked="confirmedCheck">已核对合同原文、费率及宽表字段映射</a-checkbox>
            <a-button type="primary" :loading="saving" :disabled="!confirmedCheck" @click="confirmPolicy">确认并前往任务管理</a-button>
          </a-space>
          <a-form v-if="drawer === 'edit' && currentVersion" layout="vertical">
            <a-form-item label="修改说明" required><a-input v-model:value="reason" /></a-form-item>
            <a-button type="primary" :loading="saving" :disabled="!hasRuleChanges || !validDraft || !reason.trim()" @click="save">保存为 V{{ currentVersion.version + 1 }}</a-button>
          </a-form>
        </template>

        <template v-else-if="drawer === 'analysis'">
          <template v-if="day">
            <a-space wrap class="section">
              <a-button @click="backToProgress">返回逐日数据</a-button>
              <a-breadcrumb><a-breadcrumb-item>分析此项</a-breadcrumb-item><a-breadcrumb-item>{{ routeScope?.category.name }}</a-breadcrumb-item><a-breadcrumb-item>{{ day.date }}</a-breadcrumb-item></a-breadcrumb>
              <a-button :loading="exporting" :disabled="!day.records" @click="exportRoute(day.date)">导出当日全部数据</a-button>
              <a-input-search v-model:value="detailQuery" aria-label="按订单号或票号查找当日明细" placeholder="订单号或票号（完全匹配）"
                :maxlength="80" allow-clear style="width: 260px" @search="day && showDay(day)" />
            </a-space>
            <a-table :data-source="detailRows" :columns="detailColumns" :pagination="false" row-key="id" :scroll="{ x: 1800 }" size="small" sticky>
              <template #expandedRowRender="{ record }">
                <a-list v-if="record.segmentDecisions?.length" :data-source="record.segmentDecisions" size="small">
                  <template #renderItem="{ item }"><a-list-item>
                    <a-space wrap>{{ item.route }} <span>{{ item.date }}</span><span>{{ item.cabin }} 舱</span>
                      <span>销售航司 {{ item.marketingAirline }}</span><a-tag>{{ item.result }}</a-tag>
                    </a-space>
                  </a-list-item></template>
                </a-list>
              </template>
              <template #emptyText><a-empty :description="drawerError ? '明细暂不可用' : '暂无订单明细'" /></template>
              <template #bodyCell="{ column, record }">
                <span v-if="column.key === 'segmentDates'">{{ segmentField(record, 'date') }}</span>
                <span v-else-if="column.key === 'segmentCabins'">{{ segmentField(record, 'cabin') }}</span>
                <span v-else-if="column.key === 'segmentCarriers'">{{ segmentField(record, 'marketingAirline') }}</span>
                <span v-else-if="column.key === 'ticketFare'">{{ money(record.ticketFare) }}</span>
                <span v-else-if="column.key === 'amount'">{{ money(record.eligibleAmount) }}</span>
                <span v-else-if="column.key === 'rate'">{{ percent(record.ratePercent) }}</span>
                <span v-else-if="column.key === 'reward'">{{ money(record.estimatedReward) }}</span>
                <span v-else-if="column.key === 'orderReward'">{{ money(record.orderEstimatedReward) }}</span>
              </template>
            </a-table>
            <a-pagination v-if="detailTotal > 25" class="pagination" :current="detailPage" :page-size="25" :total="detailTotal" :show-size-changer="false" @change="(page: number) => day && showDay(day, page)" />
          </template>
          <template v-else-if="routeScope">
            <a-space wrap class="section">
              <a-button @click="backToProgress">返回航线类型</a-button>
              <strong>{{ routeScope.category.name }}</strong>
              <a-button type="primary" :loading="exporting" :disabled="drawerBusy || !!drawerError || !routeDays.length"
                @click="exportRoute()">导出该类型全期数据</a-button>
            </a-space>
            <p class="muted section">计量归属日为符合条件的最晚航段计划起飞日。每日预计后返按本批费率计算。</p>
            <a-table :data-source="routeDays" row-key="id" size="small" :scroll="{ x: 700 }"
              :pagination="{ ...taskPagination, current: dailyPage, onChange: (page: number) => dailyPage = page }">
              <a-table-column title="计量归属日" data-index="date" :width="128" />
              <a-table-column title="计量记录数" data-index="records" align="right" :width="120" />
              <a-table-column title="当日计量（试算）" align="right" :width="160">
                <template #default="{ record }">{{ money(record.measuredAmount, task?.currency) }}</template>
              </a-table-column>
              <a-table-column title="预计后返（本批费率）" align="right" :width="160">
                <template #default="{ record }">{{ money(record.estimatedReward, task?.currency) }}</template>
              </a-table-column>
              <a-table-column title="操作" :width="132">
                <template #default="{ record }">
                  <a-button type="link" size="small" :disabled="!record.records" @click="showDay(record)">查看明细</a-button>
                </template>
              </a-table-column>
              <template #emptyText><a-empty :description="drawerError ? '逐日数据暂不可用' : '暂无逐日数据'" /></template>
            </a-table>
          </template>
          <template v-else-if="progress">
            <a-space wrap class="section">
              <a-button v-if="canManage" type="primary" :loading="runningTrial" @click="runTrial">运行 Hive 试算</a-button>
              <a-tag v-if="progress.tier">{{ progress.tier }} · 代理口径</a-tag>
            </a-space>
            <a-alert v-if="progress.dataNote" type="info" :message="progress.dataNote" show-icon class="section" />
            <a-alert v-if="progress.status === 'failed'" type="warning" :message="progress.errorMessage || '最近一次更新失败。'" show-icon class="section" />
            <div class="metrics section">
              <Statistic title="首档门槛（严格大于）" :value="money(progress.target, task?.currency)" />
              <Statistic title="累计计量（试算）" :value="money(progress.actual, task?.currency)" />
              <Statistic title="首档门槛进度" :value="percent(progress.completionRate)" />
              <Statistic title="预计后返（试算）" :value="money(progress.estimatedReward, task?.currency)" />
              <Statistic v-if="progress.otherOriginReward != null" title="非港澳始发（单列）" :value="money(progress.otherOriginReward, task?.currency)" />
            </div>
            <a-table v-if="progress.categories?.length" class="section" :data-source="progress.categories" row-key="id"
              :pagination="false" size="small" :scroll="{ x: 640 }">
              <a-table-column title="航线类型" data-index="name" />
              <a-table-column title="计量记录数" data-index="records" align="right" />
              <a-table-column title="累计计量（试算）" align="right">
                <template #default="{ record }">{{ money(record.measuredAmount, task?.currency) }}</template>
              </a-table-column>
              <a-table-column title="预计后返（试算）" align="right">
                <template #default="{ record }">{{ money(record.estimatedReward, task?.currency) }}</template>
              </a-table-column>
              <a-table-column title="操作" :width="136">
                <template #default="{ record }">
                  <a-button type="link" size="small" :disabled="runningTrial || !progress.runId" @click="openRouteCategory(record)">查看逐日数据</a-button>
                </template>
              </a-table-column>
            </a-table>
            <a-descriptions size="small" bordered :column="{ xs: 1, sm: 2 }" class="section">
              <a-descriptions-item label="更新状态">
                <a-tag :color="statusColors[progress.status]">{{ statusText[progress.status] }}</a-tag>
                <span v-if="progress.status === 'failed'">{{ progress.version != null ? '当前展示最近成功快照' : '暂无成功快照' }}</span>
              </a-descriptions-item>
              <a-descriptions-item label="最晚计划起飞日">{{ progress.dataAsOf || '—' }}</a-descriptions-item>
              <a-descriptions-item label="快照更新时间">{{ formatDateTimeDisplay(progress.refreshedAt) }} {{ progress.refreshMode ? refreshModes[progress.refreshMode] : '' }}</a-descriptions-item>
              <a-descriptions-item label="试算规则版本">{{ progress.version == null ? '—' : 'V' + progress.version }}</a-descriptions-item>
              <a-descriptions-item label="试算源记录数">{{ progress.sourceRows == null ? '—' : number(progress.sourceRows) + ' 条' }}</a-descriptions-item>
            </a-descriptions>
          </template>
          <a-empty v-else-if="!drawerBusy && !drawerError" description="暂无任务进度" />
        </template>
      </a-spin>
    </a-drawer>
  </div>
</template>

<style scoped>
.section { margin-bottom: 16px; }
.muted { color: #566477; font-size: 13px; overflow-wrap: anywhere; }
.task-card { min-width: 0; }
.task-card :deep(.ant-card-body) { padding: 0 16px; }
.two-lines { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.task-name { height: auto; max-width: 100%; padding: 0; text-align: left; white-space: normal; overflow-wrap: anywhere; }
.task-full-name { overflow-wrap: anywhere; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.metrics :deep(.ant-statistic) { padding: 12px; border: 1px solid #e4e9ef; border-radius: 8px; background: #f6f8fc; }
.operator { width: 100%; }
.pagination { margin-top: 16px; text-align: right; }
.rule-group h3 { margin: 0 0 8px; }
:deep(.ant-table) { font-variant-numeric: tabular-nums; }
</style>
