<template>
  <section>
    <div class="adm-toolbar">
      <strong>附件与原件（{{ attachments.length }}）</strong>
      <template v-if="canUpload">
        <a-select v-model:value="category" aria-label="附件类别" :options="categories" style="min-width: 145px" />
        <a-select v-model:value="lineId" aria-label="附件归属" :options="lineOptions" style="min-width: 190px" />
        <label class="adm-file-label">选择文件<input ref="fileInput" type="file" @change="selectFile" /></label>
        <span>{{ selectedFile?.name || '尚未选择文件' }}</span>
        <a-button :loading="uploading" :disabled="!selectedFile" @click="upload">上传附件</a-button>
      </template>
    </div>
    <a-alert v-if="error" type="error" :message="error" show-icon style="margin: 12px 0" />
    <p class="adm-muted">主单原件可供有权限的明细共同引用；历史材料保留，附件访问由服务端逐次鉴权。</p>
    <a-table
      row-key="id"
      :data-source="attachments"
      :columns="columns"
      :pagination="false"
      :scroll="{ x: 820, y: 300 }"
      size="small"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'category'">{{ categoryLabel(record.category) }}</template>
        <template v-if="column.key === 'lineId'">{{ record.lineId ? lineName(record.lineId) : '主单材料' }}</template>
        <template v-if="column.key === 'actions'">
          <a-space
            ><a-button size="small" @click="preview(record)">预览</a-button
            ><a-button size="small" @click="download(record)">下载</a-button></a-space
          >
        </template>
      </template>
    </a-table>
    <a-modal v-model:open="previewOpen" :title="previewName" :footer="null" :width="1000" @after-close="clearPreview">
      <a-spin :spinning="previewLoading">
        <a-alert v-if="previewError" type="warning" :message="previewError" show-icon />
        <img
          v-if="previewUrl && previewKind === 'image'"
          :src="previewUrl"
          :alt="previewName"
          class="adm-image-preview"
        />
        <iframe
          v-if="previewUrl && previewKind === 'pdf'"
          :src="previewUrl"
          :title="previewName"
          class="adm-pdf-preview"
        />
        <template v-if="tablePreview">
          <p>只读表格预览 · {{ tablePreview.sheet || '' }} · 最多 200 行、50 列；完整内容请下载。</p>
          <a-alert v-if="tablePreview.truncated" type="info" message="文件较大，当前预览已截断，不代表完整文件。" />
          <div class="adm-sheet-preview" tabindex="0" aria-label="附件只读表格，可横向滚动">
            <table>
              <thead>
                <tr>
                  <th v-for="(cell, index) in tablePreview.columns" :key="index">{{ cell }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in tablePreview.rows" :key="index">
                  <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
        <pre v-if="textPreview" class="adm-prose">{{ textPreview }}</pre>
      </a-spin>
    </a-modal>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  admApi,
  errorText,
  options,
  saveBlob,
  type AdmAttachment,
  type AdmCase,
  type AdmConfig,
  type Fields,
} from './api'
const props = defineProps<{ record: AdmCase; config: AdmConfig | null; canUpload: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const attachments = computed(() => props.record.attachments || [])
const category = ref('ORIGINAL'),
  lineId = ref(''),
  selectedFile = ref<File | null>(null),
  uploading = ref(false),
  error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const categoryLabels: Record<string, string> = {
  ORIGINAL: '下发原件',
  VERIFICATION: '核实材料',
  RECOVERY: '编码恢复',
  APPEAL: '申诉材料',
  FINANCE: '财务凭证',
  ANALYSIS: '分析材料',
}
const categories = computed(() =>
  options(props.config?.attachmentCategories, Object.keys(categoryLabels)).map((item) => ({
    ...item,
    label: categoryLabels[item.value] || item.label,
  })),
)
const lineOptions = computed(() => [
  { value: '', label: '主单材料（原件共享）' },
  ...(props.record.lines || []).map((line) => ({
    value: line.id,
    label: `${line.platform || '待核实平台'} · ${line.orderNo || line.id}`,
  })),
])
const categoryLabel = (value: string) => categoryLabels[value] || value
const lineName = (id: string) => lineOptions.value.find((item) => item.value === id)?.label || id
const columns = [
  { title: '文件名', dataIndex: 'name', width: 240 },
  { title: '类别', key: 'category', width: 110 },
  { title: '归属', key: 'lineId', width: 190 },
  { title: '上传时间', dataIndex: 'createdAt', width: 180 },
  { title: '操作', key: 'actions', width: 150 },
]
const selectFile = (event: Event) => {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] || null
}
async function upload() {
  if (!selectedFile.value || uploading.value) return
  uploading.value = true
  error.value = ''
  try {
    await admApi.upload(props.record.id, selectedFile.value, props.record.version, category.value, lineId.value)
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    emit('changed')
  } catch (cause) {
    error.value = errorText(cause)
  } finally {
    uploading.value = false
  }
}
const previewOpen = ref(false),
  previewLoading = ref(false),
  previewName = ref(''),
  previewUrl = ref(''),
  previewKind = ref(''),
  previewError = ref(''),
  tablePreview = ref<Fields | null>(null)
const textPreview = ref('')
let previewRequest = 0
function clearPreview() {
  previewRequest += 1
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  tablePreview.value = null
  textPreview.value = ''
  previewKind.value = ''
  previewLoading.value = false
}
async function preview(file: AdmAttachment) {
  clearPreview()
  previewOpen.value = true
  previewName.value = file.name
  previewError.value = ''
  previewLoading.value = true
  const request = ++previewRequest
  try {
    const { data: blob, headers } = await admApi.file(props.record.id, file.id, 'preview')
    if (request !== previewRequest || !previewOpen.value) return
    const mime = String(headers['content-type'] || blob.type)
    if (mime.includes('json')) {
      const result = JSON.parse(await blob.text())
      if (request !== previewRequest || !previewOpen.value) return
      const table = result.data || result
      if (table.type === 'text')
        textPreview.value = table.text + (table.truncated ? '\n（文本预览已截断，请下载原件）' : '')
      else if (table.type === 'table') tablePreview.value = table
      else throw new Error(table.message || result.message || '此附件暂不支持在线预览，请下载查看')
    } else if (mime.startsWith('image/') || mime.includes('pdf')) {
      previewKind.value = mime.startsWith('image/') ? 'image' : 'pdf'
      previewUrl.value = URL.createObjectURL(blob)
    } else {
      previewError.value = '此格式不支持在线预览，请下载查看。'
    }
  } catch (cause) {
    if (request === previewRequest) previewError.value = errorText(cause)
  } finally {
    if (request === previewRequest) previewLoading.value = false
  }
}
async function download(file: AdmAttachment) {
  try {
    const response = await admApi.file(props.record.id, file.id, 'download')
    saveBlob(response.data, file.name)
  } catch (cause) {
    error.value = errorText(cause)
  }
}
watch(
  () => props.record.id,
  () => {
    previewOpen.value = false
    clearPreview()
    selectedFile.value = null
    error.value = ''
    lineId.value = ''
  },
)
watch(previewOpen, (open) => {
  if (!open) clearPreview()
})
onBeforeUnmount(clearPreview)
</script>
