<template>
  <FormDialog v-model:open="open" title="下载订单明细" :width="720" :busy="busy" :error="error" :submit-disabled="Boolean(validationError)" ok-text="创建下载任务" @submit="submit">
    <FormGrid>
      <div class="form-span"><DateRangeField v-model:start="downloadScope.startDate" v-model:end="downloadScope.endDate" label="下载期间" :disabled="busy" /></div>
      <label class="form-span"><span>业务类型</span><a-select v-model:value="selected" mode="multiple" :options="businessOptions" :disabled="busy" aria-label="下载业务类型" /></label>
      <div class="form-span download-scope"><strong>继承的筛选条件</strong><p>{{ scopeLabel }}</p><p>可在当前统计期间内缩小日期，单次最多31天。各业务分别生成文件，下载全部匹配明细，不受分页限制。</p></div>
    </FormGrid>
    <a-alert v-if="validationError" type="warning" show-icon :message="validationError" />
    <a-alert class="download-note" type="info" show-icon message="任务在后台执行，可在页头“导出任务”中查看进度和取消。" description="每类业务最多500,000条，超过300,000条需再次确认；每用户最多3个活动任务，未提交成功的业务会保留，可稍后重试。" />
    <p v-if="busy" role="status">{{ progress }}</p>
    <ul v-if="results.length" class="download-results" aria-live="polite"><li v-for="result in results" :key="result.business">{{ label(result.business) }}：{{ result.message }}</li></ul>
  </FormDialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Modal, message } from 'ant-design-vue'
import FormDialog from './FormDialog.vue'
import FormGrid from './FormGrid.vue'
import DateRangeField from './DateRangeField.vue'
import { fetchComprehensiveDetails, type BusinessKey, type FilterScope } from '@/api/comprehensive'
import { createComprehensiveExport } from '@/api/comprehensiveExport'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ scope: FilterScope; scopeLabel: string; business?: BusinessKey | '' }>()
const store = useComprehensiveExportStore()
const businessOptions = [{ label: '出票', value: 'issue' }, { label: '退票', value: 'refund' }, { label: '改签', value: 'change' }, { label: '增值', value: 'ancillary' }]
const label = (business: BusinessKey) => businessOptions.find(item => item.value === business)?.label || business
const downloadScope = ref<FilterScope>({ ...props.scope })
const selected = ref<BusinessKey[]>([])
const busy = ref(false)
const error = ref('')
const progress = ref('')
const results = ref<{ business: BusinessKey; message: string }[]>([])
watch(open, value => {
  if (!value) return
  downloadScope.value = { ...props.scope, preset: 'custom' }
  selected.value = props.business ? [props.business] : ['issue', 'refund', 'change', 'ancillary']
  error.value = ''
  results.value = []
})
const validationError = computed(() => {
  const { startDate, endDate } = downloadScope.value
  const first = Date.parse(startDate)
  const last = Date.parse(endDate)
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first) return '请选择有效的开始和结束日期。'
  if (startDate < props.scope.startDate || endDate > props.scope.endDate) return '下载日期须在当前统计期间内。'
  if (last - first > 30 * 86400000) return '单次最多下载31天，请缩小日期范围。'
  if (!selected.value.length) return '请选择至少一种业务。'
  return ''
})
async function submit() {
  if (busy.value || validationError.value) return
  busy.value = true
  error.value = ''
  results.value = []
  const scope = { ...downloadScope.value }
  const businesses = [...selected.value]
  try {
    const counts: { business: BusinessKey; total: number }[] = []
    for (const business of businesses) {
      progress.value = `正在核对${label(business)}明细数量…`
      // Use the same bound filters and inclusive period as the existing detail API.
      // Only one preview row is read; the export service counts again independently.
      const detail = await fetchComprehensiveDetails(scope, business, 1, 1)
      if (!detail.available || detail.error) throw new Error(`${label(business)}：${detail.error || '明细数据不可用'}`)
      if (detail.total > 500_000) throw new Error(`${label(business)}匹配 ${detail.total.toLocaleString()} 条，超过500,000条，请缩小日期或筛选范围。`)
      counts.push({ business, total: detail.total })
    }
    const large = counts.filter(item => item.total > 300_000)
    if (large.length) {
      progress.value = '等待确认大批量下载…'
      const confirmed = await new Promise<boolean>(resolve => {
        Modal.confirm({ title: '确认创建大批量下载任务？', content: large.map(item => `${label(item.business)} ${item.total.toLocaleString()} 条`).join('；') + '。任务将在后台执行，可在“导出任务”中取消。', okText: '继续下载', cancelText: '返回', onOk: () => { resolve(true) }, onCancel: () => { resolve(false) } })
      })
      if (!confirmed) return
    }
    const pending: BusinessKey[] = []
    let submitted = 0
    for (const { business, total } of counts) {
      if (!total) {
        results.value.push({ business, message: '当前条件无匹配明细，未创建任务' })
        continue
      }
      progress.value = `正在提交${label(business)}下载任务…`
      try {
        const task = await createComprehensiveExport(scope, business)
        submitted++
        results.value.push({ business, message: task.reused ? '已有相同条件的活动任务，请在“导出任务”中查看' : '任务已创建，请在“导出任务”中查看' })
      } catch (failure) {
        pending.push(business)
        results.value.push({ business, message: failure instanceof Error ? failure.message : '提交失败，请重试' })
      }
    }
    selected.value = pending
    if (submitted) {
      await store.refresh(true)
      message.success(`已提交或复用 ${submitted} 个明细下载任务`)
    }
    if (pending.length) error.value = '部分业务未提交成功，成功的任务不受影响；已保留未成功的业务，可稍后重试。'
    else if (submitted) { open.value = false; store.drawerOpen = true }
    else error.value = '所选业务均无匹配明细，请调整条件后重试。'
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : '明细数量核对失败，请重试'
  } finally { busy.value = false; progress.value = '' }
}
</script>

<style scoped>
.download-scope p { margin: 6px 0 0; color: #69768a; overflow-wrap: anywhere; }
.download-note { margin-top: 16px; }
.download-results { margin: 16px 0 0; padding-left: 20px; overflow-wrap: anywhere; }
.download-results li + li { margin-top: 8px; }
</style>
