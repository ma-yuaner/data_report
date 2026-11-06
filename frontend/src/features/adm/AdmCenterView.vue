<template>
  <div class="page-wrap adm-center">
    <div class="adm-heading">
      <div>
        <h1>{{ isWorkbench ? 'ADM 工作台' : 'ADM 台账' }}</h1>
        <p>以供应下发 ADM 为主单，统一处理多平台、多订单及出退改明细。</p>
      </div>
      <a-space wrap
        ><router-link :to="isWorkbench ? '/adm/cases' : '/adm/workbench'">{{
          isWorkbench ? '查看完整台账' : '返回我的工作台'
        }}</router-link
        ><a-button :loading="loading" @click="load">刷新</a-button
        ><a-button v-if="permission('create')" type="primary" @click="openCreate">新建 ADM</a-button></a-space
      >
    </div>
    <a-alert v-if="error" type="error" show-icon :message="error" style="margin-bottom: 16px" />
    <a-alert
      v-if="config && config.storageMode !== 'mysql'"
      type="warning"
      show-icon
      :message="`当前存储模式：${config.storageMode}。隔离本机数据不代表生产迁移已完成。`"
      style="margin-bottom: 16px"
    />
    <WorkflowPanel v-if="isWorkbench" :refresh-key="workflowRefresh" />
    <a-alert
      v-if="isWorkbench"
      type="info"
      show-icon
      message="ADM第一版不提供站内消息、企业微信或其他主动通知；全部待办以本工作台实时任务为准。"
    />
    <div class="adm-metrics">
      <div v-for="item in metrics" :key="item.key">
        <span>{{ item.title }}</span
        ><strong>{{ summary[item.key] ?? '—' }}</strong>
      </div>
    </div>
    <div class="adm-toolbar adm-filter">
      <label
        >搜索<a-input
          v-model:value="search"
          placeholder="内部单号 / ADM / 订单 / 票号 / PNR / 备注"
          allow-clear
          @press-enter="query"
      /></label>
      <label
        >处理状态<a-select
          v-model:value="status"
          :options="[{ label: '全部状态', value: '' }, ...options(config?.caseStatuses)]"
      /></label>
      <label>数据范围<a-select v-model:value="scope" :options="scopes" disabled /></label>
      <label
        >业务大类<a-select
          v-model:value="businessCategory"
          :options="[
            { value: '', label: '全部' },
            { value: '0', label: '票务' },
            { value: '1', label: '业务' },
            { value: '2', label: '客服' },
          ]"
      /></label>
      <label>下发方编码<a-input v-model:value="supplierCode" allow-clear @press-enter="query" /></label>
      <a-button type="primary" :loading="loading" @click="query">查询</a-button>
      <a-button v-if="permission('import')" @click="importOpen = true">批量导入</a-button>
      <a-button v-if="isWorkbench && permission('handle')" @click="operatorOpen = true">操作人员离线处理</a-button>
      <a-button v-if="permission('export')" :loading="exporting" @click="startExport('adm_cases')">导出主单</a-button>
      <a-button v-if="permission('export')" :loading="exporting" @click="startExport('adm_lines')">导出明细</a-button>
      <a-button @click="downloadTemplate('daily19')">下载19列建单模板</a-button>
    </div>
    <p class="adm-muted">
      当前结果：{{ scopeLabel }} · {{ total }} 张 ADM。金额按原币种展示；明细及权限范围以服务端为准。
    </p>
    <a-table
      row-key="id"
      :columns="columns"
      :data-source="items"
      :loading="loading"
      :pagination="false"
      :scroll="{ x: 1910, y: 'calc(100vh - 440px)' }"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'internalNo'"
          ><router-link :to="`/adm/cases/${encodeURIComponent(record.id)}`">{{ record.internalNo }}</router-link
          ><span v-if="record.partial" class="adm-muted">（部分明细）</span></template
        >
        <template v-else-if="column.key === 'status'"
          ><a-tag>{{ label(record.status) }}</a-tag
          ><a-tag v-if="record.paused">已挂起</a-tag><a-tag v-if="record.voided">已作废</a-tag></template
        >
        <template v-else-if="column.key === 'amount'"
          ><span class="adm-money">{{ record.originalAmount ?? '—' }} {{ record.currency }}</span></template
        >
        <template v-else-if="column.key === 'progress'"
          ><span v-if="record.historicalArchive">原状态见档案</span
          ><span v-else>{{ record.completedCount ?? 0 }} / {{ record.lineCount ?? 0 }}</span></template
        >
        <template v-else-if="column.key === 'actions'"
          ><a-space
            ><router-link :to="`/adm/cases/${encodeURIComponent(record.id)}`" target="_blank" rel="noopener"
              >新标签查看</router-link
            ><a-button v-if="allowed(record, 'copy')" size="small" @click="openCopy(record)"
              >引用新建</a-button
            ></a-space
          ></template
        >
      </template>
      <template #emptyText
        ><a-empty :description="error ? '查询失败，请重试' : '当前范围没有 ADM，可调整筛选或新建主单'"
      /></template>
    </a-table>
    <div class="adm-pagination">
      <a-pagination
        v-model:current="page"
        v-model:page-size="pageSize"
        :total="total"
        :show-size-changer="true"
        :page-size-options="['20', '50', '100']"
        @change="load"
        @show-size-change="query"
      />
    </div>
    <div v-if="config" class="adm-capabilities">
      <span v-for="(title, key) in capabilityNames" :key="key"
        >{{ title }}：{{
          capabilityAvailable(config.capabilities?.[key])
            ? '已接入'
            : key === 'notifications'
              ? '待批准和部署（见运营面板）'
              : '未接入'
        }}</span
      >
    </div>
    <FormDialog
      v-model:open="createOpen"
      :title="copySource ? `引用 ${copySource.admNo} 新建` : '新建 ADM 主单'"
      :busy="saving"
      :dirty="createDirty"
      :error="createError"
      @submit="saveCreate"
    >
      <p v-if="copySource" class="adm-muted">引用基础信息，重新确认 ADM 号和金额；原单完成状态、附件事实不复制。</p>
      <CaseFields v-model="draft" />
      <InitialOrderLines v-model="initialLines" :currency="draft.currency || 'CNY'" :disabled="saving" />
    </FormDialog>
    <a-modal v-model:open="importOpen" title="批量导入 ADM" :width="900" :footer="null" :mask-closable="false">
      <p>日常建单使用19列单Sheet XLSX模板；管理员可上传ERP导出的JSON数组作为历史只读档案。均先预览再提交，不自动覆盖已有数据。</p>
      <a-space wrap
        ><a-button type="primary" @click="downloadTemplate('daily19')">19列日常建单模板</a-button
        ><a-button @click="downloadTemplate('center')">兼容双Sheet模板</a-button
        ><a-button @click="downloadTemplate('java44')">Java 44 列模板</a-button
        ><a-button @click="downloadTemplate('python38')">Python 38 列模板</a-button
        ><input type="file" accept=".xlsx,.json" aria-label="选择导入文件" @change="selectImport" /><a-button
          :loading="importBusy"
          :disabled="!importFile"
          @click="previewImport"
          >校验并预览</a-button
        ></a-space
      >
      <a-alert v-if="importError" type="error" :message="importError" style="margin-top: 12px" />
      <template v-if="importResult"
        ><p>文件 {{ importResult.rowCount }} 行，预览 {{ importResult.cases?.length ?? 0 }} 张主单。</p>
        <a-alert
          v-for="(item, i) in importResult.errors || []"
          :key="`e-${i}`"
          type="error"
          :message="`第 ${item.row} 行：${item.message}`"
        /><a-alert
          v-for="(item, i) in importResult.warnings || []"
          :key="`w-${i}`"
          type="warning"
          :message="typeof item === 'string' ? item : item.message"
        />
        <a-table
          row-key="admNo"
          :columns="importColumns"
          :data-source="importResult.cases || []"
          :pagination="{ pageSize: 5 }"
          :scroll="{ x: 650 }"
          size="small"
        />
        <a-button
          type="primary"
          :loading="importBusy"
          :disabled="!importResult.previewId || Boolean(importResult.errors?.length)"
          @click="commitImport"
          >确认导入</a-button
        >
      </template>
    </a-modal>
    <a-modal v-model:open="operatorOpen" title="操作人员34列离线处理" :width="920" :footer="null" :mask-closable="false">
      <p>只导出本人当前待处理订单。回导时重新校验归属、原状态、恢复阶段和数据版本；任何错误都会阻止本次确认。</p>
      <label>导出任务类型</label>
      <a-checkbox-group v-model:value="operatorStatuses" :options="operatorStatusOptions" style="display:block;margin:8px 0 16px" />
      <a-space wrap>
        <a-button type="primary" :loading="operatorBusy" :disabled="!operatorStatuses.length" @click="downloadOperatorWorkbook">导出34列任务</a-button>
        <input type="file" accept=".xlsx" aria-label="选择操作人员处理结果" @change="selectOperatorImport" />
        <a-button :loading="operatorBusy" :disabled="!operatorFile" @click="previewOperatorImport">校验并预览</a-button>
      </a-space>
      <a-alert v-if="operatorError" type="error" :message="operatorError" style="margin-top:12px" />
      <template v-if="operatorResult">
        <p>共 {{ operatorResult.rowCount }} 行；可提交 {{ operatorResult.readyCount }} 行；跳过 {{ operatorResult.skippedCount }} 行；错误 {{ operatorResult.errorCount }} 行。</p>
        <a-alert v-for="(item, index) in operatorResult.errors || []" :key="index" type="error" :message="`第 ${item.row} 行：${item.message}`" />
        <a-button type="primary" :loading="operatorBusy" :disabled="!operatorResult.previewId || operatorResult.errorCount > 0 || operatorResult.readyCount < 1" @click="commitOperatorImport">确认提交处理结果</a-button>
      </template>
    </a-modal>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import CaseFields from './CaseFields.vue'
import FormDialog from '@/components/FormDialog.vue'
import InitialOrderLines from './InitialOrderLines.vue'
import WorkflowPanel from './WorkflowPanel.vue'
import { createAdmKey } from './identifier'
import { admApi, allowed, errorText, label, options, saveBlob, type AdmCase, type AdmConfig, type Fields } from './api'
import './adm.css'
const auth = useAuthStore(),
  route = useRoute(),
  router = useRouter()
const permission = (name: string) => Boolean(auth.user?.isAdmin || auth.user?.permissions.includes(`adm.${name}`))
const exportStore = useComprehensiveExportStore()
const exporting = ref(false)
const workflowRefresh = ref(0)
const operatorOpen = ref(false),
  operatorBusy = ref(false),
  operatorFile = ref<File | null>(null),
  operatorError = ref(''),
  operatorResult = ref<Fields | null>(null),
  operatorStatuses = ref(['PENDING_CODE_PROCESSING', 'PENDING_DECISION', 'APPEAL_IN_PROGRESS', 'REJECTED_FOR_REVISION'])
const operatorStatusOptions = [
  { label: '待编码处理', value: 'PENDING_CODE_PROCESSING' },
  { label: '待决定', value: 'PENDING_DECISION' },
  { label: '申诉中', value: 'APPEAL_IN_PROGRESS' },
  { label: '驳回待修改', value: 'REJECTED_FOR_REVISION' },
]
async function downloadOperatorWorkbook() {
  operatorBusy.value = true
  operatorError.value = ''
  try {
    const task = await exportStore.createBackground('adm_operator_tasks', { statuses: operatorStatuses.value })
    message.success(task.reused ? '相同任务正在生成，已打开页头导出任务' : '已进入页头导出任务')
  } catch (cause) {
    operatorError.value = errorText(cause)
  } finally {
    operatorBusy.value = false
  }
}
function selectOperatorImport(event: Event) {
  operatorFile.value = (event.target as HTMLInputElement).files?.[0] || null
  operatorResult.value = null
  operatorError.value = ''
}
async function previewOperatorImport() {
  if (!operatorFile.value) return
  operatorBusy.value = true
  operatorError.value = ''
  try {
    operatorResult.value = await admApi.operatorImportPreview(operatorFile.value)
  } catch (cause) {
    operatorError.value = errorText(cause)
  } finally {
    operatorBusy.value = false
  }
}
async function commitOperatorImport() {
  if (!operatorResult.value?.previewId) return
  operatorBusy.value = true
  operatorError.value = ''
  try {
    const result = await admApi.operatorImportCommit(operatorResult.value.previewId)
    if (result.failedCount) throw new Error(`提交完成，但有 ${result.failedCount} 行因并发变化失败，请重新导出`)
    message.success(`已提交 ${result.successCount} 行，跳过 ${result.skippedCount} 行`)
    operatorOpen.value = false
    operatorFile.value = null
    operatorResult.value = null
    await load()
  } catch (cause) {
    operatorError.value = errorText(cause)
  } finally {
    operatorBusy.value = false
  }
}
async function startExport(kind: 'adm_cases' | 'adm_lines') {
  if (exporting.value) return
  exporting.value = true
  try {
    await exportStore.createBackground(kind, {
      activeOnly: isWorkbench.value,
      search: search.value,
      status: status.value,
      scope: scope.value,
      businessCategory: businessCategory.value,
      supplierCode: supplierCode.value,
    })
    message.success('已进入页头导出任务')
  } catch (cause) {
    message.error(errorText(cause))
  } finally {
    exporting.value = false
  }
}
const isWorkbench = computed(() => route.meta.admView === 'workbench')
const defaultScope = () => (isWorkbench.value ? 'mine' : 'all')
const config = ref<AdmConfig | null>(null),
  items = ref<AdmCase[]>([]),
  summary = ref<Fields>({}),
  loading = ref(false),
  error = ref('')
const search = ref(String(route.query.search || '')),
  businessCategory = ref(String(route.query.businessCategory || '')),
  supplierCode = ref(String(route.query.supplierCode || '')),
  status = ref(String(route.query.status || '')),
  scope = ref(defaultScope()),
  page = ref(1),
  pageSize = ref(20),
  total = ref(0)
const scopes = computed(() =>
  isWorkbench.value
    ? [{ value: 'mine', label: '分配给我的单' }]
    : [{ value: 'all', label: '全部单据（只读范围不等于操作权限）' }],
)
const scopeLabel = computed(() => scopes.value.find((item) => item.value === scope.value)?.label || '我的待办')
const metrics = [
  { key: 'cases', title: '范围内主单' },
  { key: 'lines', title: '订单明细' },
  { key: 'open', title: '未结案' },
  { key: 'overdue', title: '已超时' },
]
const capabilityNames = { orders: '订单查询', finance: '财务核验', notifications: '自动提醒' }
const capabilityAvailable = (value: any) => value === true || value?.available === true
const columns = [
  { title: '主单内部单号', key: 'internalNo', width: 210, fixed: 'left' as const },
  { title: '原ADM单号', dataIndex: 'admNo', width: 180 },
  { title: '下发方', dataIndex: 'supplierName', width: 170 },
  { title: '状态', key: 'status', width: 160 },
  { title: '下发金额', key: 'amount', width: 170, align: 'right' as const },
  { title: '完成 / 明细', key: 'progress', width: 120 },
  { title: '截止日期', dataIndex: 'deadline', width: 130 },
  { title: '问题描述', dataIndex: 'description', width: 260, ellipsis: true },
  { title: '备注', dataIndex: 'remark', width: 260, ellipsis: true },
  { title: '操作', key: 'actions', width: 230 },
]
let request = 0
async function load() {
  const seq = ++request
  loading.value = true
  error.value = ''
  try {
    const result = await admApi.list({
      activeOnly: isWorkbench.value,
      search: search.value,
      status: status.value,
      businessCategory: businessCategory.value,
      supplierCode: supplierCode.value,
      scope: scope.value,
      page: page.value,
      pageSize: pageSize.value,
    })
    if (seq !== request) return
    items.value = result.items
    total.value = result.pagination.total
    summary.value = result.summary
    workflowRefresh.value++
  } catch (cause) {
    if (seq === request) {
      error.value = errorText(cause)
      items.value = []
      total.value = 0
      summary.value = {}
    }
  } finally {
    if (seq === request) loading.value = false
  }
}
function query() {
  page.value = 1
  void router.replace({
    query: {
      search: search.value || undefined,
      status: status.value || undefined,
      scope: scope.value,
      businessCategory: businessCategory.value || undefined,
      supplierCode: supplierCode.value || undefined,
    },
  })
  void load()
}
const createOpen = ref(false),
  copySource = ref<AdmCase | null>(null),
  draft = ref<Fields>({}),
  initialLines = ref<Fields[]>([]),
  saving = ref(false),
  createError = ref('')
let createKey = ''
const createBaseline = ref('')
const createDirty = computed(() => JSON.stringify([draft.value, initialLines.value]) !== createBaseline.value)
function openCreate() {
  try {
    createKey = createAdmKey()
  } catch (cause) {
    message.error(errorText(cause))
    return
  }
  copySource.value = null
  initialLines.value = []
  draft.value = {
    supplierType: 'SUPPLIER',
    currency: 'CNY',
    originalAmount: '',
    admNo: '',
    supplierName: '',
    analysis: {},
  }
  createError.value = ''
  createBaseline.value = JSON.stringify([draft.value, initialLines.value])
  createOpen.value = true
}
function openCopy(source: AdmCase) {
  openCreate()
  copySource.value = source
  draft.value = {
    ...draft.value,
    supplierName: source.supplierName,
    supplierType: source.supplierType,
    currency: source.currency,
    description: source.description,
    remark: source.remark,
  }
  createBaseline.value = JSON.stringify([draft.value, initialLines.value])
}
async function saveCreate() {
  if (saving.value) return
  if (
    !draft.value.admNo?.trim() ||
    !draft.value.supplierName?.trim() ||
    !draft.value.currency ||
    !/^[-+]?\d+(\.\d+)?$/.test(String(draft.value.originalAmount))
  ) {
    createError.value = '请填写 ADM 号、下发方、币种和有效十进制金额。'
    return
  }
  const emptyIndex = initialLines.value.findIndex(
    (line) => ![line.orderNo, line.ticketNo, line.pnr, line.description].some((value) => String(value || '').trim()),
  )
  if (emptyIndex >= 0) {
    createError.value = `订单 ${emptyIndex + 1} 请填写订单号、票号、PNR或问题说明，或者移除空白订单。`
    return
  }
  saving.value = true
  createError.value = ''
  try {
    const body = {
      ...draft.value,
      lines: initialLines.value.map((line) => {
        const value: Fields = { ...line, currency: line.currency || draft.value.currency }
        delete value._draftKey
        return value
      }),
      idempotencyKey: createKey,
      ...(copySource.value ? { version: copySource.value.version } : {}),
    }
    const created = copySource.value ? await admApi.copy(copySource.value.id, body) : await admApi.create(body)
    createOpen.value = false
    message.success(`主单及 ${created.lines?.length || 0} 条订单已保存`)
    await router.push(`/adm/cases/${encodeURIComponent(created.id)}`)
  } catch (cause) {
    createError.value = errorText(cause)
  } finally {
    saving.value = false
  }
}
async function downloadTemplate(format: string) {
  try {
    const result = await admApi.template(format)
    saveBlob(result.data, `ADM-${format}.xlsx`)
  } catch (cause) {
    message.error(errorText(cause))
  }
}
const importOpen = ref(false),
  importFile = ref<File | null>(null),
  importBusy = ref(false),
  importError = ref(''),
  importResult = ref<Fields | null>(null)
let importKey = ''
const importColumns = [
  { title: 'ADM 号', dataIndex: 'admNo' },
  { title: '下发方', dataIndex: 'supplierName' },
  { title: '明细数量', dataIndex: 'lineCount' },
]
function selectImport(event: Event) {
  importFile.value = (event.target as HTMLInputElement).files?.[0] || null
  importResult.value = null
  importError.value = ''
}
async function previewImport() {
  if (!importFile.value || importBusy.value) return
  importBusy.value = true
  importError.value = ''
  importResult.value = null
  try {
    importKey = createAdmKey()
    importResult.value = await admApi.importPreview(importFile.value)
  } catch (cause) {
    importError.value = errorText(cause)
  } finally {
    importBusy.value = false
  }
}
async function commitImport() {
  if (!importResult.value?.previewId || importBusy.value) return
  importBusy.value = true
  importError.value = ''
  try {
    const result = await admApi.importCommit(importResult.value.previewId, importKey)
    if (result.failedCount) {
      importError.value = `成功 ${result.successCount} 张，失败 ${result.failedCount} 张。${(result.items || [])
        .filter((item: Fields) => item.status === 'FAILED')
        .slice(0, 5)
        .map((item: Fields) => `${item.admNo}: ${item.message}`)
        .join('；')}。已成功主单不会重复创建，可修正问题后重试。`
      return
    }
    importResult.value = null
    importOpen.value = false
    message.success(result.notice || `已建档 ${result.successCount} 张 ADM；请补充供应原件并核实后发布`)
    await load()
  } catch (cause) {
    importError.value = errorText(cause)
  } finally {
    importBusy.value = false
  }
}
watch(
  () => route.meta.admView,
  () => {
    scope.value = defaultScope()
    query()
  },
)
watch(
  () => auth.user?.id,
  () => {
    items.value = []
    summary.value = {}
    createOpen.value = false
    importOpen.value = false
    request++
    config.value = null
    void loadConfig()
    void load()
  },
)
let configRequest = 0
async function loadConfig() {
  const seq = ++configRequest
  try {
    const result = await admApi.config()
    if (seq === configRequest) config.value = result
  } catch (cause) {
    if (seq === configRequest) error.value = errorText(cause)
  }
}
void loadConfig()
void load()
onBeforeUnmount(() => {
  request++
  configRequest++
})
</script>
