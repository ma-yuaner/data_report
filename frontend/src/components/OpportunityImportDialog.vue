<template>
  <a-modal :open="open" title="批量新建分析机会" width="min(1000px, calc(100vw - 32px))" :mask-closable="false" :closable="!busy" :keyboard="!busy" @cancel="close">
    <div class="import-content">
      <a-alert type="info" show-icon message="只新增分析机会" description="不支持覆盖已有机会，不导入审核、认领、投放登记或后续修改。整批校验通过后才能确认。" />
      <a-space wrap class="import-controls">
        <a-button :loading="downloading" :disabled="busy" @click="download">下载示例模板</a-button>
        <input ref="fileInput" class="file-input" type="file" accept=".xlsx" :disabled="busy" aria-label="选择分析机会Excel" @change="selectFile" />
        <a-button :disabled="busy" @click="fileInput?.click()">选择文件</a-button>
        <span>{{ file?.name || '每次最多200行，.xlsx文件不超过2MB' }}</span>
      </a-space>
      <a-alert type="warning" show-icon message="模板第2行是完整填写示例，请先替换或删除再导入" description="多选字段用英文逗号（,）分隔，如 Y,B,M 或 平台手工订单,直连订单；逐字段要求见模板的填写说明。" />
      <div class="import-mode">
        <span>导入方式：</span>
        <a-radio-group v-model:value="submit" :disabled="busy || !!result" @change="invalidate">
          <a-radio :value="false">保存为草稿</a-radio>
          <a-radio :value="true">提交数据审核</a-radio>
        </a-radio-group>
      </div>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-alert v-if="result" type="success" show-icon :message="result.alreadyImported ? `该批次已导入，共${result.count}条，本次未重复新建` : `已成功新建${result.count}条分析机会`" description="请在任务列表查看。后续仍按现有流程操作。" />
      <template v-else-if="preview">
        <a-alert :type="preview.errors.length ? 'error' : 'success'" show-icon :message="`共${preview.total}条，${preview.errors.length}条错误`" :description="preview.errors.length ? '整批尚未写入，请按行号修改文件后重新校验。' : `将${preview.submit ? '新建并进入数据经理审核' : '新建为草稿'}；请核对预览，再确认导入。预览30分钟内有效。`" />
        <a-table v-if="preview.errors.length" size="small" row-key="line" :columns="errorColumns" :data-source="preview.errors" :pagination="false" :scroll="{ y: 160 }" />
        <a-table size="small" row-key="line" :columns="columns" :data-source="preview.rows" :pagination="{ pageSize: 10, showSizeChanger: false }" :scroll="{ x: 1150, y: 280 }">
          <template #expandedRowRender="{ record }">
            <a-descriptions size="small" bordered :column="2">
              <a-descriptions-item v-for="field in preview.fields" :key="field.key" :label="field.title"><span class="full-value">{{ display(record[field.key]) }}</span></a-descriptions-item>
            </a-descriptions>
          </template>
        </a-table>
      </template>
      <a-table v-if="result" size="small" row-key="id" :columns="resultColumns" :data-source="result.rows" :pagination="{ pageSize: 10, showSizeChanger: false }" :scroll="{ y: 260 }" />
    </div>
    <template #footer>
      <a-button :disabled="busy" @click="close">{{ result ? '完成' : '取消' }}</a-button>
      <template v-if="!result">
        <a-button :disabled="!file || busy" :loading="checking" @click="check">校验并预览</a-button>
        <a-button type="primary" :disabled="!preview?.token || !!preview.errors.length || busy" :loading="saving" @click="confirm">确认导入{{ preview?.total ? ` ${preview.total} 条` : '' }}</a-button>
      </template>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Modal } from 'ant-design-vue'
import { confirmOpportunityImport, downloadOpportunityTemplate, previewOpportunityImport, type OpportunityImportPreview, type OpportunityImportResult } from '@/api/placementImport'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; imported: [] }>()
const fileInput = ref<HTMLInputElement>()
const file = ref<File>()
const submit = ref(false)
const checking = ref(false)
const saving = ref(false)
const downloading = ref(false)
const preview = ref<OpportunityImportPreview>()
const result = ref<OpportunityImportResult>()
const error = ref('')
const busy = computed(() => checking.value || saving.value)
const errorColumns = [{ title: 'Excel行号', dataIndex: 'line', width: 100 }, { title: '错误原因', dataIndex: 'message' }]
const columns = [
  { title: '行号', dataIndex: 'line', width: 65 }, { title: '机会名称', dataIndex: 'opportunityName', width: 220 },
  { title: '平台', dataIndex: 'platformName', width: 120 }, { title: '航司', dataIndex: 'airlineCode', width: 75 },
  { title: '出发类型', dataIndex: 'departureType', width: 100 }, { title: '出发代码', dataIndex: 'departureCode', width: 100 },
  { title: '到达类型', dataIndex: 'arrivalType', width: 100 }, { title: '到达代码', dataIndex: 'arrivalCode', width: 100 },
  { title: '建议投放方式', dataIndex: 'placementMethod', width: 240 },
]
const statusLabels: Record<string, string> = { DRAFT: '草稿', PENDING_DATA_REVIEW: '待数据审核' }
const resultColumns = [{ title: '任务编号', dataIndex: 'taskNo' }, { title: '当前状态', dataIndex: 'status', customRender: ({ text }: { text: string }) => statusLabels[text] || text }]
const display = (value: unknown) => value === true ? '是' : value === false ? '否' : value === undefined || value === '' ? '不限／未填写' : String(value)
const failure = (reason: unknown) => reason instanceof Error ? reason.message : '操作失败，请稍后重试'
function invalidate() { preview.value = undefined; result.value = undefined; error.value = '' }
watch(() => props.open, value => {
  if (value) { file.value = undefined; submit.value = false; invalidate(); if (fileInput.value) fileInput.value.value = '' }
})
function selectFile(event: Event) {
  invalidate()
  const candidate = (event.target as HTMLInputElement).files?.[0]
  file.value = undefined
  if (!candidate) return
  if (!candidate.name.toLowerCase().endsWith('.xlsx') || candidate.size > 2 * 1024 * 1024) { error.value = '请选择不超过2MB的.xlsx文件'; return }
  file.value = candidate
}
async function download() {
  downloading.value = true; error.value = ''
  try { await downloadOpportunityTemplate() } catch (reason) { error.value = failure(reason) } finally { downloading.value = false }
}
async function check() {
  if (!file.value || busy.value) return
  checking.value = true; error.value = ''; preview.value = undefined
  try { preview.value = await previewOpportunityImport(file.value, submit.value) } catch (reason) { error.value = failure(reason) } finally { checking.value = false }
}
async function confirm() {
  if (!preview.value?.token || busy.value || result.value) return
  saving.value = true; error.value = ''
  try { result.value = await confirmOpportunityImport(preview.value.token); emit('imported') }
  catch (reason) { error.value = `${failure(reason)}。若网络中断，可保留当前预览再次确认，同一批次不会重复新建。` }
  finally { saving.value = false }
}
function close() {
  if (busy.value) return
  if (file.value && !result.value) {
    Modal.confirm({ title: '关闭导入窗口？', content: '尚未确认的数据不会保存。', onOk: () => emit('update:open', false) })
  } else emit('update:open', false)
}
</script>

<style scoped>
.import-content { display: flex; flex-direction: column; gap: 14px; max-height: calc(100vh - 250px); overflow-y: auto; min-height: 150px; }
.import-controls { padding-top: 4px; }.file-input { display: none; }.import-mode { display: flex; flex-wrap: wrap; gap: 8px; }.full-value { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
