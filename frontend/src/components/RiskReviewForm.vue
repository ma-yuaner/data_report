<template>
  <FormDialog :open="open" title="人工核实" :busy="busy" :dirty="dirty" :error="error" ok-text="保存核实结论" :submit-disabled="loading || !contexts.length || !!contexts[0]?.review?.caseId" @submit="save" @cancel="emit('close')">
    <a-spin :spinning="loading">
      <a-alert v-if="contexts[0]?.review?.caseId" type="warning" show-icon message="此单已关联历史案例，请从人工核实记录进入原案例处理，避免影响其他关联订单。" />
      <label>人工结论 <span class="required">必填</span><a-radio-group v-model:value="form.conclusion" class="conclusion-options"><a-radio-button v-for="option in conclusionOptions" :key="option.value" :value="option.value">{{ option.label }}</a-radio-button></a-radio-group></label>
      <a-alert :type="form.conclusion === 'unknown' ? 'warning' : 'info'" show-icon :message="form.conclusion === 'unknown' ? '保存后为待补证，可补充证据后重新核实。' : '保存后完成人工判断，保留系统原始结果。'" />
      <a-alert v-if="contexts.some(item => item.stale)" type="warning" show-icon message="证据已变化，本次将按当前证据重新核实" />
      <template v-if="orders.length > 1">
        <label>公司策略及版本<a-select v-model:value="form.policyId" placeholder="选择批量核实的共同策略" :options="policies.map(p => ({ value: p.id, label: `${p.name} / ${p.policyVersion}` }))" /></label>
        <a-checkbox v-model:checked="form.scopeConfirmed">已逐单核对，所选订单均符合此策略适用范围</a-checkbox>
      </template>
      <label>核实类型 <span class="muted">选填，可多选</span><a-space wrap><a-checkbox v-model:checked="form.firstSeen">首次出现</a-checkbox><a-checkbox v-model:checked="form.special">特殊案例</a-checkbox></a-space></label>
      <label v-if="form.firstSeen || form.special">类型说明 <span class="required">必填</span><a-input v-model:value="form.specialReason" :maxlength="1000" placeholder="说明首次出现或特殊之处" /></label>
      <label>{{ form.conclusion === 'unknown' ? '缺失证据／待核实内容' : '核实依据' }} <span class="required">必填</span><a-textarea v-model:value="form.reason" :rows="4" :maxlength="2000" show-count :placeholder="form.conclusion === 'unknown' ? '说明缺少什么，补证后可在详情底部重新核实' : '简要说明判断依据或发现的问题'" /></label>
    </a-spin>
  </FormDialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Alert as AAlert, Checkbox as ACheckbox, Input as AInput, RadioButton as ARadioButton, RadioGroup as ARadioGroup, Select as ASelect, Space as ASpace, Spin as ASpin, message } from 'ant-design-vue'
import FormDialog from '@/components/FormDialog.vue'
import { riskFollowup, conclusions, reviewKey, type ReviewPolicy, type ReviewContext } from '@/api/riskFollowup'
const ATextarea = AInput.TextArea
const props = defineProps<{ open: boolean; orders: { orderId: string; issueDate: string }[] }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const busy = ref(false), loading = ref(false), error = ref('')
const contexts = ref<ReviewContext[]>([]), policies = ref<ReviewPolicy[]>([])
const defaults = () => ({ conclusion: '', reason: '', firstSeen: false, special: false, specialReason: '', policyId: '', scopeConfirmed: false })
const form = reactive(defaults())
const initial = ref('')
const dirty = computed(() => JSON.stringify(form) !== initial.value)
let requestId = '', epoch = 0
const conclusionOptions = computed(() => Object.entries(conclusions).filter(([key]) => props.orders.length === 1 || key === 'no_issue').map(([value, label]) => ({ value, label })))
watch(() => props.open, async open => {
  const token = ++epoch
  if (!open) return
  Object.assign(form, defaults(), props.orders.length > 1 ? { conclusion: 'no_issue' } : {}); initial.value = JSON.stringify(form)
  error.value = ''; contexts.value = []; loading.value = true
  try {
    requestId = reviewKey()
    const [c, p] = await Promise.all([Promise.all(props.orders.map(o => riskFollowup.order(o.orderId, o.issueDate))), props.orders.length > 1 ? riskFollowup.policies() : Promise.resolve([])])
    if (token !== epoch) return
    contexts.value = c; policies.value = p
    const previous = c.length === 1 ? c[0]?.review : null
    if (previous) Object.assign(form, { conclusion: previous.conclusion, reason: previous.reason, firstSeen: previous.firstSeen ?? false, special: previous.special ?? false, specialReason: previous.specialReason ?? '' })
    initial.value = JSON.stringify(form)
  } catch (e) { if (token === epoch) error.value = e instanceof Error ? e.message : '读取核实依据失败，请关闭后重试' }
  finally { if (token === epoch) loading.value = false }
}, { immediate: true })
onBeforeUnmount(() => { epoch++ })
async function save() {
  if (busy.value || loading.value || !contexts.value.length) return
  error.value = ''
  if (!form.conclusion) { error.value = '请选择人工结论'; return }
  if (!form.reason.trim()) { error.value = '请填写核实依据或缺失证据'; return }
  if ((form.firstSeen || form.special) && !form.specialReason.trim()) { error.value = '请填写类型说明'; return }
  busy.value = true
  try {
    await riskFollowup.review({ ...form, simpleReview: true, noIssueReason: props.orders.length > 1 ? 'company_policy' : 'evidence_verified', requestId, orders: contexts.value.map(c => ({ orderId: c.orderId, issueDate: c.issueDate, resultId: c.resultId, version: c.version })) })
    message.success('人工核实已保存'); emit('saved'); emit('close')
  } catch (e) { error.value = e instanceof Error ? e.message : '保存失败，输入已保留' }
  finally { busy.value = false }
}
</script>
<style scoped>
label{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:20px 0;color:#182235;font-weight:500}label>:last-child:not(span){flex-basis:100%;font-weight:400}.conclusion-options{display:flex;flex-wrap:wrap;margin-top:4px}.conclusion-options :deep(.ant-radio-button-wrapper){flex:1;text-align:center;min-width:110px}.required,.muted{font-size:12px;font-weight:400;color:#738298}.required{color:#a33b35}.ant-alert+.ant-alert{margin-top:12px}
</style>
