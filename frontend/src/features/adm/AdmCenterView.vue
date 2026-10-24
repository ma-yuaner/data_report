<template>
  <div class="adm-center">
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
          placeholder="ADM / 订单 / 票号 / PNR / 备注"
          allow-clear
          @press-enter="query"
      /></label>
      <label
        >处理状态<a-select
          v-model:value="status"
          :options="[{ label: '全部状态', value: '' }, ...options(config?.caseStatuses)]"
      /></label>
      <label>数据范围<a-select v-model:value="scope" :options="scopes" /></label>
      <a-button type="primary" :loading="loading" @click="query">查询</a-button>
      <a-button v-if="permission('import')" @click="importOpen = true">批量导入</a-button>
      <a-button v-if="permission('export')" :loading="exporting" @click="startExport('adm_cases')">导出主单</a-button>
      <a-button v-if="permission('export')" :loading="exporting" @click="startExport('adm_lines')">导出明细</a-button>
      <a-button @click="downloadTemplate('center')">下载统一模板</a-button>
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
      :scroll="{ x: 1730, y: 'calc(100vh - 440px)' }"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'admNo'"
          ><router-link :to="`/adm/cases/${encodeURIComponent(record.id)}`">{{ record.admNo }}</router-link
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
          >{{ record.completedCount ?? 0 }} / {{ record.lineCount ?? 0 }}</template
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
        >{{ title }}：{{ capabilityAvailable(config.capabilities?.[key]) ? '已接入' : '未接入' }}</span
      >
    </div>
    <a-modal
      v-model:open="createOpen"
      :title="copySource ? `引用 ${copySource.admNo} 新建` : '新建 ADM 主单'"
      :width="800"
      :confirm-loading="saving"
      :mask-closable="false"
      @ok="saveCreate"
    >
      <a-alert v-if="createError" type="error" :message="createError" show-icon style="margin-bottom: 12px" />
      <p v-if="copySource" class="adm-muted">引用基础信息，重新确认 ADM 号和金额；原单完成状态、附件事实不复制。</p>
      <CaseFields v-model="draft" />
    </a-modal>
    <a-modal v-model:open="importOpen" title="批量导入 ADM" :width="900" :footer="null" :mask-closable="false">
      <p>先预览再提交。首版新增主单及明细；已有单冲突将退回，不自动覆盖人工备注。</p>
      <a-space wrap
        ><a-button @click="downloadTemplate('center')">统一模板</a-button
        ><a-button @click="downloadTemplate('java44')">Java 44 列模板</a-button
        ><a-button @click="downloadTemplate('python38')">Python 38 列模板</a-button
        ><input type="file" accept=".xlsx,.csv" aria-label="选择导入文件" @change="selectImport" /><a-button
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
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import CaseFields from './CaseFields.vue'
import { admApi, allowed, errorText, label, options, saveBlob, type AdmCase, type AdmConfig, type Fields } from './api'
import './adm.css'
const auth = useAuthStore(),
  route = useRoute(),
  router = useRouter()
const permission = (name: string) => Boolean(auth.user?.isAdmin || auth.user?.permissions.includes(`adm.${name}`))
const exportStore = useComprehensiveExportStore()
const exporting = ref(false)
async function startExport(kind: 'adm_cases' | 'adm_lines') {
  if (exporting.value) return
  exporting.value = true
  try {
    await exportStore.createBackground(kind, { search: search.value, status: status.value, scope: scope.value })
    message.success('已进入页头导出任务')
  } catch (cause) {
    message.error(errorText(cause))
  } finally {
    exporting.value = false
  }
}
const isWorkbench = computed(() => route.meta.admView === 'workbench')
const config = ref<AdmConfig | null>(null),
  items = ref<AdmCase[]>([]),
  summary = ref<Fields>({}),
  loading = ref(false),
  error = ref('')
const search = ref(String(route.query.search || '')),
  status = ref(String(route.query.status || '')),
  scope = ref(String(route.query.scope || 'mine')),
  page = ref(1),
  pageSize = ref(20),
  total = ref(0)
const scopes = computed(() => [
  { value: 'mine', label: '我的待办' },
  ...(permission('scope.team') ? [{ value: 'team', label: '管理团队' }] : []),
  ...(permission('scope.all') ? [{ value: 'all', label: '全部' }] : []),
])
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
  { title: 'ADM 单号', key: 'admNo', width: 200, fixed: 'left' as const },
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
      search: search.value,
      status: status.value,
      scope: scope.value,
      page: page.value,
      pageSize: pageSize.value,
    })
    if (seq !== request) return
    items.value = result.items
    total.value = result.pagination.total
    summary.value = result.summary
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
    query: { search: search.value || undefined, status: status.value || undefined, scope: scope.value },
  })
  void load()
}
const createOpen = ref(false),
  copySource = ref<AdmCase | null>(null),
  draft = ref<Fields>({}),
  saving = ref(false),
  createError = ref('')
let createKey = ''
function openCreate() {
  copySource.value = null
  draft.value = {
    supplierType: 'SUPPLIER',
    currency: 'CNY',
    originalAmount: '',
    admNo: '',
    supplierName: '',
    analysis: {},
  }
  createError.value = ''
  createKey = crypto.randomUUID()
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
  saving.value = true
  createError.value = ''
  try {
    const body = {
      ...draft.value,
      idempotencyKey: createKey,
      ...(copySource.value ? { version: copySource.value.version } : {}),
    }
    const created = copySource.value ? await admApi.copy(copySource.value.id, body) : await admApi.create(body)
    createOpen.value = false
    message.success('主单已保存')
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
    importResult.value = await admApi.importPreview(importFile.value)
    importKey = crypto.randomUUID()
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
    message.success(`已建档 ${result.successCount} 张 ADM；请补充供应原件并核实后发布`)
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
    scope.value = String(route.query.scope || 'mine')
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
    void load()
  },
)
void admApi
  .config()
  .then((result) => {
    config.value = result
  })
  .catch((cause) => {
    error.value = errorText(cause)
  })
void load()
onBeforeUnmount(() => {
  request++
})
</script>
