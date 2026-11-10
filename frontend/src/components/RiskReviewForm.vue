<template>
  <FormDialog :open="open" title="人工核实" :busy="busy" :dirty="dirty" :error="error" ok-text="保存核实结论" :submit-disabled="loading || !contexts.length" @submit="save" @cancel="emit('close')">
    <a-spin :spinning="loading">
      <label>人工结论 <span class="required">必填</span><a-radio-group v-model:value="form.conclusion" class="conclusion-options"><a-radio-button value="no_issue">核查无问题</a-radio-button><a-radio-button v-if="orders.length === 1" value="problem">有问题</a-radio-button></a-radio-group></label>
      <template v-if="form.conclusion === 'problem'">
        <label>实际盈亏原因 <span class="required">必填</span><a-textarea v-model:value="form.actualProfitReason" :rows="2" :maxlength="200" show-count placeholder="填写核查确认的实际业务原因" /></label>
        <label>是否已咨询 <span class="required">必填</span><a-radio-group v-model:value="form.consultation"><a-radio value="pending">待咨询</a-radio><a-radio value="consulted">已咨询</a-radio></a-radio-group></label>
        <label v-if="!contexts[0]?.review?.caseId">处理方式<a-radio-group v-model:value="form.initialDisposition"><a-radio value="pending">进入跟进，待认定</a-radio><a-radio value="included">直接计入差错并完结</a-radio></a-radio-group></label>
      </template>
      <a-alert v-if="contexts.some(item => item.stale)" type="warning" show-icon message="证据已变化，本次将按当前证据重新核实" />
      <label>核实依据 <span class="required">必填</span><a-textarea v-model:value="form.reason" :rows="4" :maxlength="2000" show-count placeholder="填写判断依据" /></label>
      <label>备注 <span class="muted">选填</span><a-textarea v-model:value="form.remark" :rows="3" :maxlength="2000" show-count placeholder="补充需要保留的说明" /></label>
    </a-spin>
  </FormDialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Alert as AAlert, Input as AInput, Radio as ARadio, RadioButton as ARadioButton, RadioGroup as ARadioGroup, Spin as ASpin, message } from 'ant-design-vue'
import FormDialog from '@/components/FormDialog.vue'
import { riskFollowup, reviewKey, isLegacyAutoPending, type ReviewContext } from '@/api/riskFollowup'
const ATextarea = AInput.TextArea
const props = defineProps<{ open: boolean; currentCaseId?: string; orders: { orderId: string; issueDate: string }[] }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const router = useRouter(), busy = ref(false), loading = ref(false), error = ref('')
const contexts = ref<ReviewContext[]>([])
const defaults = () => ({ conclusion: '', reason: '', actualProfitReason: '', remark: '', consultation: 'pending', initialDisposition: 'pending' })
const form = reactive(defaults()), initial = ref('')
const dirty = computed(() => JSON.stringify(form) !== initial.value)
let requestId = '', epoch = 0
watch(() => form.conclusion, (value, previous) => {
 if (value === 'no_issue' && !form.reason.startsWith('核查无问题')) form.reason = form.reason.trim() ? `核查无问题\n${form.reason}` : '核查无问题'
 else if (previous === 'no_issue' && form.reason.startsWith('核查无问题')) form.reason = form.reason.slice('核查无问题'.length).replace(/^\n/, '')
}, { flush: 'sync' })
watch(() => props.open, async open => {
 const token = ++epoch
 if (!open) return
 Object.assign(form, defaults(), props.orders.length > 1 ? { conclusion: 'no_issue', reason: '核查无问题' } : {}); initial.value = JSON.stringify(form)
 error.value = ''; contexts.value = []; loading.value = true
 try {
  requestId = reviewKey()
  const values = await Promise.all(props.orders.map(o => riskFollowup.order(o.orderId, o.issueDate)))
  if (token !== epoch) return
  contexts.value = values
  const previous = values.length === 1 ? values[0]?.review : null
  if (previous && !isLegacyAutoPending(previous)) Object.assign(form, { conclusion: previous.conclusion === 'unknown' ? '' : previous.conclusion, reason: previous.reason, actualProfitReason: previous.actualProfitReason ?? '', remark: previous.remark ?? '', consultation: previous.consultation ?? 'pending' })
  initial.value = JSON.stringify(form)
 } catch (e) { if (token === epoch) error.value = e instanceof Error ? e.message : '读取核实记录失败，请关闭后重试' }
 finally { if (token === epoch) loading.value = false }
}, { immediate: true })
onBeforeUnmount(() => { epoch++ })
async function save() {
 if (busy.value || loading.value || !contexts.value.length) return
 error.value = ''
 if (!form.conclusion) { error.value = '请选择人工结论'; return }
 if (form.conclusion === 'problem' && !form.actualProfitReason.trim()) { error.value = '请填写实际盈亏原因'; return }
 if (!form.reason.trim()) { error.value = '请填写核实依据'; return }
 busy.value = true
 try {
  const result = await riskFollowup.review({ ...form, workflowVersion: 3, requestId, orders: contexts.value.map(c => ({ orderId: c.orderId, issueDate: c.issueDate, resultId: c.resultId, version: c.version, caseId: c.review?.caseId })) })
  message.success(form.conclusion === 'problem' && form.initialDisposition === 'included' ? '已计入差错并完结' : '核查结论已保存'); emit('saved'); emit('close')
  if (form.conclusion === 'problem' && result.caseId && result.caseId !== props.currentCaseId) await router.push({ name: 'risk-followup-cases', query: { case: result.caseId, pool: result.casePool } })
 } catch (e) { error.value = e instanceof Error ? e.message : '保存失败，输入已保留' }
 finally { busy.value = false }
}
</script>
<style scoped>
label{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:20px 0;color:#182235;font-weight:500}label>:last-child:not(span){flex-basis:100%;font-weight:400}.conclusion-options{display:flex;flex-wrap:wrap;margin-top:4px}.conclusion-options :deep(.ant-radio-button-wrapper){flex:1;text-align:center;min-width:110px}.required,.muted{font-size:12px;font-weight:400;color:#738298}.required{color:#a33b35}.ant-alert+.ant-alert{margin-top:12px}
</style>
