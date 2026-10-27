<template>
  <FormDialog v-model:open="open" :title="rows.length > 1 ? '批量修改已投放政策' : '修改已投放政策'" :width="960" :busy="busy" :dirty="dirty" :error="error" :ok-text="previewRows.length ? '确认保存' : '预览逐条变更'" :submit-disabled="uncertain || !rows.length" @submit="submit">
    <a-alert type="info" show-icon message="本页不自动修改外部政策" description="待人工执行仅保存请求；实际配置与监控保持原值。已线下完成的政策，真实确认后可补登记并同步监控；历史命中订单保持原快照。" />
    <p>已选择 {{ rows.length }} 条政策。仅勾选需要修改的字段；舱位勾选后留空表示清空。</p>
    <fieldset v-if="!previewRows.length" :disabled="busy">
      <FormGrid>
        <label><a-checkbox v-model:checked="form.changeInclude">修改包含舱位</a-checkbox><a-input v-model:value="form.includeCabins" :disabled="!form.changeInclude" placeholder="英文逗号分隔，例如 Y,B,M" :maxlength="500" /></label>
        <label><a-checkbox v-model:checked="form.changeExclude">修改排除舱位</a-checkbox><a-input v-model:value="form.excludeCabins" :disabled="!form.changeExclude" placeholder="英文逗号分隔，例如 X,N" :maxlength="500" /></label>
        <label class="form-span"><a-checkbox v-model:checked="form.changePeriod">修改政策有效期（统一替换起止时间和长期选项）</a-checkbox></label>
        <label>政策生效时间<DateField v-model="form.effectiveStartAt" with-time :disabled="!form.changePeriod" /></label>
        <label>政策失效时间<DateField v-model="form.effectiveEndAt" with-time :disabled="!form.changePeriod || form.longTerm" /></label>
        <label class="form-span"><a-checkbox v-model:checked="form.longTerm" :disabled="!form.changePeriod">长期有效</a-checkbox></label>
        <label class="form-span"><span>保存方式 <span class="required">*</span></span><a-radio-group v-model:value="form.mode"><a-radio value="REQUEST_EXTERNAL">待人工外部执行</a-radio><a-radio value="OFFLINE_CONFIRMED">补登记实际配置（已线下处理）</a-radio></a-radio-group></label>
        <template v-if="form.mode === 'OFFLINE_CONFIRMED'">
          <label>线下实际修改时间（北京时间）<DateField v-model="form.appliedAt" with-time /></label>
          <label><span>真实执行确认 <span class="required">*</span></span><a-checkbox v-model:checked="form.externalConfirmed">所有选中政策已在线下完成本次修改，无需再次下发</a-checkbox></label>
        </template>
        <label class="form-span"><span>修改原因 <span class="required">*</span></span><a-textarea v-model:value="form.reason" :rows="3" :maxlength="1000" placeholder="说明本次修改的业务原因" /></label>
      </FormGrid>
    </fieldset>
    <template v-else>
      <a-alert :type="form.mode === 'REQUEST_EXTERNAL' ? 'warning' : 'info'" show-icon :message="form.mode === 'REQUEST_EXTERNAL' ? '确认后仅记录待人工外部执行请求，实际配置与监控不变' : '确认后补登记实际配置，并从保存时起同步新监控版本'" :description="`修改原因：${form.reason}${form.mode === 'OFFLINE_CONFIRMED' ? `；线下实际修改：${form.appliedAt.replace('T', ' ')}` : ''}`" />
      <article v-for="row in previewRows" :key="row.id" class="change-preview">
        <strong>{{ row.opportunityName }} · {{ row.taskNo }}</strong><p>外部政策 {{ row.externalPolicyId }} · 当前版本 V{{ row.versionNo }}</p>
        <p v-if="!row.changed">所选字段无变化，将跳过此条；其余政策仍需全部校验通过。</p>
        <div class="change-table-wrap"><table><thead><tr><th>所选字段</th><th>修改前</th><th>修改后</th></tr></thead><tbody><tr v-for="field in chosenFields" :key="field.key"><td>{{ field.label }}</td><td>{{ formatValue(row.before, field.key) }}</td><td>{{ formatValue(row.after, field.key) }}</td></tr></tbody></table></div>
      </article>
      <a-button :disabled="busy" @click="backToForm">返回修改</a-button>
    </template>
    <a-alert v-if="uncertain" type="warning" show-icon message="保存结果待核对，已禁止重复保存" description="请关闭窗口，刷新政策详情与流转日志，核对本次原因、操作人和时间；确认未保存后重新打开。" />
  </FormDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, Checkbox as ACheckbox, Input as AInput, Radio as ARadio, RadioGroup as ARadioGroup, Textarea as ATextarea, message } from 'ant-design-vue'
import FormDialog from './FormDialog.vue'
import FormGrid from './FormGrid.vue'
import DateField from './DateField.vue'
import { ApiError } from '@/api/http'
import { changePlacedPolicies, type PlacedPolicyChangeInput, type PlacedPolicyChangeRow, type PlacementTaskRow } from '@/api/smartPlacement'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ rows: PlacementTaskRow[] }>()
const emit = defineEmits<{ saved: [] }>()
function blank() { return { changeInclude: false, changeExclude: false, changePeriod: false, includeCabins: '', excludeCabins: '', effectiveStartAt: '', effectiveEndAt: '', longTerm: false, mode: 'REQUEST_EXTERNAL' as PlacedPolicyChangeInput['mode'], reason: '', appliedAt: '', externalConfirmed: false } }
const form = ref(blank())
const busy = ref(false)
const error = ref('')
const uncertain = ref(false)
const previewRows = ref<PlacedPolicyChangeRow[]>([])
const previewInput = ref<PlacedPolicyChangeInput>()
const dirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(blank()))
const chosenFields = computed(() => [
  ...(form.value.changeInclude ? [{ key: 'includeCabins', label: '包含舱位' }] : []),
  ...(form.value.changeExclude ? [{ key: 'excludeCabins', label: '排除舱位' }] : []),
  ...(form.value.changePeriod ? [{ key: 'effectivePeriod', label: '政策有效期' }] : []),
])
watch(open, value => { if (value) { form.value = blank(); previewRows.value = []; previewInput.value = undefined; error.value = ''; uncertain.value = false } })
function formatValue(values: PlacedPolicyChangeRow['before'], key: string) {
  if (key === 'effectivePeriod') return `${values.effectiveStartAt || '—'} 至 ${Number(values.longTermFlag) ? '长期有效' : values.effectiveEndAt || '—'}`
  return String(values[key] || (key === 'includeCabins' ? '不限' : '无'))
}
function backToForm() { previewRows.value = []; previewInput.value = undefined; error.value = '' }
async function submit() {
  if (busy.value || uncertain.value) return
  error.value = ''
  const saving = !!previewRows.value.length
  try {
    let input = previewInput.value
    if (!saving) {
      const patch: PlacedPolicyChangeInput['patch'] = {}
      if (form.value.changeInclude) patch.includeCabins = form.value.includeCabins
      if (form.value.changeExclude) patch.excludeCabins = form.value.excludeCabins
      if (form.value.changePeriod) patch.effectivePeriod = { effectiveStartAt: form.value.effectiveStartAt, effectiveEndAt: form.value.effectiveEndAt, longTerm: form.value.longTerm }
      if (!Object.keys(patch).length) throw new Error('请至少勾选一个需要变更的字段')
      if (!form.value.reason.trim()) throw new Error('请填写修改原因')
      input = { targets: props.rows.map(row => ({ id: row.id, versionNo: row.versionNo })), patch, mode: form.value.mode, reason: form.value.reason.trim(), appliedAt: form.value.appliedAt, externalConfirmed: form.value.externalConfirmed }
    }
    if (!input) return
    input = JSON.parse(JSON.stringify(input)) as PlacedPolicyChangeInput
    busy.value = true
    const result = await changePlacedPolicies(input, !saving)
    if (saving) {
      message.success(result.applied ? `${result.count} 条实际配置与监控已更新（线下确认补登记）` : `已记录 ${result.count} 条待人工外部执行请求，实际配置与监控未变`)
      open.value = false
      emit('saved')
    } else {
      previewRows.value = result.rows
      previewInput.value = { ...input, targets: result.rows.map(row => ({ id: row.id, versionNo: row.versionNo, ruleVersionId: row.ruleVersionId })) }
    }
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : '修改失败，请核对后重试'
    if (saving && failure instanceof ApiError && (!failure.status || failure.status >= 500)) uncertain.value = true
    if (failure instanceof ApiError && failure.status === 409) { previewRows.value = []; previewInput.value = undefined }
  } finally { busy.value = false }
}
</script>

<style scoped>
.shared-form-grid { margin: 16px 0; }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
.change-preview { margin: 16px 0; padding: 12px; border: 1px solid #e5eaf0; border-radius: 6px; }
.change-preview p { color: #64748b; font-size: 12px; margin: 4px 0 8px; }
.change-table-wrap { overflow-x: auto; }
table { width: 100%; min-width: 480px; border-collapse: collapse; table-layout: fixed; }
th, td { border-bottom: 1px solid #edf0f5; padding: 8px; text-align: left; overflow-wrap: anywhere; vertical-align: top; }
th { background: #f7f9fc; } th:first-child { width: 110px; }
</style>
