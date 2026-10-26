<template>
  <section class="completion-panel">
    <details @toggle="togglePanel">
      <summary>提醒收件箱、日报与运营设置</summary>
      <template v-if="expanded">
        <p class="adm-muted">
          本人收件箱最多100条；日报按日最多20个修订，非全量历史统计。真实发送由策略与部署开关共同控制。
        </p>
        <a-tabs v-model:active-key="activeTab" @change="loadTab">
          <a-tab-pane key="inbox" tab="我的收件箱">
            <div class="adm-toolbar">
              <span>未读 {{ unread ?? '待查询' }}；已读不代表接单。</span
              ><a-button :loading="loading" @click="loadTab">刷新</a-button>
            </div>
            <a-table
              row-key="id"
              :columns="inboxColumns"
              :data-source="inbox"
              :loading="loading"
              :pagination="{ pageSize: 10 }"
              :scroll="{ x: 780, y: 360 }"
              size="small"
            >
              <template #bodyCell="{ column, record: item }">
                <template v-if="column.key === 'body'"
                  ><details>
                    <summary>{{ item.title }}</summary>
                    <p class="adm-prose">{{ item.body }}</p>
                  </details></template
                >
                <template v-if="column.key === 'read'">{{ item.readAt ? `已读 ${item.readAt}` : '未读' }}</template>
                <template v-if="column.key === 'actions'"
                  ><a-space
                    ><router-link v-if="item.caseId" :to="inboxLink(item)">查看任务</router-link
                    ><a-button v-if="!item.readAt" size="small" :disabled="busy" @click="markRead(item)"
                      >标记已读</a-button
                    ></a-space
                  ></template
                >
              </template>
              <template #emptyText
                ><a-empty description="当前没有仍有效的本人消息；不表示没有待办或业务已达标"
              /></template>
            </a-table>
          </a-tab-pane>
          <a-tab-pane key="reports" tab="日报与分项试榜">
            <FilterPanel stacked :instant="false" :show-reset="false" :loading="loading">
              <label><span>业务日期（北京时间）</span><DateField v-model="reportDate" /></label>
              <label
                ><span>查看范围</span><a-select v-model:value="reportScope" :options="scopes" @change="scopeChanged"
              /></label>
              <template #actions
                ><a-button :loading="loading" @click="loadTab">查询日报</a-button
                ><a-button v-if="admin" :disabled="busy" @click="openDialog('capture')"
                  >捕获当前快照</a-button
                ></template
              >
              <template #footer
                >只捕获当前时点，不伪造过去午夜。未发布报告仅管理员可见；旧来源不足不补0，不作为正式绩效或处罚依据。</template
              >
            </FilterPanel>
            <a-table
              row-key="id"
              :columns="reportColumns"
              :data-source="reports"
              :pagination="{ pageSize: 5 }"
              :scroll="{ x: 900 }"
              size="small"
            >
              <template #bodyCell="{ column, record: item }">
                <template v-if="column.key === 'published'">{{ item.published ? '已发布' : '待人工核对' }}</template>
                <template v-if="column.key === 'actions'"
                  ><a-space
                    ><a-button size="small" :disabled="busy" @click="viewReport(item.id)">查看</a-button
                    ><a-button
                      v-if="admin && !item.published"
                      size="small"
                      :disabled="busy"
                      @click="openDialog('publish', item)"
                      >核对后发布</a-button
                    ></a-space
                  ></template
                >
              </template>
            </a-table>
            <a-spin :spinning="reportLoading">
              <template v-if="selectedReport">
                <h3>
                  {{ selectedReport.businessDate }} · 修订{{ selectedReport.revision }} ·
                  {{ selectedReport.published ? '已发布' : '未发布' }}
                </h3>
                <p class="adm-muted">
                  截点 {{ selectedReport.generatedAt }} · 规则 {{ selectedReport.ruleVersion }} · 范围
                  {{ scopeLabel }}；风险快照不是全天工作量。
                </p>
                <details open>
                  <summary>数据质量与范围限制（先核对，再看表现）</summary>
                  <dl class="quality-list">
                    <template v-for="item in qualityItems" :key="item.key"
                      ><dt>{{ item.key }}</dt>
                      <dd class="adm-prose">{{ renderValue(item.value) }}</dd></template
                    >
                  </dl>
                  <p v-for="item in selectedReport.limitations || []" :key="item" class="adm-muted">{{ item }}</p>
                </details>
                <details>
                  <summary>当前风险摘要</summary>
                  <dl class="quality-list">
                    <template v-for="(value, key) in selectedReport.summary || {}" :key="key"
                      ><dt>{{ summaryLabels[key] || key }}</dt>
                      <dd>{{ renderValue(value) }}</dd></template
                    >
                  </dl>
                </details>
                <p class="adm-muted">
                  试运行分项榜仅比较同业务类型的承办首次审核通过率；样本不足/来源不足不排名，同分并列，无综合分。完成量、当前负荷与质量不能混为同一个结论。
                </p>
                <details v-if="Array.isArray(selectedReport.sources) && selectedReport.sources.length">
                  <summary>获授权来源对象与快照版本（最多展示100条）</summary>
                  <p class="adm-muted">
                    来源共{{
                      selectedReport.sources.length
                    }}项；以下链接为当前详情，不是旧版本页面，访问时会重新鉴权。当前状态可能已变化，不能反写日报快照。
                  </p>
                  <ul>
                    <li v-for="source in selectedReport.sources.slice(0, 100)" :key="source.id">
                      <router-link :to="`/adm/cases/${encodeURIComponent(source.id)}`">{{ source.id }}</router-link> ·
                      快照版本 {{ source.version }}
                    </li>
                  </ul>
                </details>
                <a-table
                  :row-key="personKey"
                  :columns="peopleColumns"
                  :data-source="selectedReport.people || []"
                  :pagination="{ pageSize: 10 }"
                  :scroll="{ x: 1550, y: 360 }"
                  size="small"
                >
                  <template #bodyCell="{ column, record: person }">
                    <template v-if="column.key === 'role'">{{ roleLabels[person.role] || person.role }}</template>
                    <template v-if="column.key === 'businessType'">{{ label(person.businessType) }}</template>
                    <template v-if="column.key === 'rate'">{{
                      person.firstPassRate == null ? '来源/样本不足' : `${person.firstPassRate}%`
                    }}</template>
                    <template v-if="column.key === 'rank'">{{
                      person.rank == null
                        ? person.eligible
                          ? '试榜未启用'
                          : '不参与排名'
                        : `并列允许 · ${person.rank}`
                    }}</template>
                    <template v-if="column.nullable">{{ person[column.dataIndex] ?? '来源不足' }}</template>
                  </template>
                </a-table>
              </template>
            </a-spin>
          </a-tab-pane>
          <a-tab-pane v-if="admin" key="settings" tab="运营设置（管理员）">
            <a-button :loading="loading" @click="loadTab">读取已保存设置</a-button>
            <template v-if="settings">
              <a-descriptions bordered size="small" :column="{ xs: 1, md: 2 }" style="margin-top: 12px">
                <a-descriptions-item label="策略版本">{{ settings.version }}</a-descriptions-item>
                <a-descriptions-item label="提醒策略">{{
                  settings.notificationsEnabled ? '已启用' : '关闭'
                }}</a-descriptions-item>
                <a-descriptions-item label="部署站外发送开关">{{
                  settings.externalDeliveryEnabled ? '开启（仍需策略、映射及权限）' : '关闭：不向外发送'
                }}</a-descriptions-item>
                <a-descriptions-item label="监控端点可用">{{
                  settings.endpointAvailable ? '可选择已有端点' : '不可用，不输入Webhook'
                }}</a-descriptions-item>
                <a-descriptions-item label="自动日报">{{
                  settings.snapshotsEnabled ? `北京时间 ${settings.snapshotAt}` : '关闭'
                }}</a-descriptions-item>
                <a-descriptions-item label="分项试榜">{{
                  settings.rankingEnabled ? `已启用，最小样本 ${settings.minimumSamples}` : '关闭'
                }}</a-descriptions-item>
                <a-descriptions-item label="批准依据" :span="2"
                  ><span class="adm-prose">{{ settings.approvalNote || '未配置' }}</span></a-descriptions-item
                >
              </a-descriptions>
              <div class="adm-toolbar">
                <a-button :disabled="busy" @click="openDialog('settings')">修改运营策略</a-button
                ><a-button :loading="busy" @click="preview">只预览，不发送</a-button>
              </div>
            </template>
            <template v-if="previewResult">
              <a-alert
                type="info"
                show-icon
                :message="`预览：策略${previewResult.enabled ? '开启' : '关闭'}，站外部署开关${previewResult.externalDeliveryEnabled ? '开启' : '关闭'}；本操作没有发送消息`"
              />
              <p>
                当前任务
                {{
                  Array.isArray(previewResult.tasks) ? previewResult.tasks.length : (previewResult.tasks ?? '未返回')
                }}；拟创建 {{ renderValue(previewResult.wouldCreate) }}
              </p>
              <p
                v-for="item in [...(previewResult.missingConfig || []), ...(previewResult.warnings || [])]"
                :key="item"
                class="adm-muted"
              >
                {{ item }}
              </p>
            </template>
          </a-tab-pane>
          <a-tab-pane v-if="admin" key="deliveries" tab="投递记录">
            <div class="adm-toolbar">
              <span>最多100条；UNKNOWN表示结果未知，不冒充已送达或自动重发。</span
              ><a-button :loading="loading" @click="loadTab">刷新</a-button>
            </div>
            <a-table
              row-key="id"
              :columns="deliveryColumns"
              :data-source="deliveries"
              :pagination="{ pageSize: 10 }"
              :scroll="{ x: 1100, y: 360 }"
              size="small"
            >
              <template #bodyCell="{ column, record: item }"
                ><template v-if="column.key === 'status'">{{
                  deliveryLabels[item.status] || item.status
                }}</template></template
              >
            </a-table>
          </a-tab-pane>
        </a-tabs>
        <a-alert v-if="error" type="error" :message="error" show-icon style="margin-top: 12px" />
      </template>
    </details>
    <FormDialog
      v-model:open="dialogOpen"
      :title="dialogTitle"
      :busy="busy"
      :dirty="dirty"
      :error="dialogError"
      :submit-disabled="conflict"
      @submit="saveDialog"
    >
      <template v-if="dialogAction === 'settings'">
        <a-alert
          type="warning"
          show-icon
          message="这里仅修改经业务批准的策略；开启提醒会允许worker创建通知。站外发送还需部署开关，页面不能开启部署开关。"
        />
        <FormGrid>
          <label
            ><span>启用提醒策略</span
            ><a-checkbox v-model:checked="draft.notificationsEnabled" :disabled="busy">启用</a-checkbox></label
          >
          <label
            ><span>复用监控通知端点</span
            ><a-select
              v-model:value="draft.endpointIds"
              mode="multiple"
              :disabled="busy || !settings?.endpointAvailable"
              :options="(settings?.endpointOptions || []).map((item) => ({ value: item.id, label: item.name }))"
          /></label>
          <label v-for="field in minuteFields" :key="field.key"
            ><span>{{ field.label }}（分钟，不预设SLA）</span
            ><a-input-number v-model:value="draft[field.key]" :min="1" :precision="0" :disabled="busy"
          /></label>
          <label
            ><span>启用自动日报快照</span
            ><a-checkbox v-model:checked="draft.snapshotsEnabled" :disabled="busy">启用</a-checkbox></label
          >
          <label
            ><span>自动快照时刻（北京时间HH:mm）</span
            ><a-input v-model:value="draft.snapshotAt" placeholder="业务批准后填写，例如09:30" :disabled="busy"
          /></label>
          <label
            ><span>启用分项试榜（非正式绩效）</span
            ><a-checkbox v-model:checked="draft.rankingEnabled" :disabled="busy">启用</a-checkbox></label
          >
          <label
            ><span>最小样本量</span
            ><a-input-number v-model:value="draft.minimumSamples" :min="1" :precision="0" :disabled="busy"
          /></label>
          <label class="form-span"
            ><span>批准依据与适用范围 *</span><a-textarea v-model:value="draft.approvalNote" :rows="4" :disabled="busy"
          /></label>
        </FormGrid>
      </template>
      <template v-else
        ><a-alert
          type="info"
          show-icon
          :message="
            dialogAction === 'capture'
              ? '仅捕获当前时点；不能选择过去日期生成虚假历史。'
              : '请核对来源质量与可见范围；发布后普通用户可按授权范围查看。内容不可编辑，更正需新修订。'
          " /><label class="dialog-reason"
          ><span>{{ dialogAction === 'capture' ? '捕获原因' : '人工核对及发布依据' }} *</span
          ><a-textarea v-model:value="draft.reason" :rows="4" :disabled="busy" /></label
      ></template>
      <a-alert
        v-if="conflict"
        type="warning"
        show-icon
        message="版本已变化，草稿保留但不可覆盖。请关闭后读取最新版本，再重新打开核对。"
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
import { admApi, errorText, label, type AdmOperationConfig, type AdmReport, type Fields } from './api'

const auth = useAuthStore()
const admin = computed(() => Boolean(auth.user?.isAdmin))
const can = (permission: string) => admin.value || Boolean(auth.user?.permissions.includes(`adm.${permission}`))
const scopes = computed(() => [
  { value: 'mine', label: '本人' },
  ...(can('scope.team') ? [{ value: 'team', label: '管理团队' }] : []),
  ...(can('scope.all') ? [{ value: 'all', label: '全部授权范围' }] : []),
])
const expanded = ref(false),
  activeTab = ref('inbox'),
  loading = ref(false),
  busy = ref(false),
  error = ref('')
const inbox = ref<Fields[]>([]),
  unread = ref<number | null>(null),
  deliveries = ref<Fields[]>([]),
  reports = ref<AdmReport[]>([])
const settings = ref<AdmOperationConfig | null>(null),
  previewResult = ref<Fields | null>(null)
const todayParts = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
}).formatToParts(new Date())
const todayPart = (name: string) => todayParts.find((part) => part.type === name)?.value || ''
const reportDate = ref(`${todayPart('year')}-${todayPart('month')}-${todayPart('day')}`),
  reportScope = ref('mine'),
  selectedReport = ref<AdmReport | null>(null),
  reportLoading = ref(false)
let request = 0,
  reportRequest = 0,
  generation = 0
const scopeLabel = computed(() => scopes.value.find((item) => item.value === reportScope.value)?.label || '本人')
const inboxLink = (item: Fields) =>
  `/adm/cases/${encodeURIComponent(item.caseId)}${item.lineId ? `?lineId=${encodeURIComponent(item.lineId)}` : ''}`
const renderValue = (value: unknown): string =>
  value == null ? '来源不足 / 未配置' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
const summaryLabels: Record<string, string> = {
  tasks: '当前任务',
  overdue: '已逾期',
  missingDeadline: '缺期限',
  unassigned: '未分配',
  waiting: '等待跟进',
  openTasks: '未完成任务',
  completedTasks: '可信已完成任务',
}
const roleLabels: Record<string, string> = {
  HANDLER: '承办人',
  REVIEWER: '审核人',
  FINANCE: '财务',
  COLLABORATOR: '协办人',
}
const deliveryLabels: Record<string, string> = {
  PENDING: '待投递',
  SENT: '已获成功回执',
  FAILED: '明确失败',
  UNKNOWN: '结果未知，勿重复发送',
  CANCELLED: '已取消',
  RETRY: '待有限重试',
  SKIPPED: '跳过',
  DELIVERED: '已获成功回执',
}
const qualityItems = computed(() =>
  Object.entries(selectedReport.value?.quality || {}).map(([key, value]) => ({ key, value })),
)
const personKey = (person: Fields) => `${person.ownerId || 'unmapped'}:${person.role}:${person.businessType}`
const inboxColumns = [
  { title: '消息（展开全文）', key: 'body', width: 340 },
  { title: '创建时间', dataIndex: 'createdAt', width: 190 },
  { title: '阅读', key: 'read', width: 210 },
  { title: '操作', key: 'actions', width: 180 },
]
const reportColumns = [
  { title: '业务日期', dataIndex: 'businessDate', width: 120 },
  { title: '捕获时间', dataIndex: 'generatedAt', width: 190 },
  { title: '修订', dataIndex: 'revision', width: 70 },
  { title: '状态', key: 'published', width: 130 },
  { title: '规则版本', dataIndex: 'ruleVersion', width: 160 },
  { title: '操作', key: 'actions', width: 190 },
]
const peopleColumns = [
  { title: '人员', dataIndex: 'ownerName', width: 140 },
  { title: '角色', key: 'role', width: 100 },
  { title: '业务类型', key: 'businessType', width: 110 },
  ...[
    { title: '当前未完成', dataIndex: 'openTasks' },
    { title: '当前逾期', dataIndex: 'overdue' },
    { title: '缺期限', dataIndex: 'missingDeadline' },
    { title: '可信首次审核', dataIndex: 'firstReviewed' },
    { title: '首次通过', dataIndex: 'firstPassed' },
    { title: '可信完成', dataIndex: 'completedTasks' },
  ].map((item) => ({ ...item, key: item.dataIndex, nullable: true, width: 130 })),
  { title: '首次通过率', key: 'rate', width: 150 },
  { title: '同类型分项试榜', key: 'rank', width: 180 },
]
const deliveryColumns = [
  { title: '渠道', dataIndex: 'channel', width: 100 },
  { title: '接收账号', dataIndex: 'recipientId', width: 160 },
  { title: '状态', key: 'status', width: 220 },
  { title: '尝试数', dataIndex: 'attempts', width: 80 },
  { title: '创建时间', dataIndex: 'createdAt', width: 190 },
  { title: '下次尝试', dataIndex: 'nextAttemptAt', width: 190 },
  { title: '诊断码', dataIndex: 'errorCode', width: 160 },
]
const minuteFields = [
  { key: 'leadMinutes', label: '临期提前量' },
  { key: 'repeatMinutes', label: '重复提醒间隔' },
  { key: 'escalationMinutes', label: '逾期升级间隔' },
]
function togglePanel(event: Event) {
  expanded.value = (event.target as HTMLDetailsElement).open
  if (expanded.value) void loadTab()
}
async function loadTab() {
  if (!expanded.value) return
  const seq = ++request,
    tab = activeTab.value
  loading.value = true
  error.value = ''
  try {
    if (tab === 'inbox') {
      const value = await admApi.inbox()
      if (seq === request) {
        inbox.value = value.items
        unread.value = value.unread
      }
    } else if (tab === 'settings' && admin.value) {
      const value = await admApi.operationConfig()
      if (seq === request) settings.value = value
    } else if (tab === 'deliveries' && admin.value) {
      const value = await admApi.deliveries()
      if (seq === request) deliveries.value = value.items
    } else if (tab === 'reports') {
      reportRequest++
      selectedReport.value = null
      if (!reportDate.value) {
        reports.value = []
        error.value = '请选择业务日期后查询'
        return
      }
      const value = await admApi.reports(reportDate.value)
      if (seq === request) reports.value = value.items
    }
  } catch (cause) {
    if (seq === request) {
      error.value = errorText(cause)
      if (tab === 'inbox') {
        inbox.value = []
        unread.value = null
      } else if (tab === 'reports') reports.value = []
      else if (tab === 'settings') settings.value = null
      else deliveries.value = []
    }
  } finally {
    if (seq === request) loading.value = false
  }
}
async function markRead(item: Fields) {
  if (busy.value) return
  busy.value = true
  const gen = generation
  try {
    await admApi.readInbox(item.id, item.version)
    if (gen === generation) await loadTab()
  } catch (cause) {
    if (gen === generation) error.value = errorText(cause)
  } finally {
    if (gen === generation) busy.value = false
  }
}
async function viewReport(id: string) {
  const seq = ++reportRequest
  selectedReport.value = null
  reportLoading.value = true
  error.value = ''
  try {
    const value = await admApi.report(id, reportScope.value)
    if (seq === reportRequest) selectedReport.value = value
  } catch (cause) {
    if (seq === reportRequest) error.value = errorText(cause)
  } finally {
    if (seq === reportRequest) reportLoading.value = false
  }
}
function scopeChanged() {
  const id = selectedReport.value?.id
  reportRequest++
  selectedReport.value = null
  if (id) void viewReport(id)
}
async function preview() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  previewResult.value = null
  const gen = generation
  try {
    const result = await admApi.operationPreview()
    if (gen === generation) previewResult.value = result
  } catch (cause) {
    if (gen === generation) error.value = errorText(cause)
  } finally {
    if (gen === generation) busy.value = false
  }
}
const dialogOpen = ref(false),
  dialogAction = ref(''),
  draft = ref<Fields>({}),
  baseline = ref('{}'),
  dialogError = ref(''),
  conflict = ref(false)
let targetReport: AdmReport | null = null
const dirty = computed(() => baseline.value !== JSON.stringify(draft.value))
const dialogTitle = computed(
  () =>
    ({ settings: '修改ADM运营策略', capture: '捕获当前日报快照', publish: '人工核对并发布日报' })[dialogAction.value] ||
    '运营操作',
)
const settingKeys = [
  'notificationsEnabled',
  'endpointIds',
  'leadMinutes',
  'repeatMinutes',
  'escalationMinutes',
  'snapshotsEnabled',
  'snapshotAt',
  'rankingEnabled',
  'minimumSamples',
  'approvalNote',
]
function openDialog(action: string, report?: AdmReport) {
  if (!admin.value || busy.value) return
  dialogAction.value = action
  targetReport = report || null
  draft.value = { reason: '' }
  if (action === 'settings') {
    if (!settings.value) return
    draft.value = Object.fromEntries(settingKeys.map((key) => [key, settings.value?.[key]]))
    draft.value.endpointIds = [...(settings.value.endpointIds || [])]
    draft.value.version = settings.value.version
  }
  baseline.value = JSON.stringify(draft.value)
  dialogError.value = ''
  conflict.value = false
  dialogOpen.value = true
}
async function saveDialog() {
  if (busy.value || conflict.value || !admin.value) return
  const action = dialogAction.value
  if (action === 'settings') {
    if (!draft.value.approvalNote?.trim()) {
      dialogError.value = '请填写批准依据与适用范围'
      return
    }
    if (draft.value.snapshotsEnabled && !/^([01]\d|2[0-3]):[0-5]\d$/.test(draft.value.snapshotAt || '')) {
      dialogError.value = '请输入北京时间HH:mm'
      return
    }
    if (
      draft.value.rankingEnabled &&
      (!Number.isInteger(draft.value.minimumSamples) || draft.value.minimumSamples < 1)
    ) {
      dialogError.value = '试榜须填写批准的正整数最小样本量'
      return
    }
  } else if (!draft.value.reason?.trim()) {
    dialogError.value = '请填写操作原因或核对依据'
    return
  }
  busy.value = true
  dialogError.value = ''
  const gen = generation
  try {
    let report: AdmReport | null = null
    if (action === 'settings') {
      const result = await admApi.saveOperationConfig({ ...draft.value })
      if (gen === generation) {
        settings.value = result
        previewResult.value = null
      }
    } else if (action === 'capture') report = await admApi.captureReport(draft.value.reason)
    else if (targetReport)
      report = await admApi.publishReport(targetReport.id, targetReport.version, draft.value.reason)
    if (gen !== generation) return
    baseline.value = JSON.stringify(draft.value)
    dialogOpen.value = false
    message.success(action === 'publish' ? '日报已发布；不代表正式绩效确认' : '已保存')
    if (report) {
      reportDate.value = report.businessDate
      await loadTab()
      await viewReport(report.id)
    }
  } catch (cause) {
    if (gen === generation) {
      dialogError.value = errorText(cause)
      conflict.value = (cause as { code?: string }).code === 'ADM_VERSION_CONFLICT'
    }
  } finally {
    if (gen === generation) busy.value = false
  }
}
watch(
  () => [auth.user?.id, auth.user?.isAdmin, auth.user?.permissions.join(',')],
  () => {
    generation++
    request++
    reportRequest++
    loading.value = false
    busy.value = false
    reportLoading.value = false
    inbox.value = []
    unread.value = null
    reports.value = []
    deliveries.value = []
    settings.value = null
    selectedReport.value = null
    previewResult.value = null
    dialogOpen.value = false
    draft.value = {}
    baseline.value = '{}'
    activeTab.value = 'inbox'
    reportScope.value = 'mine'
    error.value = ''
    dialogError.value = ''
    if (expanded.value) void loadTab()
  },
)
onBeforeUnmount(() => {
  generation++
  request++
  reportRequest++
})
defineExpose({ hasUnsavedDraft: () => dialogOpen.value && dirty.value })
</script>

<style scoped>
.completion-panel {
  margin: 16px 0;
  min-width: 0;
  padding: 16px;
  border: 1px solid #e4e9ef;
  border-radius: 10px;
  background: #fff;
}
summary {
  cursor: pointer;
  margin: 8px 0;
}
.quality-list {
  display: grid;
  grid-template-columns: minmax(120px, 220px) minmax(0, 1fr);
  gap: 8px 16px;
}
.quality-list dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.dialog-reason {
  display: grid;
  gap: 8px;
  margin: 16px 0;
}
@media (max-width: 560px) {
  .quality-list {
    grid-template-columns: 1fr;
  }
}
</style>
