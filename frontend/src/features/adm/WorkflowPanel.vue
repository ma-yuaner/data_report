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
          >无任务不代表已达标；缺期限单列，不视为按时。站外自动消息、历史日报与综合排名尚未接入。</template
        >
      </FilterPanel>
      <a-alert v-if="overviewError" type="error" :message="overviewError" show-icon />
      <template v-if="overview">
        <p class="adm-muted">
          {{ overview.businessDate }} · 生成时间 {{ overview.generatedAt }} ·
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
              ><span>{{ task.dueAt || '未设置期限' }}</span
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
      <p class="adm-muted">协调人与造成问题的实际责任人不同；截止时间不因转交重置。站内待办不等同于站外通知已发送。</p>
      <template v-if="line">
        <a-descriptions bordered size="small" :column="{ xs: 1, sm: 2, lg: 3 }">
          <a-descriptions-item label="当前承办">{{ line.ownerName || line.ownerId || '未分配' }}</a-descriptions-item>
          <a-descriptions-item label="审核人">{{
            line.workflow?.reviewerName || line.workflow?.reviewerId || '待指定（沿用获权审核角色）'
          }}</a-descriptions-item>
          <a-descriptions-item label="财务确认人">{{
            line.workflow?.financeOwnerName || line.workflow?.financeOwnerId || '待指定（沿用获权财务角色）'
          }}</a-descriptions-item>
          <a-descriptions-item v-for="field in deadlineFields" :key="field.key" :label="field.label">{{
            line.workflow?.[field.key] || '未设置'
          }}</a-descriptions-item>
          <a-descriptions-item label="等待对象">{{ line.workflow?.waitingFor || '未登记等待' }}</a-descriptions-item>
          <a-descriptions-item label="下次跟进">{{ line.workflow?.nextFollowUpAt || '未设置' }}</a-descriptions-item>
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
          v-if="line.handover?.status === 'PENDING'"
          type="warning"
          show-icon
          :message="`待交接：${line.handover.fromName || '未分配'} → ${line.handover.toName}；接收前原责任不变，接收人仅可查看交接内容。`"
        />
        <div v-if="line.handover" class="adm-record">
          <strong>最近交接 · {{ handoverLabels[line.handover.status] || line.handover.status }}</strong>
          <p>{{ line.handover.fromName || '未分配' }} → {{ line.handover.toName }} · {{ line.handover.requestedAt }}</p>
          <p class="adm-prose">原因：{{ line.handover.reason }}<br />已做 / 待做 / 风险：{{ line.handover.summary }}</p>
          <p v-if="line.handover.responseReason" class="adm-prose">回应：{{ line.handover.responseReason }}</p>
        </div>
        <details v-if="line.assignmentSegments?.length">
          <summary>分段责任与接单记录</summary>
          <a-table
            row-key="id"
            :columns="segmentColumns"
            :data-source="line.assignmentSegments"
            :pagination="false"
            :scroll="{ x: 900 }"
            size="small"
          />
        </details>
        <details v-if="line.handoverHistory?.length">
          <summary>交接历史</summary>
          <div v-for="handover in line.handoverHistory" :key="handover.id" class="adm-record">
            <strong>{{ handoverLabels[handover.status] || handover.status }}</strong>
            <p>{{ handover.fromName || '未分配' }} → {{ handover.toName }} · {{ handover.requestedAt }}</p>
            <p class="adm-prose">
              {{ handover.reason }}<br />{{ handover.summary }}<br />{{ handover.responseReason }}
            </p>
          </div>
        </details>
      </template>
      <p v-else class="adm-muted">选择订单明细，查看其计划、交接与分段责任。</p>
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
        仅更新本次字段；空值会清除原值。未确认的SLA不自动填入期限。审核人与承办人默认不可相同。
      </p>
      <p v-if="action.startsWith('transfer_')" class="adm-muted">
        接收前原责任保留；接受后切换承办和锁。外部截止与原有期限不重置。
      </p>
      <FormGrid>
        <label v-if="action === 'coordinator'"
          ><span>主单协调人 <span class="required">*</span></span
          ><AccountSelect v-model="draft.coordinatorId" :options="config?.people?.coordinate || []" :disabled="saving"
        /></label>
        <template v-if="action === 'plan'">
          <label
            ><span>审核人</span
            ><AccountSelect v-model="draft.reviewerId" :options="config?.people?.review || []" :disabled="saving"
          /></label>
          <label
            ><span>财务确认人</span
            ><AccountSelect v-model="draft.financeOwnerId" :options="config?.people?.finance || []" :disabled="saving"
          /></label>
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
    ASSIGN: '待分配',
    ACCEPT: '待接单',
    PROCESS: '处理中',
    TRANSFER: '待交接确认',
    REVIEW: '待审核',
    FINANCE: '待财务',
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
  { key: 'acceptanceDueAt', label: '接单截止' },
  { key: 'processingDueAt', label: '办理截止' },
  { key: 'reviewDueAt', label: '审核截止' },
  { key: 'financeDueAt', label: '财务截止' },
]
const actionNames: Record<string, string> = {
  coordinator: '调整协调人',
  plan: '设置人员与期限',
  follow_up: '登记等待与跟进',
  transfer_request: '发起转交',
  transfer_accept: '接受交接',
  transfer_reject: '驳回交接',
  transfer_cancel: '撤销交接',
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
  (props.config?.people?.handle || props.config?.assignees || []).filter((person) => person.id !== props.line?.ownerId),
)
const segmentColumns = [
  { title: '承办人', dataIndex: 'ownerName', width: 130 },
  { title: '分配时间', dataIndex: 'assignedAt', width: 190 },
  { title: '接单时间', dataIndex: 'acceptedAt', width: 190 },
  { title: '结束时间', dataIndex: 'endedAt', width: 190 },
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
    for (const key of ['reviewerId', 'financeOwnerId', ...deadlineFields.map((field) => field.key)])
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
