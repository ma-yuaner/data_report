<template>
  <section class="collaboration-panel">
    <div class="adm-toolbar">
      <strong>协办、整改与责任复核</strong
      ><a-button
        v-if="line && allowed(line, 'collaboration_create')"
        :disabled="saving"
        @click="openAction('collaboration_create')"
        >新增协办 / 整改</a-button
      ><a-button
        v-if="line && allowed(line, 'responsibility_propose')"
        :disabled="saving"
        @click="openAction('responsibility_propose')"
        >提出责任认定</a-button
      ><a-button @click="emit('attachments')">查看 / 上传证据附件</a-button>
    </div>
    <p class="adm-muted">
      协办只授予完成任务所需的访问范围，不等同于整单承办。责任提案需独立复核，不自动处罚或授予被归因人权限。非必需整改可在结案后继续跟踪。
    </p>
    <template v-if="line">
      <a-table
        row-key="id"
        :columns="taskColumns"
        :data-source="line.collaborations || []"
        :pagination="{ pageSize: 5 }"
        :scroll="{ x: 1120, y: 340 }"
        size="small"
      >
        <template #bodyCell="{ column, record: task }">
          <template v-if="column.key === 'description'"
            ><details>
              <summary>{{ task.title }}</summary>
              <p class="adm-prose">{{ task.description || '—' }}</p>
              <p v-if="task.result" class="adm-prose">办理结果：{{ task.result }}</p>
              <p>结果证据：{{ evidenceNames(task.evidence) }}</p>
              <p v-for="(review, index) in task.reviews || []" :key="index" class="adm-prose">
                复核：{{ review.approved ? '通过' : '退回' }} · {{ review.reason || '—' }} ·
                {{ review.reviewedByName || review.reviewedBy || review.byName || review.by || '—' }} ·
                {{ review.reviewedAt || review.at || '—' }}
              </p>
            </details></template
          >
          <template v-if="column.key === 'kind'"
            >{{ task.kind === 'REMEDIATION' ? '整改' : '协办' }}<br />{{
              task.required ? '完成前阻断结案' : '非结案前置'
            }}</template
          >
          <template v-if="column.key === 'status'">{{ taskStatusLabels[task.status] || task.status }}</template>
          <template v-if="column.key === 'due'">{{ task.dueAt || '未设期限，不视为按时' }}</template>
          <template v-if="column.key === 'actions'"
            ><a-space wrap
              ><a-button
                v-for="name in taskActions.filter((action) => allowed(task, action))"
                :key="name"
                size="small"
                :disabled="saving"
                @click="openAction(name, task)"
                >{{ actionNames[name] }}</a-button
              ></a-space
            ></template
          >
        </template>
        <template #emptyText><a-empty description="尚无协办或整改任务，不代表无整改需要" /></template>
      </a-table>
      <details :open="Boolean(line.responsibility)">
        <summary>责任认定提案及复核</summary>
        <template v-if="line.responsibility">
          <a-descriptions bordered size="small" :column="{ xs: 1, sm: 2 }">
            <a-descriptions-item label="认定状态">{{
              responsibilityStatusLabels[line.responsibility.status] || line.responsibility.status
            }}</a-descriptions-item>
            <a-descriptions-item label="类型">{{
              responsibilityTypes.find((item) => item.value === line?.responsibility?.type)?.label ||
              line.responsibility.type
            }}</a-descriptions-item>
            <a-descriptions-item label="责任主体">{{
              line.responsibility.responsibleName || line.responsibility.subject || '待确定'
            }}</a-descriptions-item>
            <a-descriptions-item label="提案人 / 时间"
              >{{ line.responsibility.proposedByName || line.responsibility.proposedBy }} ·
              {{ line.responsibility.proposedAt }}</a-descriptions-item
            >
            <a-descriptions-item label="认定依据" :span="2"
              ><span class="adm-prose">{{ line.responsibility.reason }}</span></a-descriptions-item
            >
            <a-descriptions-item label="证据" :span="2">{{
              evidenceNames(line.responsibility.evidence)
            }}</a-descriptions-item>
            <a-descriptions-item v-if="line.responsibility.reviewedAt" label="复核人 / 时间" :span="2"
              >{{ line.responsibility.reviewedByName || line.responsibility.reviewedBy }} ·
              {{ line.responsibility.reviewedAt }}</a-descriptions-item
            >
            <a-descriptions-item v-if="line.responsibility.reviewReason" label="复核依据" :span="2"
              ><span class="adm-prose">{{ line.responsibility.reviewReason }}</span></a-descriptions-item
            >
          </a-descriptions>
          <a-button
            v-if="allowed(line, 'responsibility_review')"
            :disabled="saving"
            style="margin: 12px 0"
            @click="openAction('responsibility_review')"
            >复核责任提案</a-button
          >
        </template>
        <a-empty v-else description="尚未形成责任提案，不自动归因到承办人" />
        <details v-if="line.responsibilityHistory?.length">
          <summary>历史责任版本（{{ line.responsibilityHistory.length }}）</summary>
          <article v-for="item in line.responsibilityHistory" :key="item.id" class="history-item">
            <p>
              {{ responsibilityStatusLabels[item.status] || item.status }} ·
              {{ item.responsibleName || item.subject || '未确定' }} · {{ item.proposedAt }}
            </p>
            <p class="adm-prose">提案依据：{{ item.reason }}</p>
            <p class="adm-prose">复核依据：{{ item.reviewReason || '尚无' }}</p>
            <p>证据：{{ evidenceNames(item.evidence) }}</p>
          </article>
        </details>
      </details>
    </template>
    <p v-else class="adm-muted">先选择订单明细，查看或办理协办、整改与责任认定。</p>
    <details v-if="allowed(record, 'attachment_share')">
      <summary>显式授权附件整份共享</summary>
      <a-alert
        type="warning"
        show-icon
        message="共享的是所选文件的全部内容，不是自动脱敏。需要脱敏时，请先上传实际脱敏副本，再关联原件。撤销共享不代表能收回已经下载的文件。"
      />
      <a-table
        row-key="id"
        :columns="sharingColumns"
        :data-source="record.attachments || []"
        :pagination="{ pageSize: 5 }"
        :scroll="{ x: 860 }"
        size="small"
      >
        <template #bodyCell="{ column, record: attachment }">
          <template v-if="column.key === 'shared'"
            >{{ (attachment.sharedLineIds || []).map(lineName).join('；') || '无显式共享明细' }}
            <p v-if="attachment.redactedFromId" class="adm-muted">
              标记为实际脱敏副本；原件：{{ fileName(attachment.redactedFromId) }}
            </p></template
          >
          <template v-if="column.key === 'actions'"
            ><a-button size="small" :disabled="saving" @click="openAction('attachment_share', attachment)"
              >设置 / 撤销共享</a-button
            ></template
          >
        </template>
      </a-table>
    </details>
    <p v-if="cachedDrafts.size" class="adm-muted">
      另有 {{ cachedDrafts.size }} 份未提交草稿；切回对应明细可恢复。草稿未保存到服务器。
    </p>
    <FormDialog
      v-model:open="dialogOpen"
      :title="actionNames[action] || '协作操作'"
      :busy="saving"
      :dirty="dirty"
      :error="formError"
      :submit-disabled="versionConflict"
      @submit="saveAction"
    >
      <FormGrid>
        <template v-if="action === 'collaboration_create'">
          <label
            ><span>任务类型 *</span
            ><a-select
              v-model:value="draft.kind"
              :disabled="saving"
              :options="[
                { value: 'COLLABORATION', label: '协办' },
                { value: 'REMEDIATION', label: '整改' },
              ]"
          /></label>
          <label
            ><span>接收人 *</span
            ><AccountSelect v-model="draft.ownerId" :options="config?.people?.handle || []" :disabled="saving"
          /></label>
          <label class="form-span"
            ><span>任务标题 *</span><a-input v-model:value="draft.title" :disabled="saving" :maxlength="200"
          /></label>
          <label class="form-span"
            ><span>办理目标与边界 *</span><a-textarea v-model:value="draft.description" :rows="4" :disabled="saving"
          /></label>
          <label><span>截止（北京时间）</span><DateField v-model="draft.dueAt" with-time :disabled="saving" /></label>
          <label
            ><span>是否结案前置</span
            ><a-checkbox v-model:checked="draft.required" :disabled="saving"
              >完成前阻断明细提交和整单结案</a-checkbox
            ></label
          >
        </template>
        <template v-if="action === 'collaboration_submit'"
          ><label class="form-span"
            ><span>办理结果 *</span><a-textarea v-model:value="draft.result" :rows="5" :disabled="saving" /></label
        ></template>
        <template v-if="action === 'responsibility_propose'">
          <label
            ><span>责任类型 *</span
            ><a-select v-model:value="draft.type" :options="responsibilityTypes" :disabled="saving"
          /></label>
          <label v-if="draft.type === 'PERSON'"
            ><span>内部责任账号 *</span
            ><AccountSelect
              v-model="draft.responsibleUserId"
              :options="config?.people?.handle || []"
              :disabled="saving"
          /></label>
          <label v-else
            ><span>外部 / 系统主体（无法确定时可待定）</span><a-input v-model:value="draft.subject" :disabled="saving"
          /></label>
        </template>
        <label v-if="['collaboration_submit', 'responsibility_propose'].includes(action)" class="form-span"
          ><span>有效证据附件 *</span
          ><a-select
            v-model:value="draft.evidence"
            mode="multiple"
            :options="evidenceOptions"
            :disabled="saving"
            placeholder="先上传真实材料，再选择附件"
          /><span class="adm-muted">请先在详情“原件与附件”页上传真实证据，返回此处选择。</span></label
        >
        <template v-if="action === 'attachment_share'">
          <label class="form-span"
            ><span>共享文件</span><a-input :value="fileName(draft.attachmentId)" readonly
          /></label>
          <label class="form-span"
            ><span>明确授权的订单明细（清空后保存即撤销共享）</span
            ><a-select v-model:value="draft.lineIds" mode="multiple" :options="lineOptions" :disabled="saving"
          /></label>
          <label class="form-span"
            ><span>如本文件为实际脱敏副本，关联原件</span
            ><a-select
              v-model:value="draft.redactedFromId"
              allow-clear
              :options="evidenceOptions.filter((item) => item.value !== draft.attachmentId)"
              :disabled="saving"
              placeholder="不做系统自动脱敏"
          /></label>
          <label class="form-span"
            ><a-checkbox v-model:checked="draft.acknowledgeFullFile" :disabled="saving"
              >我确认已检查所选文件全部内容，并明确授权整份文件（含撤销操作） *</a-checkbox
            ></label
          >
        </template>
        <label v-if="['collaboration_review', 'responsibility_review'].includes(action)" class="form-span"
          ><span>复核结论 *</span
          ><a-radio-group v-model:value="draft.approved" :disabled="saving"
            ><a-radio :value="true">通过</a-radio><a-radio :value="false">退回 / 不认可</a-radio></a-radio-group
          ></label
        >
        <label v-if="needsReason" class="form-span"
          ><span>{{ action === 'responsibility_propose' ? '责任认定依据' : '操作 / 复核依据' }} *</span
          ><a-textarea v-model:value="draft.reason" :rows="4" :disabled="saving"
        /></label>
        <p v-if="action === 'collaboration_accept'" class="form-span">
          接受后由你完成该协办任务；不会取代原订单承办人，也不重置原截止时间。
        </p>
      </FormGrid>
      <a-alert
        v-if="versionConflict"
        type="warning"
        show-icon
        message="草稿已保留，但不可覆盖最新记录。请先刷新，再重新打开核对；原草稿可复制保留。"
      />
    </FormDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import AccountSelect from '@/components/AccountSelect.vue'
import FormDialog from '@/components/FormDialog.vue'
import FormGrid from '@/components/FormGrid.vue'
import DateField from '@/components/DateField.vue'
import { admApi, allowed, errorText, type AdmCase, type AdmConfig, type AdmLine, type Fields } from './api'
const props = defineProps<{ record: AdmCase; line: AdmLine | null; config: AdmConfig | null }>()
const emit = defineEmits<{ changed: [record: AdmCase]; attachments: [] }>()
const auth = useAuthStore()
const dialogOpen = ref(false),
  action = ref(''),
  draft = ref<Fields>({}),
  baseline = ref('{}'),
  saving = ref(false),
  formError = ref(''),
  versionConflict = ref(false)
let contextCase = '',
  contextLine = '',
  version = 0,
  generation = 0
type Cached = { action: string; draft: Fields; baseline: string; version: number; conflict: boolean }
const cachedDrafts = ref(new Map<string, Cached>())
const dirty = computed(() => JSON.stringify(draft.value) !== baseline.value)
const needsReason = computed(() =>
  [
    'responsibility_propose',
    'responsibility_review',
    'collaboration_review',
    'collaboration_cancel',
    'attachment_share',
  ].includes(action.value),
)
const actionNames: Record<string, string> = {
  collaboration_create: '新增协办 / 整改',
  collaboration_accept: '接受协办任务',
  collaboration_submit: '提交协办结果',
  collaboration_review: '复核协办结果',
  collaboration_cancel: '取消协办任务',
  responsibility_propose: '提出责任认定',
  responsibility_review: '复核责任提案',
  attachment_share: '设置 / 撤销整份附件共享',
}
const taskActions = ['collaboration_accept', 'collaboration_submit', 'collaboration_review', 'collaboration_cancel']
const responsibilityTypes = [
  { value: 'PERSON', label: '内部人员' },
  { value: 'SYSTEM', label: '系统' },
  { value: 'SUPPLIER', label: '供应商' },
  { value: 'AIRLINE', label: '航司' },
  { value: 'PLATFORM', label: '平台' },
  { value: 'UNDETERMINED', label: '待认定' },
]
const taskStatusLabels: Record<string, string> = {
  PENDING_ACCEPT: '待接收',
  PROCESSING: '办理中',
  PENDING_REVIEW: '待复核',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
}
const responsibilityStatusLabels: Record<string, string> = {
  PENDING_REVIEW: '提案待复核',
  CONFIRMED: '已确认',
  REJECTED: '不认可 / 已退回',
}
const fileName = (id: string) =>
  props.record.attachments?.find((item) => item.id === id)?.name || '不可见 / 已撤销的附件'
const evidenceNames = (ids: unknown) =>
  Array.isArray(ids) && ids.length ? ids.map((id) => fileName(String(id))).join('；') : '无'
const lineName = (id: string) => {
  const line = props.record.lines.find((item) => item.id === id)
  return line ? `${line.platform || '待核实平台'} · ${line.orderNo || line.id}` : '无关 / 不可见明细'
}
const evidenceOptions = computed(() =>
  (props.record.attachments || []).map((item) => ({
    value: item.id,
    label: `${item.name} · ${item.lineId ? lineName(item.lineId) : '主单材料'}`,
  })),
)
const lineOptions = computed(() => props.record.lines.map((item) => ({ value: item.id, label: lineName(item.id) })))
const taskColumns = [
  { title: '标题与详情（展开）', key: 'description', width: 330 },
  { title: '类型 / 结案约束', key: 'kind', width: 150 },
  { title: '协办人', dataIndex: 'ownerName', width: 130 },
  { title: '状态', key: 'status', width: 110 },
  { title: '截止（北京时间）', key: 'due', width: 190 },
  { title: '操作', key: 'actions', width: 230 },
]
const sharingColumns = [
  { title: '文件名', dataIndex: 'name', width: 260 },
  { title: '整份文件授权明细', key: 'shared', width: 380 },
  { title: '操作', key: 'actions', width: 180 },
]
function openAction(name: string, target?: Fields) {
  if (saving.value) return
  action.value = name
  contextCase = props.record.id
  contextLine = props.line?.id || ''
  version = props.record.version
  draft.value = { reason: '' }
  if (name === 'collaboration_create')
    draft.value = { kind: 'COLLABORATION', ownerId: '', title: '', description: '', dueAt: '', required: false }
  if (name.startsWith('collaboration_') && target) {
    draft.value.taskId = target.id
    draft.value.result = target.result || ''
    draft.value.evidence = [...(target.evidence || [])]
  }
  if (['collaboration_review', 'responsibility_review'].includes(name)) draft.value.approved = true
  if (name === 'responsibility_propose')
    draft.value = { type: 'UNDETERMINED', responsibleUserId: '', subject: '', reason: '', evidence: [] }
  if (name === 'attachment_share' && target)
    draft.value = {
      attachmentId: target.id,
      lineIds: [...(target.sharedLineIds || [])],
      redactedFromId: target.redactedFromId || undefined,
      acknowledgeFullFile: false,
      reason: '',
    }
  baseline.value = JSON.stringify(draft.value)
  formError.value = ''
  versionConflict.value = false
  dialogOpen.value = true
}
async function saveAction() {
  if (saving.value || versionConflict.value) return
  const name = action.value,
    value = draft.value
  if (needsReason.value && !value.reason?.trim()) {
    formError.value = '请填写操作或认定依据'
    return
  }
  if (name === 'collaboration_create' && (!value.ownerId || !value.title?.trim() || !value.description?.trim())) {
    formError.value = '请选择接收人，填写标题与办理目标'
    return
  }
  if (name === 'collaboration_submit' && (!value.result?.trim() || !value.evidence?.length)) {
    formError.value = '提交结果需要描述与真实证据附件'
    return
  }
  if (
    name === 'responsibility_propose' &&
    (!value.evidence?.length ||
      (value.type === 'PERSON' && !value.responsibleUserId) ||
      (['SUPPLIER', 'AIRLINE', 'PLATFORM', 'SYSTEM'].includes(value.type) && !value.subject?.trim()))
  ) {
    formError.value = '请补齐责任主体及有效证据附件'
    return
  }
  if (name === 'attachment_share' && !value.acknowledgeFullFile) {
    formError.value = '请确认已检查并明确授权整份文件内容'
    return
  }
  saving.value = true
  formError.value = ''
  const gen = generation,
    caseId = contextCase,
    lineId = contextLine
  const body: Fields = { ...value, action: name, version }
  if (name === 'responsibility_propose' && value.type !== 'PERSON') delete body.responsibleUserId
  try {
    const result =
      name === 'attachment_share' ? await admApi.action(caseId, body) : await admApi.lineAction(caseId, lineId, body)
    if (gen !== generation || props.record.id !== caseId || (props.line?.id || '') !== lineId) return
    baseline.value = JSON.stringify(draft.value)
    dialogOpen.value = false
    cachedDrafts.value.delete(`${caseId}:${lineId}`)
    message.success('已保存；责任提案不代表自动处罚，站内任务不代表站外通知已送达')
    emit('changed', result)
  } catch (cause) {
    if (gen === generation) {
      formError.value = errorText(cause)
      versionConflict.value = (cause as { code?: string }).code === 'ADM_VERSION_CONFLICT'
    }
  } finally {
    if (gen === generation) saving.value = false
  }
}
watch(
  () => `${props.record.id}:${props.line?.id || ''}`,
  (key, old) => {
    if (old && dialogOpen.value && dirty.value)
      cachedDrafts.value.set(old, {
        action: action.value,
        draft: JSON.parse(JSON.stringify(draft.value)),
        baseline: baseline.value,
        version,
        conflict: versionConflict.value,
      })
    generation++
    saving.value = false
    dialogOpen.value = false
    formError.value = ''
    draft.value = {}
    baseline.value = '{}'
    const cached = cachedDrafts.value.get(key)
    if (cached) {
      action.value = cached.action
      draft.value = cached.draft
      baseline.value = cached.baseline
      version = cached.version
      versionConflict.value = cached.conflict
      contextCase = props.record.id
      contextLine = props.line?.id || ''
      dialogOpen.value = true
      formError.value = '已恢复该明细未提交草稿，仍使用原版本；请核对最新记录后提交。'
      cachedDrafts.value.delete(key)
    }
  },
)
watch(
  () => auth.user?.id,
  () => {
    generation++
    cachedDrafts.value.clear()
    dialogOpen.value = false
    saving.value = false
    draft.value = {}
    baseline.value = '{}'
    formError.value = ''
  },
)
onBeforeUnmount(() => {
  generation++
})
defineExpose({ hasUnsavedDraft: () => (dialogOpen.value && dirty.value) || cachedDrafts.value.size > 0 })
</script>

<style scoped>
.collaboration-panel {
  margin: 16px 0;
  min-width: 0;
  padding: 16px;
  border: 1px solid #e4e9ef;
  border-radius: 10px;
  background: #fff;
}
summary {
  cursor: pointer;
  margin: 10px 0;
  overflow-wrap: anywhere;
}
.history-item {
  border-top: 1px solid #e4e9ef;
  padding: 12px 0;
}
</style>
