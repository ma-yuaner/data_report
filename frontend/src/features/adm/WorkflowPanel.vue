<template>
  <section class="workflow-panel">
    <template v-if="!record">
      <FilterPanel stacked :instant="false" :show-reset="false" :loading="loading">
        <template #header
          ><h2>站内待办与风险观察</h2>
          <span>当前状态快照，不是人员绩效榜</span></template
        >
        <label><span>数据范围</span><a-select v-model:value="scope" :options="scopes" /></label>
        <label><span>任务环节</span><a-select v-model:value="kind" :options="taskKinds" /></label>
        <template #actions
          ><a-button type="primary" :loading="loading" @click="query">查询 / 刷新待办</a-button></template
        >
          <template #footer
          >无任务不代表已达标；缺期限单列，不视为按时。第一版不发送站内、企业微信或其他主动通知，待办仅保留在我的工作台。</template
        >
      </FilterPanel>
      <a-alert v-if="overviewError" type="error" :message="overviewError" show-icon />
      <template v-if="overview">
        <p class="adm-muted">
          {{ overview.businessDate }} · 生成时间 {{ formatDateTimeDisplay(overview.generatedAt) }} ·
          {{ appliedScopeLabel }}；汇总为全部获授权任务，不是当前页。
        </p>
        <div class="adm-metrics">
          <div v-for="metric in metrics" :key="metric.key">
            <span>{{ metric.label }}</span
            ><strong>{{ overview.summary[metric.key] }}</strong>
          </div>
        </div>
        <a-table
          row-key="id"
          :columns="taskColumns"
          :data-source="overview.items"
          :loading="loading"
          :pagination="false"
          :scroll="{ x: 1050, y: 320 }"
          size="small"
        >
          <template #bodyCell="{ column, record: task }">
            <template v-if="column.key === 'admNo'"
              ><router-link v-if="!task.coordinationOnly" :to="taskLink(task)">{{ task.admNo }}</router-link>
              <span v-else>{{ task.admNo }}（协调摘要，无明细权限）</span></template
            >
            <template v-else-if="column.key === 'owner'">{{ task.ownerName || '待指定' }}</template>
            <template v-else-if="column.key === 'status'"
              >{{ label(task.status) }}<a-tag v-if="task.paused">挂起，风险仍保留</a-tag></template
            >
            <template v-else-if="column.key === 'due'"
              ><span>{{ formatDateTimeDisplay(task.dueAt || '未设置期限') }}</span
              ><a-tag v-if="task.overdue" color="red">已超期</a-tag></template
            >
          </template>
          <template #emptyText><a-empty description="当前范围没有待办，不代表业务已达标" /></template>
        </a-table>
        <div class="adm-pagination">
          <a-pagination :current="page" :page-size="20" :total="overview.pagination.total" @change="changePage" />
        </div>
        <details>
          <summary>人员当前负荷（按姓名排序，非排名）</summary>
          <a-table
            :row-key="personKey"
            :columns="peopleColumns"
            :data-source="overview.people"
            :pagination="{ pageSize: 10 }"
            :scroll="{ x: 600 }"
            size="small"
          />
        </details>
        <p v-for="limitation in overview.limitations" :key="limitation" class="adm-muted">{{ limitation }}</p>
      </template>
    </template>
    <template v-else>
      <div class="adm-toolbar">
        <strong>责任与流转</strong
        ><a-button v-if="allowed(record, 'coordinator')" :disabled="saving" @click="openAction('coordinator')"
          >调整主单协调人</a-button
        >
      </div>
      <p>
        主单协调人：{{ record.coordinatorName || record.coordinatorId || '待指定'
        }}<a-tag v-if="record.legacyCoordination">旧单创建者兼协调人</a-tag>
      </p>
      <p class="adm-muted">整张ADM任一时刻只有一名当前承办人；需要他人处理时必须整单转派。截止时间不因转派重置。</p>
      <template v-if="line">
        <a-descriptions bordered size="small" :column="{ xs: 1, sm: 2, lg: 3 }">
          <a-descriptions-item label="当前承办人">{{ record.ownerName || record.ownerId || '未分配' }}</a-descriptions-item>
          <a-descriptions-item label="审核人">{{ record.coordinatorName || record.coordinatorId || 'ADM负责人' }}</a-descriptions-item>
          <a-descriptions-item v-for="field in deadlineFields" :key="field.key" :label="field.label">{{
            displayDateTimeField(line.workflow?.[field.key] || '未设置', field.key)
          }}</a-descriptions-item>
          <a-descriptions-item label="等待对象">{{ line.workflow?.waitingFor || '未登记等待' }}</a-descriptions-item>
          <a-descriptions-item label="下次跟进">{{ formatDateTimeDisplay(line.workflow?.nextFollowUpAt || '未设置') }}</a-descriptions-item>
          <a-descriptions-item label="等待原因" :span="3"
            ><span class="adm-prose">{{ line.workflow?.waitingReason || '—' }}</span></a-descriptions-item
          >
        </a-descriptions>
        <div class="adm-toolbar">
          <a-button v-for="action in workflowActions" :key="action" :disabled="saving" @click="openAction(action)">{{
            actionNames[action]
          }}</a-button>
        </div>
        <a-alert
          v-if="record.handover?.status === 'PENDING'"
          type="warning"
          show-icon
          :message="`待整单转派：${record.handover.fromName || '未分配'} → ${record.handover.toName}；接收前仍由原承办人负责。`"
        />
        <div v-if="record.handover" class="adm-record">
          <strong>最近整单转派 · {{ handoverLabels[record.handover.status] || record.handover.status }}</strong>
          <p>{{ record.handover.fromName || '未分配' }} → {{ record.handover.toName }} · {{ formatDateTimeDisplay(record.handover.requestedAt) }}</p>
          <p class="adm-prose">原因：{{ record.handover.reason }}<br />已做 / 待做 / 风险：{{ record.handover.summary }}</p>
          <p v-if="record.handover.responseReason" class="adm-prose">回应：{{ record.handover.responseReason }}</p>
        </div>
        <details v-if="record.assignmentSegments?.length">
          <summary>整单承办记录</summary>
          <a-table
            row-key="id"
            :columns="segmentColumns"
            :data-source="record.assignmentSegments"
            :pagination="false"
            :scroll="{ x: 900 }"
            size="small"
          />
        </details>
        <details v-if="record.handoverHistory?.length">
          <summary>整单转派历史</summary>
          <div v-for="handover in record.handoverHistory" :key="handover.id" class="adm-record">
            <strong>{{ handoverLabels[handover.status] || handover.status }}</strong>
            <p>{{ handover.fromName || '未分配' }} → {{ handover.toName }} · {{ formatDateTimeDisplay(handover.requestedAt) }}</p>
            <p class="adm-prose">
              {{ handover.reason }}<br />{{ handover.summary }}<br />{{ handover.responseReason }}
            </p>
          </div>
        </details>
      </template>
      <p v-else class="adm-muted">选择任一订单查看节点期限；承办人与转派记录属于整张ADM。</p>
    </template>
    <FormDialog
      v-model:open="dialogOpen"
      :title="actionNames[action] || '流转操作'"
      :busy="saving"
      :dirty="dirty"
      :error="formError"
      :submit-disabled="versionConflict"
      @submit="saveAction"
    >
      <p v-if="action === 'plan'" class="adm-muted">
        仅更新本次期限；未确认的SLA不自动填入。审核人固定为本ADM负责人，不单独设置。
      </p>
      <p v-if="action.startsWith('transfer_')" class="adm-muted">
        接收前原责任保留；接受后切换承办和锁。外部截止与原有期限不重置。
      </p>
      <FormGrid>
        <label v-if="action === 'coordinator'"
          ><span>主单协调人 <span class="required">*</span></span
          ><AccountSelect v-model="draft.coordinatorId" :options="config?.people?.owner || []" :disabled="saving"
        /></label>
        <template v-if="action === 'plan'">
          <label v-for="field in deadlineFields" :key="field.key"
            ><span>{{ field.label }}（北京时间）</span
            ><DateField v-model="draft[field.key]" with-time :disabled="saving"
          /></label>
        </template>
        <label v-if="action === 'transfer_request'"
          ><span>转交接收人 <span class="required">*</span></span
          ><AccountSelect v-model="draft.ownerId" :options="handlePeople" :disabled="saving"
        /></label>
        <label v-if="action === 'transfer_request'" class="form-span"
          ><span>交接摘要 <span class="required">*</span></span
          ><a-textarea
            v-model:value="draft.summary"
            :rows="4"
            placeholder="已做事项、待办、证据位置及风险"
            :disabled="saving"
        /></label>
        <template v-if="action === 'follow_up'">
          <label
            ><span>等待对象</span
            ><a-input v-model:value="draft.waitingFor" :disabled="saving" placeholder="清空表示不再等待"
          /></label>
          <label
            ><span>下次跟进（北京时间）</span><DateField v-model="draft.nextFollowUpAt" with-time :disabled="saving"
          /></label>
          <label class="form-span"
            ><span>等待原因</span><a-textarea v-model:value="draft.waitingReason" :rows="3" :disabled="saving"
          /></label>
        </template>
        <label class="form-span"
          ><span>操作原因 / 交接回应 <span class="required">*</span></span
          ><a-textarea v-model:value="draft.reason" :rows="3" :disabled="saving"
        /></label>
      </FormGrid>
      <a-alert
        v-if="versionConflict"
        type="warning"
        show-icon
        message="草稿保留，但不可覆盖最新记录。请先刷新，再关闭并重新打开本操作核对后提交。"
      />
    </FormDialog>
  </section>
</template>

<script setup lang="ts">
import { formatDateTimeDisplay, displayDateTimeField } from '@/utils/dateTimeDisplay'

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import FilterPanel from '@/components/FilterPanel.vue'
import FormDialog from '@/components/FormDialog.vue'
import FormGrid from '@/components/FormGrid.vue'
import DateField from '@/components/DateField.vue'
import AccountSelect from '@/components/AccountSelect.vue'
import {
  admApi,
  allowed,
  errorText,
  label,
  type AdmCase,
  type AdmConfig,
  type AdmLine,
  type Fields,
  type WorkflowOverview,
  type WorkflowTask,
} from './api'
const props = withDefaults(
  defineProps<{ record?: AdmCase; line?: AdmLine | null; config?: AdmConfig | null; refreshKey?: number }>(),
  { record: undefined, line: null, config: null, refreshKey: 0 },
)
const emit = defineEmits<{ changed: [record: AdmCase] }>()
const auth = useAuthStore()
const permitted = (name: string) => Boolean(auth.user?.isAdmin || auth.user?.permissions.includes(`adm.${name}`))
const scopes = computed(() => [
  { value: 'mine', label: '我的待办' },
  ...(permitted('scope.team') ? [{ value: 'team', label: '管理团队' }] : []),
  ...(permitted('scope.all') ? [{ value: 'all', label: '全部' }] : []),
])
const scope = ref('mine'),
  kind = ref(''),
  page = ref(1),
  loading = ref(false),
  overviewError = ref(''),
  overview = ref<WorkflowOverview | null>(null)
let appliedScope = 'mine',
  appliedKind = ''
let request = 0
const appliedScopeLabel = computed(
  () => scopes.value.find((item) => item.value === overview.value?.scope)?.label || '我的待办',
)
const taskKinds = [
  { value: '', label: '全部环节' },
  ...Object.entries({
    ASSIGN_OPERATOR: '待分配整单承办人',
    CODE_PROCESSING: '待编码处理',
    DECISION: '待决定/修改',
    APPEAL: '申诉中',
    TRANSFER: '待整单转派确认',
    REVIEW: '待审核',
    COLLECTION: '待回款跟进',
    FOLLOW_UP: '待跟进',
  }).map(([value, text]) => ({ value, label: text })),
]
const metrics = [
  { key: 'tasks', label: '当前任务' },
  { key: 'overdue', label: '已超期' },
  { key: 'unassigned', label: '待指定人员' },
  { key: 'missingDeadline', label: '未设期限' },
  { key: 'waiting', label: '等待跟进' },
] as const
const taskColumns = [
  { title: 'ADM单号', key: 'admNo', width: 180 },
  { title: '任务', dataIndex: 'label', width: 160 },
  { title: '责任人', key: 'owner', width: 130 },
  { title: '状态', key: 'status', width: 170 },
  { title: '截止（北京时间）', key: 'due', width: 240 },
]
const peopleColumns = [
  { title: '人员', dataIndex: 'ownerName' },
  { title: '当前任务', dataIndex: 'tasks' },
  { title: '已超期', dataIndex: 'overdue' },
  { title: '未设期限', dataIndex: 'missingDeadline' },
]
const personKey = (person: { ownerId: string | null }) => person.ownerId || 'unassigned'
const taskLink = (task: WorkflowTask) =>
  `/adm/cases/${encodeURIComponent(task.caseId)}${task.lineId ? `?lineId=${encodeURIComponent(task.lineId)}` : ''}`
async function loadOverview() {
  if (props.record) return
  const seq = ++request
  loading.value = true
  overviewError.value = ''
  try {
    const result = await admApi.workflow({ scope: appliedScope, kind: appliedKind, page: page.value, pageSize: 20 })
    if (seq === request) overview.value = result
  } catch (cause) {
    if (seq === request) {
      overviewError.value = errorText(cause)
      overview.value = null
    }
  } finally {
    if (seq === request) loading.value = false
  }
}
function query() {
  page.value = 1
  appliedScope = scope.value
  appliedKind = kind.value
  overview.value = null
  void loadOverview()
}
function changePage(value: number) {
  page.value = value
  void loadOverview()
}
const deadlineFields = [
  { key: 'processingDueAt', label: '办理截止' },
  { key: 'reviewDueAt', label: '审核截止' },
  { key: 'collectionDueAt', label: '回款跟进截止' },
]
const actionNames: Record<string, string> = {
  coordinator: '调整协调人',
  plan: '设置人员与期限',
  follow_up: '登记等待与跟进',
  transfer_request: '发起整单转派',
  transfer_accept: '接受整单转派',
  transfer_reject: '驳回整单转派',
  transfer_cancel: '撤销整单转派',
}
const handoverLabels: Record<string, string> = {
  PENDING: '待确认',
  ACCEPTED: '已接受',
  REJECTED: '已驳回',
  CANCELLED: '已撤销',
}
const workflowActions = computed(() =>
  Object.keys(actionNames).filter((name) => name !== 'coordinator' && allowed(props.line || null, name)),
)
const handlePeople = computed(() =>
  (props.config?.people?.handle || props.config?.assignees || []).filter((person) => person.id !== props.record?.ownerId),
)
const segmentColumns = [
  { title: '承办人', dataIndex: 'ownerName', width: 130 },
  { title: '分配时间', dataIndex: 'assignedAt', width: 190, customRender: ({ text }: { text: unknown }) => formatDateTimeDisplay(text) },
  { title: '接单时间', dataIndex: 'acceptedAt', width: 190, customRender: ({ text }: { text: unknown }) => formatDateTimeDisplay(text) },
  { title: '结束时间', dataIndex: 'endedAt', width: 190, customRender: ({ text }: { text: unknown }) => formatDateTimeDisplay(text) },
  { title: '轮次', dataIndex: 'round', width: 70 },
  { title: '原因', dataIndex: 'reason', width: 240 },
]
const dialogOpen = ref(false),
  saving = ref(false),
  action = ref(''),
  draft = ref<Fields>({}),
  formError = ref(''),
  versionConflict = ref(false),
  baseline = ref('')
let actionCase = '',
  actionLine = '',
  version = 0
const dirty = computed(() => JSON.stringify(draft.value) !== baseline.value)
function openAction(name: string) {
  if (!props.record) return
  action.value = name
  actionCase = props.record.id
  actionLine = props.line?.id || ''
  version = props.record.version
  draft.value = { reason: '' }
  if (name === 'coordinator') draft.value.coordinatorId = props.record.coordinatorId || ''
  if (name === 'plan')
    for (const key of deadlineFields.map((field) => field.key))
      draft.value[key] = props.line?.workflow?.[key] || ''
  if (name === 'follow_up')
    for (const key of ['waitingFor', 'waitingReason', 'nextFollowUpAt'])
      draft.value[key] = props.line?.workflow?.[key] || ''
  baseline.value = JSON.stringify(draft.value)
  formError.value = ''
  versionConflict.value = false
  dialogOpen.value = true
}
async function saveAction() {
  if (saving.value || versionConflict.value) return
  if (!draft.value.reason?.trim()) {
    formError.value = '请填写操作原因 / 交接回应'
    return
  }
  if (action.value === 'coordinator' && !draft.value.coordinatorId) {
    formError.value = '请选择获授权协调人'
    return
  }
  if (action.value === 'transfer_request' && (!draft.value.ownerId || !draft.value.summary?.trim())) {
    formError.value = '请选择接收人并填写交接摘要'
    return
  }
  if (
    action.value === 'follow_up' &&
    draft.value.waitingFor?.trim() &&
    (!draft.value.waitingReason?.trim() || !draft.value.nextFollowUpAt)
  ) {
    formError.value = '登记等待时需要原因和下次跟进时间'
    return
  }
  saving.value = true
  formError.value = ''
  const caseId = actionCase
  try {
    const body = { ...draft.value, action: action.value, version }
    const result =
      action.value === 'coordinator'
        ? await admApi.action(caseId, body)
        : await admApi.lineAction(caseId, actionLine, body)
    if (props.record?.id !== caseId) return
    baseline.value = JSON.stringify(draft.value)
    dialogOpen.value = false
    message.success('流转操作已保存；站内待办已按新责任更新')
    emit('changed', result)
  } catch (cause) {
    if (props.record?.id === caseId) {
      formError.value = errorText(cause)
      versionConflict.value = (cause as { code?: string }).code === 'ADM_VERSION_CONFLICT'
    }
  } finally {
    saving.value = false
  }
}
watch(
  () => props.refreshKey,
  () => {
    if (!props.record) void loadOverview()
  },
)
watch(
  () => auth.user?.id,
  () => {
    request++
    overview.value = null
    dialogOpen.value = false
    draft.value = {}
    baseline.value = '{}'
    scope.value = 'mine'
    query()
  },
)
watch(
  () => props.record?.id,
  () => {
    dialogOpen.value = false
    draft.value = {}
    baseline.value = '{}'
    formError.value = ''
  },
)
if (!props.record) void loadOverview()
onBeforeUnmount(() => {
  request++
})
defineExpose({ hasUnsavedDraft: () => dialogOpen.value && dirty.value })
</script>

<style scoped>
.workflow-panel {
  min-width: 0;
  margin: 16px 0;
  padding: 16px;
  border: 1px solid #e4e9ef;
  background: #fff;
  border-radius: 10px;
}
.workflow-panel details {
  margin: 12px 0;
}
.workflow-panel summary {
  cursor: pointer;
  margin-bottom: 10px;
}
</style>
