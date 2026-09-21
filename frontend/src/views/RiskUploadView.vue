<template>
  <div class="page-wrap risk-upload-page">
    <PageHeader eyebrow="RISK CONTROL DATA" title="风控数据上传" description="上传出票、退票、改签利润核对Excel，校验通过后写入Hive">
      <a-tag color="purple">异步任务 · Hive</a-tag>
    </PageHeader>

    <a-alert
      class="page-alert"
      type="warning"
      show-icon
      message="出、退、改均按出票票号增量更新"
      description="新票号新增，已有票号整行替换；上传记录的预估利润为0时作为删除指令。系统校验票号唯一性及合并结果后才重写对应Hive正式表，利润为空不会当作0。"
    />
    <a-alert v-if="error" class="page-alert" type="error" show-icon :message="error" />

    <section v-if="data?.tokenRequired" class="token-panel">
      <div><strong>导入口令</strong><span>口令只用于本次浏览器会话，不写入任务记录。</span></div>
      <a-input-password v-model:value="token" placeholder="请输入.env中的RISK_UPLOAD_TOKEN" @press-enter="refresh" />
      <a-button :loading="loading" @click="refresh">验证并刷新</a-button>
    </section>

    <div class="upload-grid">
      <a-card v-for="definition in data?.definitions || []" :key="definition.key" :bordered="false" class="upload-card">
        <template #title><div class="card-title"><span class="type-icon"><FileExcelOutlined /></span><div><strong>{{ definition.label }}数据</strong><small>{{ definition.writeMode }}</small></div></div></template>
        <div class="target-table"><span>Hive目标表</span><code>{{ definition.targetTable }}</code></div>
        <label class="form-field"><span>Excel文件</span>
          <input type="file" accept=".xlsx,.xlsm" :disabled="submitting[definition.key]" @change="chooseFile(definition.key, $event)" />
          <small>{{ files[definition.key]?.name || `仅支持.xlsx/.xlsm，最大${data?.maxFileSizeMb || 200}MB` }}</small>
        </label>
        <label class="form-field"><span>工作表名称</span><a-input v-model:value="forms[definition.key].sheetName" :disabled="submitting[definition.key]" /></label>
        <label v-if="definition.requiresLoadDate" class="form-field"><span>出票表dt分区</span><a-date-picker v-model:value="forms[definition.key].loadDate" value-format="YYYY-MM-DD" :allow-clear="false" :disabled="submitting[definition.key]" /></label>
        <a-progress v-if="submitting[definition.key]" :percent="progress[definition.key]" size="small" />
        <a-button type="primary" block :loading="submitting[definition.key]" :disabled="!data?.enabled || !files[definition.key]" @click="confirmSubmit(definition)">
          <CloudUploadOutlined />上传并进入Hive导入队列
        </a-button>
      </a-card>
    </div>

    <a-card :bordered="false" class="jobs-panel">
      <template #title><div class="panel-title"><div><strong>最近导入任务</strong><small>上传文件处理完成后自动删除，仅保留哈希、行数和脱敏日志</small></div><a-button :loading="loading" @click="refresh"><ReloadOutlined />刷新</a-button></div></template>
      <a-alert v-if="data?.tokenRequired && !data.historyAuthorized" type="info" show-icon message="输入正确导入口令后可查看任务历史。" />
      <a-table v-else :columns="columns" :data-source="data?.jobs || []" row-key="id" :pagination="{ pageSize: 10 }" :scroll="{ x: 1100 }" :locale="{ emptyText: '暂无上传任务' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'business'">{{ businessLabel(record.businessType) }}</template>
          <template v-else-if="column.key === 'file'"><div class="file-cell"><strong>{{ record.originalName }}</strong><small>{{ fileSize(record.fileSize) }} · SHA256 {{ record.fileSha256.slice(0, 12) }}…</small></div></template>
          <template v-else-if="column.key === 'scope'"><span>{{ record.sheetName }}</span><small v-if="record.loadDate" class="block-note">dt={{ record.loadDate }}</small></template>
          <template v-else-if="column.key === 'status'"><a-tag :color="statusMeta(record.status).color">{{ statusMeta(record.status).label }}</a-tag></template>
          <template v-else-if="column.key === 'rows'">{{ record.rowsWritten == null ? '—' : count(record.rowsWritten) + ' 行' }}</template>
          <template v-else-if="column.key === 'time'"><span>{{ record.finishedAt || record.startedAt || record.queuedAt }}</span></template>
          <template v-else-if="column.key === 'action'"><a-button type="link" size="small" @click="selectedJob = record">查看日志</a-button></template>
        </template>
      </a-table>
    </a-card>

    <a-drawer :open="Boolean(selectedJob)" title="Hive导入任务详情" :width="'min(720px, 100vw)'" @close="selectedJob = undefined">
      <template v-if="selectedJob">
        <a-descriptions bordered size="small" :column="1">
          <a-descriptions-item label="状态"><a-tag :color="statusMeta(selectedJob.status).color">{{ statusMeta(selectedJob.status).label }}</a-tag></a-descriptions-item>
          <a-descriptions-item label="目标表">{{ selectedJob.targetTable }}</a-descriptions-item>
          <a-descriptions-item label="文件">{{ selectedJob.originalName }}</a-descriptions-item>
          <a-descriptions-item label="结果">{{ selectedJob.message || '等待Worker处理' }}</a-descriptions-item>
        </a-descriptions>
        <pre class="task-log">{{ selectedJob.logs.length ? selectedJob.logs.join('\n') : '暂无运行日志' }}</pre>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { CloudUploadOutlined, FileExcelOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { createRiskUpload, getRiskUploads, type RiskUploadBusiness, type RiskUploadData, type RiskUploadDefinition, type RiskUploadJob, type RiskUploadStatus } from '@/api/riskUpload'

function businessToday() { return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }) }
const data = ref<RiskUploadData>()
const loading = ref(false)
const error = ref('')
const token = ref(sessionStorage.getItem('risk-upload-token') || '')
const selectedJob = ref<RiskUploadJob>()
const files = reactive<Record<RiskUploadBusiness, File | null>>({ issue: null, refund: null, change: null })
const forms = reactive<Record<RiskUploadBusiness, { sheetName: string; loadDate: string }>>({
  issue: { sheetName: '', loadDate: businessToday() },
  refund: { sheetName: '', loadDate: '' },
  change: { sheetName: '', loadDate: '' },
})
const submitting = reactive<Record<RiskUploadBusiness, boolean>>({ issue: false, refund: false, change: false })
const progress = reactive<Record<RiskUploadBusiness, number>>({ issue: 0, refund: 0, change: 0 })
let pollTimer: number | undefined

const columns = [
  { title: '业务', key: 'business', width: 80, fixed: 'left' as const },
  { title: '文件', key: 'file', width: 230 },
  { title: '工作表 / 分区', key: 'scope', width: 180 },
  { title: '状态', key: 'status', width: 100 },
  { title: '写入行数', key: 'rows', width: 110 },
  { title: '状态时间', key: 'time', width: 190 },
  { title: '结果', dataIndex: 'message', key: 'message', width: 260 },
  { title: '操作', key: 'action', width: 90, fixed: 'right' as const },
]

const statusMap: Record<RiskUploadStatus, { label: string; color: string }> = {
  queued: { label: '排队中', color: 'default' },
  running: { label: '导入中', color: 'processing' },
  success: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
}
const statusMeta = (status: RiskUploadStatus) => statusMap[status]
const businessLabel = (key: RiskUploadBusiness) => data.value?.definitions.find(item => item.key === key)?.label || key
const count = (value: number) => new Intl.NumberFormat('zh-CN').format(value)
const fileSize = (value: number) => value < 1024 * 1024 ? `${(value / 1024).toFixed(1)}KB` : `${(value / 1024 / 1024).toFixed(1)}MB`

function chooseFile(key: RiskUploadBusiness, event: Event) {
  files[key] = (event.target as HTMLInputElement).files?.[0] || null
}

function confirmSubmit(definition: RiskUploadDefinition) {
  const file = files[definition.key]
  if (!file) { message.warning(`请选择${definition.label}Excel文件`); return }
  if (data.value && file.size > data.value.maxFileSizeMb * 1024 * 1024) { message.error(`文件不能超过${data.value.maxFileSizeMb}MB`); return }
  if (!forms[definition.key].sheetName.trim()) { message.warning('请填写工作表名称'); return }
  if (definition.requiresLoadDate && !forms[definition.key].loadDate) { message.warning('请选择出票表dt分区日期'); return }
  Modal.confirm({
    title: `确认增量导入${definition.label}数据？`,
    content: `文件“${file.name}”将按出票票号与${definition.targetTable}合并：新票号新增，已有票号整行替换，预估利润为0的票号删除。`,
    okText: '确认增量导入',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => submit(definition),
  })
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    sessionStorage.setItem('risk-upload-token', token.value)
    const result = await getRiskUploads(token.value)
    data.value = result
    for (const definition of result.definitions) {
      if (!forms[definition.key].sheetName) forms[definition.key].sheetName = definition.defaultSheet
    }
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : '上传任务状态查询失败'
  } finally {
    loading.value = false
  }
}

async function submit(definition: RiskUploadDefinition) {
  const file = files[definition.key]
  if (!file) { message.warning(`请选择${definition.label}Excel文件`); return }
  if (data.value && file.size > data.value.maxFileSizeMb * 1024 * 1024) { message.error(`文件不能超过${data.value.maxFileSizeMb}MB`); return }
  if (!forms[definition.key].sheetName.trim()) { message.warning('请填写工作表名称'); return }
  if (definition.requiresLoadDate && !forms[definition.key].loadDate) { message.warning('请选择出票表dt分区日期'); return }
  submitting[definition.key] = true
  progress[definition.key] = 0
  try {
    await createRiskUpload(definition, file, forms[definition.key].sheetName, forms[definition.key].loadDate, token.value, value => { progress[definition.key] = value })
    files[definition.key] = null
    message.success(`${definition.label}文件上传成功，已进入Hive导入队列`)
    await refresh()
  } catch (failure) {
    message.error(failure instanceof Error ? failure.message : '文件上传失败')
  } finally {
    submitting[definition.key] = false
  }
}

onMounted(() => {
  void refresh()
  pollTimer = window.setInterval(() => {
    if (!loading.value && data.value?.jobs.some(job => job.status === 'queued' || job.status === 'running')) void refresh()
  }, 3000)
})
onBeforeUnmount(() => { if (pollTimer) window.clearInterval(pollTimer) })
</script>

<style scoped>
.risk-upload-page { padding-bottom: 32px; }
.page-alert { margin-bottom: 16px; border-radius: 10px; }
.token-panel { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(260px, 420px) auto; gap: 14px; align-items: center; margin-bottom: 16px; padding: 15px 18px; border: 1px solid #e3e8f0; border-radius: 12px; background: #fff; }
.token-panel > div { display: grid; gap: 3px; }
.token-panel span { color: #8a95a7; font-size: 11px; }
.upload-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.upload-card { border: 1px solid #e4e9f1 !important; border-radius: 13px; box-shadow: 0 8px 24px rgba(31, 49, 77, .05); }
.card-title { display: flex; align-items: center; gap: 10px; }
.card-title > div { display: grid; gap: 2px; }
.card-title small { color: #8e99aa; font-size: 10px; font-weight: 400; }
.type-icon { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 9px; color: #fff; background: #4a79d8; }
.target-table { display: grid; gap: 6px; margin-bottom: 17px; padding: 11px 12px; border-radius: 9px; background: #f6f8fb; }
.target-table span, .form-field > span { color: #6e7b90; font-size: 11px; }
.target-table code { overflow-wrap: anywhere; color: #526079; font-size: 11px; }
.form-field { display: grid; gap: 7px; margin-bottom: 15px; }
.form-field input[type='file'] { width: 100%; padding: 9px; border: 1px dashed #cfd7e4; border-radius: 8px; color: #59677d; background: #fafbfd; font-size: 11px; }
.form-field small { overflow: hidden; color: #929cad; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.form-field :deep(.ant-picker) { width: 100%; }
.jobs-panel { border: 1px solid #e5eaf1 !important; border-radius: 13px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.panel-title > div { display: grid; gap: 2px; }
.panel-title small { color: #8d98aa; font-size: 10px; font-weight: 400; }
.file-cell { display: grid; gap: 3px; }
.file-cell strong { overflow: hidden; max-width: 210px; text-overflow: ellipsis; white-space: nowrap; }
.file-cell small, .block-note { color: #929daf; font-size: 10px; }
.block-note { display: block; margin-top: 3px; }
.task-log { min-height: 180px; margin-top: 18px; padding: 14px; overflow: auto; border-radius: 9px; color: #d8e0ec; background: #172033; font: 11px/1.7 Consolas, monospace; white-space: pre-wrap; }
@media (max-width: 1100px) { .upload-grid { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .token-panel { grid-template-columns: 1fr; } }
</style>
