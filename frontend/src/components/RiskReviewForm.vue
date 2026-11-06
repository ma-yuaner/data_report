<template>
  <FormDialog :open="open" title="人工核实" :busy="busy || linkBusy || typeBusy" :dirty="true" :error="error" ok-text="保存核实结论" :submit-disabled="loading || !contexts.length" @submit="save" @cancel="emit('close')">
    <a-spin :spinning="loading">
      <p>本次 {{ contexts.length }} 单 · 人工结论独立保存，保留系统原始判断。</p>
      <a-alert v-if="contexts.some(item => item.stale)" type="warning" show-icon message="原人工结论已过期，本次将按当前证据重新核实" />
      <label>人工结论<a-select v-model:value="form.conclusion" :options="conclusionOptions" /></label>
      <template v-if="form.conclusion === 'no_issue'">
        <label v-if="orders.length === 1">无问题原因<a-select v-model:value="form.noIssueReason" :options="[{ value: 'company_policy', label: '符合公司策略' }, { value: 'evidence_verified', label: '证据核实无问题' }, { value: 'system_false_positive', label: '系统误报，人工核实无问题' }]" /></label>
        <template v-if="form.noIssueReason === 'company_policy' || orders.length > 1"><label>公司策略及版本<a-select v-model:value="form.policyId" placeholder="选择已登记策略" :options="policies.map(p => ({ value: p.id, label: `${p.name} / ${p.policyVersion}` }))" /></label>
        <div v-if="policy" class="policy"><strong>{{ policy.start }} 至 {{ policy.end }}</strong><p>适用范围：{{ policy.scope }}</p><p>依据：{{ policy.basis }}</p></div>
        <p v-if="linkedCase">保留关联案例：{{ linkedCase.title }} · v{{ linkedCase.version }}</p><a-checkbox v-model:checked="form.scopeConfirmed">已逐单核对，所选订单均符合此策略适用范围</a-checkbox>
        <p v-if="!policies.length" class="muted">尚无已登记策略，请具备类型管理权限的人员在“类型与策略”登记实际依据。</p></template>
      </template>
      <template v-else>
        <label>跟进方式<a-radio-group v-model:value="mode"><a-radio value="create">创建案例</a-radio><a-radio value="link">关联已有案例</a-radio></a-radio-group></label>
        <template v-if="mode === 'link'"><label>案例编号<a-input v-model:value="form.caseId" placeholder="粘贴案例完整编号" @change="linkedCase = undefined" /></label><a-button :loading="linkBusy" @click="lookupCase">核对关联案例</a-button><p v-if="linkedCase">{{ linkedCase.title }} · v{{ linkedCase.version }} · 已关联 {{ linkedCase.orders.length }} 单 · {{ conclusions[linkedCase.conclusion] }}</p><p class="muted">仅可关联结论相同且未完成的案例；请先核对案例再保存。</p></template>
        <template v-else>
          <label>案例标题<a-input v-model:value="form.title" :maxlength="160" /></label>
          <label>问题类型<a-select v-model:value="form.problemType" show-search placeholder="选择问题类型" :options="types.map(t => ({ value: t.name, label: t.name }))" /></label>
          <div v-if="canManageTypes" class="add-type"><a-input v-model:value="newType" placeholder="没有合适类型？输入新增类型" :maxlength="60" /><a-button :loading="typeBusy" @click="addType">新增问题类型</a-button></div>
          <div class="two"><label>发生原因或待核实项<a-input v-model:value="form.cause" placeholder="如系统配置错误，或说明待核实内容" /></label><label>责任归属<a-input v-model:value="form.responsibility" placeholder="人员／团队／待确认说明" /></label></div>
          <label>负责人<a-input v-model:value="form.assignee" :maxlength="80" placeholder="实际负责跟进的人员姓名" /></label>
          <label>下一步<a-input v-model:value="form.nextStep" :maxlength="1000" /></label>
          <label>下次跟进时间<DateField v-model="form.nextAt" with-time /></label>
          <a-space><a-checkbox v-model:checked="form.firstSeen">首次出现（已核对历史案例）</a-checkbox><a-checkbox v-model:checked="form.special">特殊案例</a-checkbox></a-space>
          <label v-if="form.firstSeen || form.special">首次或特殊案例说明<a-input v-model:value="form.specialReason" :maxlength="1000" /></label>
        </template>
      </template>
      <label>核实依据／缺失证据<a-textarea v-model:value="form.reason" :rows="3" :maxlength="2000" placeholder="写清人工判断依据；暂无法判断时说明缺少什么" /></label>
    </a-spin>
  </FormDialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, Checkbox as ACheckbox, Input as AInput, Radio as ARadio, RadioGroup as ARadioGroup, Select as ASelect, Space as ASpace, Spin as ASpin, message } from 'ant-design-vue'
import FormDialog from '@/components/FormDialog.vue'
import DateField from '@/components/DateField.vue'
import { riskFollowup, conclusions, reviewKey, type ReviewPolicy, type ReviewContext, type FollowDetail } from '@/api/riskFollowup'
import { riskProblems, type RiskProblemType } from '@/api/riskVerification'
import { useRiskPermissions } from '@/composables/useRiskPermissions'
const ATextarea = AInput.TextArea
const { canManageTypes } = useRiskPermissions()
const props = defineProps<{ open: boolean; orders: { orderId: string; issueDate: string }[] }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const busy = ref(false), loading = ref(false), error = ref(''), mode = ref('create'), newType = ref(''), typeBusy = ref(false)
const linkedCase = ref<FollowDetail>(), linkBusy = ref(false)
const policies = ref<ReviewPolicy[]>([]), contexts = ref<ReviewContext[]>([]), types = ref<RiskProblemType[]>([])
const form = reactive({ conclusion: 'no_issue', noIssueReason: 'company_policy', policyId: '', scopeConfirmed: false, reason: '', title: '', problemType: '', cause: '', responsibility: '', assignee: '', nextStep: '', nextAt: '', firstSeen: false, special: false, specialReason: '', caseId: '' })
let requestId = '', epoch = 0
const policy = computed(() => policies.value.find(p => p.id === form.policyId))
const conclusionOptions = computed(() => Object.entries(conclusions).filter(([key]) => props.orders.length === 1 || key === 'no_issue').map(([value, label]) => ({ value, label })))
watch(() => props.open, async open => {
  const token = ++epoch
  if (!open) return
  Object.assign(form, { conclusion: 'no_issue', noIssueReason: 'company_policy', policyId: '', scopeConfirmed: false, reason: '', title: '', problemType: '', cause: '', responsibility: '', assignee: '', nextStep: '', nextAt: '', firstSeen: false, special: false, specialReason: '', caseId: '' })
  linkedCase.value = undefined; mode.value = 'create'; error.value = ''; contexts.value = []; loading.value = true
  try {
    requestId = reviewKey()
    const [p, c, t] = await Promise.all([riskFollowup.policies(), Promise.all(props.orders.map(o => riskFollowup.order(o.orderId, o.issueDate))), riskProblems.types()])
    if (token !== epoch) return
    policies.value = p; contexts.value = c; types.value = t
    const previous = c[0]?.review
    if (c.length === 1 && previous?.caseId) { form.caseId = previous.caseId; form.conclusion = previous.conclusion; mode.value = 'link'; const linked = await riskFollowup.detail(previous.caseId); if (token === epoch) linkedCase.value = linked }
  } catch (e) { if (token === epoch) error.value = e instanceof Error ? e.message : '读取核实依据失败' }
  finally { if (token === epoch) loading.value = false }
}, { immediate: true })
onBeforeUnmount(() => { epoch++ })
async function addType() {
  if (!newType.value.trim() || typeBusy.value) return
  typeBusy.value = true
  try { const t = await riskProblems.createType(newType.value); if (!types.value.some(i => i.id === t.id)) types.value.push(t); form.problemType = t.name; newType.value = '' }
  catch (e) { error.value = e instanceof Error ? e.message : '新增类型失败' }
  finally { typeBusy.value = false }
}
async function lookupCase() {
  if (linkBusy.value || !form.caseId.trim()) return
  linkBusy.value = true; error.value = ''
  try { const id = form.caseId.trim(), token = epoch; const linked = await riskFollowup.detail(id); if (token === epoch && id === form.caseId.trim()) linkedCase.value = linked }
  catch (e) { error.value = e instanceof Error ? e.message : '案例读取失败' }
  finally { linkBusy.value = false }
}
async function save() {
  if (busy.value || loading.value) return
  busy.value = true; error.value = ''
  try {
    const linked = mode.value === 'link' ? linkedCase.value : null
    if (mode.value === 'link' && (!linked || linked.id !== form.caseId.trim())) throw new Error('请先点击核对关联案例')
    await riskFollowup.review({ ...form, caseId: linked?.id, caseVersion: linked?.version, requestId, orders: contexts.value.map(c => ({ orderId: c.orderId, issueDate: c.issueDate, resultId: c.resultId, version: c.version })) })
    message.success('人工核实已保存'); emit('saved'); emit('close')
  } catch (e) { error.value = e instanceof Error ? e.message : '保存失败，输入已保留' }
  finally { busy.value = false }
}
</script>
<style scoped>
label{display:grid;gap:6px;margin:16px 0}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.policy{padding:12px;background:#f5f8fc;overflow-wrap:anywhere}.policy p{margin:4px 0}.add-type{display:flex;gap:8px}.muted{color:#738298}input[type=datetime-local]{padding:8px;border:1px solid #d9d9d9;border-radius:6px;font:inherit;width:100%}@media(max-width:650px){.two{grid-template-columns:1fr}}
</style>
