<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Statistic } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import { ApiError } from '@/api/http'
import {
  airlineRebates, type RebateCondition, type RebateDailyPoint, type RebateDetailRow,
  type RebatePolicy, type RebateNumber, type RebateProgress, type RebateRule, type RebateTask, type RebateVersion,
} from '@/api/airlineRebates'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const isPolicies = computed(() => route.name === 'airline-rebate-policies')
const confirmedCheck = ref(false)
const runningTrial = ref(false)
const canManage = computed(() => Boolean(auth.user?.isAdmin || auth.user?.permissions?.includes('airline_rebates.manage')))
const policies = ref<RebatePolicy[]>([])
const tasks = ref<RebateTask[]>([])
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
const progress = ref<RebateProgress>()
const day = ref<RebateDailyPoint>()
const detailRows = ref<RebateDetailRow[]>([])
const detailPage = ref(1)
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
  const label = drawer.value === 'analysis' ? (day.value ? '每日明细' : '分析此项') : drawer.value === 'edit' ? '编辑规则' : '任务详情'
  return label + ' · ' + (task.value?.name ?? '')
})
const policyColumns = [
  { title: '文件', dataIndex: 'name', width: 310 }, { title: '航司', dataIndex: 'airline', width: 105 },
  { title: '政策期', dataIndex: 'period', width: 195 }, { title: '解析状态', key: 'status', width: 160 },
  { title: '操作', key: 'action', width: 140 },
]
const taskColumns = [
  { title: '任务 / 航司', key: 'name', width: 220 }, { title: '政策期', dataIndex: 'period', width: 170 },
  { title: '负责人', dataIndex: 'owner', width: 100 }, { title: '目标 / 累计完成', key: 'progress', width: 210 },
  { title: '数据截至', key: 'asOf', width: 130 }, { title: '操作', key: 'action', width: 240 },
]
const detailColumns = [
  { title: '订单号', dataIndex: 'orderNo', width: 180 }, { title: '航程', dataIndex: 'route', width: 170 },
  { title: '计量票面价（试算）', key: 'amount', width: 150, align: 'right' as const }, { title: '匹配结果', dataIndex: 'result', width: 230 },
]
const statusText = { pending: '待产出', ready: '成功', failed: '失败' }
const operators = [['eq', '等于'], ['in', '属于'], ['not_in', '排除'], ['gte', '大于等于'], ['gt', '大于'], ['lte', '小于等于'], ['review', '待确认']]
  .map(([value, label]) => ({ value, label }))
const number = (value: number | string) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const money = (value: RebateNumber, currency = '') => value == null ? '—' : [currency, number(value)].filter(Boolean).join(' ')
const percent = (value: RebateNumber) => value == null ? '—' : number(value) + '%'
const displayValue = (value: RebateCondition['value']) => Array.isArray(value) ? value.join(', ') : String(value)
const rateMatrix = computed(() => ruleGroups.value.filter(group => group.id.startsWith('tier-')).flatMap(group => {
  const value = (id: string) => group.conditions.find(condition => condition.id === id)?.value
  const upper = value('maximum')
  const lower = Number(value('minimum')) / 10_000
  const threshold = upper ? `${lower} < T ≤ ${Number(upper) / 10_000}` : `T > ${lower}`
  return ['group_a', 'group_b'].map((id, index) => ({
    id: group.id + '-' + id, threshold, cabin: index === 0 ? 'A 组' : 'B 组',
    rates: (value(id) as string[] | undefined) ?? [],
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
  day.value = undefined
  drawerBusy.value = false
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
    if (activePolicy.value?.id === item.id) activePolicy.value = confirmed
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
    void load()
  } catch (error) {
    if (drawer.value === 'analysis' && task.value?.id === item.id) drawerError.value = explain(error)
  } finally { runningTrial.value = false }
}
function openCreate() {
  if (!canManage.value) return
  activePolicy.value = undefined
  taskName.value = ''
  owner.value = auth.user?.displayName || auth.user?.username || ''
  drawer.value = 'create'
  void loadDrawer(async signal => {
    const rows = await airlineRebates.listPolicies(signal)
    if (signal.aborted) return
    policies.value = rows
    const policyId = route.query.policy
    const policy = readyPolicies.value.find(item => item.id === policyId)
    if (policy) selectPolicy(policy.id)
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
  if (!activePolicy.value || !canManage.value || saving.value || !taskName.value.trim() || !owner.value.trim()) return
  saving.value = true
  drawerError.value = ''
  try {
    const created = await airlineRebates.createTask({ policyId: activePolicy.value.id, name: taskName.value.trim(), owner: owner.value.trim() })
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
function showDay(point: RebateDailyPoint, page = 1) {
  const item = task.value
  if (!item) return
  day.value = point
  detailPage.value = page
  detailRows.value = []
  detailTotal.value = 0
  void loadDrawer(async signal => {
    const rows = await airlineRebates.details(item.id, point.id, page, signal)
    if (!signal.aborted) { detailRows.value = rows.items; detailTotal.value = rows.total }
  })
}
function backToProgress() {
  drawerRequest?.abort()
  day.value = undefined
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
        <a-button v-if="!isPolicies && canManage" type="primary" :disabled="loading || !!listError" @click="openCreate">新建任务</a-button>
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
    <a-card v-else title="航司后返任务" class="section">
      <a-table :data-source="tasks" :columns="taskColumns" :loading="loading" row-key="id" :scroll="{ x: 1070 }">
        <template #emptyText><a-empty :description="listError ? '任务暂不可用' : '暂无后返任务'" /></template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'"><strong>{{ record.name }}</strong><div class="muted">{{ record.airline }} · {{ record.id }}</div></template>
          <template v-else-if="column.key === 'progress'">
            <div>{{ money(record.target, record.currency) }} / {{ money(record.actual, record.currency) }}</div>
            <span class="muted">{{ record.completionRate == null ? '待产出' : '完成率 ' + percent(record.completionRate) }}</span>
          </template>
          <span v-else-if="column.key === 'asOf'">{{ record.dataAsOf || '—' }}</span>
          <a-space v-else-if="column.key === 'action'" :size="0" wrap>
            <a-button type="link" @click="openTask(record, 'details')">详情</a-button>
            <a-button type="link" @click="openTask(record, 'analysis')">分析此项</a-button>
            <a-button v-if="canManage && record.editable !== false" type="link" @click="openTask(record, 'edit')">编辑规则</a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>

    <a-drawer :open="!!drawer" :title="drawerTitle" placement="right"
      :width="drawer === 'create' ? 'min(560px, 100vw)' : 'min(1280px, 100vw)'"
      :closable="!saving" :keyboard="!saving" :mask-closable="!saving && drawer !== 'edit'" @close="closeDrawer">
      <a-alert v-if="drawerError" :message="drawerError" type="warning" show-icon class="section" />
      <a-spin :spinning="drawerBusy || saving">
        <a-form v-if="drawer === 'create'" layout="vertical">
          <a-form-item label="解析文件" required>
            <a-select :value="activePolicy?.id" :options="readyPolicies.map(item => ({ value: item.id, label: item.name }))" placeholder="选择已解析政策" @change="(value: string) => selectPolicy(value)" />
          </a-form-item>
          <a-form-item label="任务名称" required><a-input v-model:value="taskName" /></a-form-item>
          <a-form-item label="负责人" required><a-input v-model:value="owner" /></a-form-item>
          <a-button type="primary" :disabled="drawerBusy || saving || !activePolicy || !taskName.trim() || !owner.trim()" @click="create">确认建档</a-button>
        </a-form>

        <template v-else-if="drawer === 'policy' || drawer === 'details' || drawer === 'edit'">
          <a-space v-if="drawer === 'policy' && activePolicy" wrap class="section">
            <a-tag>{{ activePolicy.confirmed ? '已确认' : '解析初版' }}</a-tag>{{ activePolicy.airline || '—' }} · {{ activePolicy.period || '—' }}
            <a-button :href="'/api/v1/airline-rebates/policies/' + encodeURIComponent(activePolicy.id) + '/original'">下载原件</a-button>
            <a-button v-if="canManage && activePolicy.confirmed && !drawerBusy && !drawerError" type="primary"
              @click="router.push({ name: 'airline-rebate-tasks', query: { policy: activePolicy.id } })">去任务管理建档</a-button>
          </a-space>
          <a-space v-if="task && drawer !== 'policy'" wrap class="section">
            <span>{{ task.airline }} · {{ task.period }}</span><span>来源 {{ task.policyName }}</span>
            <a-select v-if="drawer === 'details'" v-model:value="selectedVersion" aria-label="规则版本"
              :options="versions.map(item => ({ value: item.version, label: 'V' + item.version + (item === currentVersion ? ' · 当前' : ' · 历史') }))" />
            <a-tag v-else-if="currentVersion">基于 V{{ currentVersion.version }} 编辑</a-tag>
          </a-space>
          <p v-if="drawer === 'details' && viewedVersion" class="muted section">{{ viewedVersion.savedAt }} {{ viewedVersion.reason }}</p>
          <a-empty v-if="!drawerBusy && !drawerError && !ruleGroups.length" description="暂无规则" />
          <section v-if="drawer !== 'edit' && rateMatrix.length" class="section rule-group">
            <h3>航线奖励费率 <small class="muted">· 第 2 页 · 累计收入单位为万 HKD</small></h3>
            <a-table :data-source="rateMatrix" row-key="id" :pagination="false" size="small" :scroll="{ x: 780 }">
              <a-table-column title="累计收入档位" data-index="threshold" />
              <a-table-column title="舱位组" data-index="cabin" />
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
                  <template v-else>{{ displayValue(record.value) }}<div v-if="drawer === 'details' && preceding(group, record)" class="muted">上版 {{ preceding(group, record) }}</div></template>
                </template>
              </a-table-column>
              <a-table-column title="Hive 字段及口径" data-index="mapping" :width="310" />
            </a-table>
          </section>
          <a-space v-if="drawer === 'policy' && activePolicy && !activePolicy.confirmed && ruleGroups.length && canManage" wrap>
            <a-checkbox v-model:checked="confirmedCheck">已核对 PDF 原文与规则</a-checkbox>
            <a-button type="primary" :loading="saving" :disabled="!confirmedCheck" @click="confirmPolicy">确认解析结果</a-button>
          </a-space>
          <a-form v-if="drawer === 'edit' && currentVersion" layout="vertical">
            <a-form-item label="修改说明" required><a-input v-model:value="reason" /></a-form-item>
            <a-button type="primary" :loading="saving" :disabled="!hasRuleChanges || !validDraft || !reason.trim()" @click="save">保存为 V{{ currentVersion.version + 1 }}</a-button>
          </a-form>
        </template>

        <template v-else-if="drawer === 'analysis'">
          <template v-if="day">
            <a-space wrap class="section">
              <a-button @click="backToProgress">返回任务进度</a-button>
              <a-breadcrumb><a-breadcrumb-item>分析此项</a-breadcrumb-item><a-breadcrumb-item>{{ day.date }}</a-breadcrumb-item><a-breadcrumb-item>每日明细</a-breadcrumb-item></a-breadcrumb>
              <a-tag>规则 V{{ day.version }}</a-tag>
            </a-space>
            <a-table :data-source="detailRows" :columns="detailColumns" :pagination="false" row-key="id" :scroll="{ x: 1320 }">
              <template #expandedRowRender="{ record }">
                <a-descriptions size="small" :column="3">
                  <a-descriptions-item label="票号">{{ record.ticketNo || '—' }}</a-descriptions-item>
                  <a-descriptions-item label="整票票面价">{{ money(record.ticketFare, record.currency) }}</a-descriptions-item>
                  <a-descriptions-item label="批次费率">{{ record.ratePercent == null ? '—' : record.ratePercent + '%' }}</a-descriptions-item>
                  <a-descriptions-item label="本票预计后返">{{ money(record.estimatedReward, record.currency) }}</a-descriptions-item>
                  <a-descriptions-item label="订单已算后返小计">{{ money(record.orderEstimatedReward, record.currency) }}</a-descriptions-item>
                </a-descriptions>
                <a-list v-if="record.segmentDecisions?.length" :data-source="record.segmentDecisions" size="small">
                  <template #renderItem="{ item }"><a-list-item>
                    <a-space wrap>{{ item.route }} <span>{{ item.date }}</span><span>{{ item.cabin }} 舱</span>
                      <span>销售航司 {{ item.marketingAirline }}</span><a-tag>{{ item.result }}</a-tag>
                    </a-space>
                  </a-list-item></template>
                </a-list>
              </template>
              <template #emptyText><a-empty :description="drawerError ? '明细暂不可用' : '暂无订单明细'" /></template>
              <template #bodyCell="{ column, record }"><span v-if="column.key === 'amount'">{{ money(record.eligibleAmount, task?.currency) }}</span></template>
            </a-table>
            <a-pagination v-if="detailTotal > 25" class="pagination" :current="detailPage" :page-size="25" :total="detailTotal" :show-size-changer="false" @change="(page: number) => day && showDay(day, page)" />
          </template>
          <template v-else-if="progress">
            <a-space wrap class="section">
              <a-button v-if="canManage" type="primary" :loading="runningTrial" @click="runTrial">运行 Hive 试算</a-button>
              <a-tag v-if="progress.tier">{{ progress.tier }} · 代理口径</a-tag>
              <a-tag v-if="progress.pendingCount" color="orange">{{ progress.pendingCount }} 条待核</a-tag>
            </a-space>
            <a-alert v-if="progress.dataNote" type="info" :message="progress.dataNote" show-icon class="section" />
            <a-alert v-if="progress.status === 'failed'" type="warning" :message="progress.errorMessage || '最近一次更新失败。'" show-icon class="section" />
            <div class="metrics section">
              <Statistic title="首档门槛（严格大于）" :value="money(progress.target, task?.currency)" />
              <Statistic title="累计计量（试算）" :value="money(progress.actual, task?.currency)" />
              <Statistic title="完成率" :value="percent(progress.completionRate)" />
              <Statistic title="预计后返（试算）" :value="money(progress.estimatedReward, task?.currency)" />
              <Statistic v-if="progress.otherOriginReward != null" title="非港澳始发（单列）" :value="money(progress.otherOriginReward, task?.currency)" />
            </div>
            <a-table v-if="progress.categories?.length" class="section" :data-source="progress.categories" row-key="id"
              :pagination="false" size="small" :scroll="{ x: 640 }">
              <a-table-column title="航线类型" data-index="name" />
              <a-table-column title="计量记录数" data-index="records" />
              <a-table-column title="累计计量（试算）">
                <template #default="{ record }">{{ money(record.measuredAmount, task?.currency) }}</template>
              </a-table-column>
              <a-table-column title="预计后返">
                <template #default="{ record }">{{ money(record.estimatedReward, task?.currency) }}</template>
              </a-table-column>
            </a-table>
            <p class="muted section">最近更新 {{ statusText[progress.status] }} · 数据截至 {{ progress.dataAsOf || '—' }} · {{ progress.version == null ? '规则版本待产出' : '规则 V' + progress.version }}</p>
            <a-list header="每日累计进度" :data-source="progress.daily">
              <template #renderItem="{ item }"><a-list-item>
                <a-space wrap>{{ item.date }} <strong>{{ money(item.actual, task?.currency) }}</strong><a-tag>{{ percent(item.completionRate) }}</a-tag><span class="muted">V{{ item.version }}</span></a-space>
                <a-button type="link" @click="showDay(item)">查看当日明细</a-button>
              </a-list-item></template>
              <template #emptyText><a-empty description="暂无每日进度" /></template>
            </a-list>
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
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.metrics :deep(.ant-statistic) { padding: 12px; border: 1px solid #e4e9ef; border-radius: 8px; background: #f6f8fc; }
.operator { width: 100%; }
.pagination { margin-top: 16px; text-align: right; }
.rule-group h3 { margin: 0 0 8px; }
:deep(.ant-table) { font-variant-numeric: tabular-nums; }
</style>
