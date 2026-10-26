<template>
  <FormGrid>
    <label
      >业务类型<a-select
        v-model:value="model.businessType"
        :options="options(config?.businessTypes, ['ISSUE', 'REFUND', 'CHANGE', 'UNKNOWN'])"
    /></label>
    <label v-for="field in identifiers" :key="field[0]"
      >{{ field[1] }}<a-input v-model:value="model[field[0]]"
    /></label>
    <label>币种<a-input v-model:value="model.currency" :maxlength="3" /></label>
    <label
      >明细分配金额<a-input
        v-model:value="model.amount"
        inputmode="decimal"
        placeholder="精确金额字符串；空值表示待核实"
    /></label>
    <label
      >订单归属核实<a-select
        v-model:value="model.matchStatus"
        :options="options(undefined, ['UNVERIFIED', 'OURS', 'NOT_OURS'])"
    /></label>
    <label class="adm-span"
      >归属核实依据<a-textarea
        v-model:value="model.matchEvidence"
        :rows="2"
        placeholder="匹配依据及人工核实结论；未匹配不能直接判非我司"
    /></label>
    <label>差异一级分类<a-input v-model:value="model.diffType" /></label>
    <label>差异二级分类<a-input v-model:value="model.diffSecondType" /></label>
    <label>平台编码<a-input v-model:value="model.platformCode" /></label>
    <label>航司<a-input v-model:value="model.airline" /></label>
    <label>票号数量<a-input v-model:value="model.ticketCount" inputmode="numeric" /></label>
    <label
      >人民币分摊金额<a-input v-model:value="model.amountCny" inputmode="decimal" placeholder="人工核实，不自动换算"
    /></label>
    <label>业务大类<a-select v-model:value="model.businessCategory" :options="businessCategories" /></label>
    <label>实际责任人<a-input v-model:value="model.actualOwner" placeholder="业务责任，不自动授予账号权限" /></label>
    <label>实际处理人<a-input v-model:value="model.actualHandler" /></label>
    <label
      >编码恢复时限（北京时间）<DateField v-model="recoveryDeadlineInput" with-time aria-label="编码恢复时限（北京时间）"
    /></label>
    <label class="adm-span">问题描述<a-textarea v-model:value="model.description" :rows="3" /></label>
    <label class="adm-span">差异说明<a-textarea v-model:value="model.differenceDescription" :rows="3" /></label>
    <label class="adm-span">明细备注<a-textarea v-model:value="model.remark" :rows="2" /></label>
    <label class="adm-span"
      >处理结果说明<a-textarea v-model:value="model.resolution" :rows="2" placeholder="只记事实；填写不自动结案"
    /></label>
    <label>申诉决策<a-select v-model:value="model.appealDecision" :options="appealDecisions" /></label>
    <label
      >是否需要编码恢复<a-switch
        v-model:checked="model.recoveryRequired"
        checked-children="需要"
        un-checked-children="不需要"
    /></label>
    <label class="adm-span"
      >申诉决策说明<a-textarea v-model:value="model.appealReason" :rows="2" placeholder="不申诉时请说明理由"
    /></label>
    <label
      >是否需要财务处理<a-switch
        v-model:checked="model.finance.required"
        checked-children="需要"
        un-checked-children="不需要"
    /></label>
    <label class="adm-span"
      >财务处理依据<a-textarea v-model:value="model.finance.reason" :rows="2" placeholder="无需财务处理时必须说明依据"
    /></label>
    <label v-for="field in analysisFields" :key="field[0]" class="adm-span"
      >{{ field[1] }}<a-textarea v-model:value="model.analysis[field[0]]" :rows="3"
    /></label>
    <label>结案原因归属<a-select v-model:value="model.attribution" allow-clear :options="attributions" /></label>
  </FormGrid>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import DateField from '@/components/DateField.vue'
import FormGrid from '@/components/FormGrid.vue'
import { options, type AdmConfig, type Fields } from './api'
const model = defineModel<Fields>({ required: true })
const recoveryDeadlineInput = computed({
  get: () => String(model.value.recoveryDeadline || '').slice(0, 16),
  set: (value: string) => {
    model.value.recoveryDeadline = value
  },
})
const businessCategories = [
  { value: '', label: '待分类' },
  { value: '0', label: '票务' },
  { value: '1', label: '业务' },
  { value: '2', label: '客服' },
]
defineProps<{ config: AdmConfig | null }>()
const identifiers = [
  ['platform', '平台'],
  ['shop', '店铺'],
  ['site', '细分站点'],
  ['orderNo', '订单号'],
  ['ticketNo', '票号'],
  ['pnr', 'PNR / 编码'],
  ['system', '系统'],
  ['pcc', 'PCC'],
]
const analysisFields = [
  ['facts', '事实核实与证据说明'],
  ['dispute', '争议点'],
  ['cause', '原因分析'],
  ['proposal', '处理方案'],
  ['conclusion', '最终结论'],
  ['prevention', '改进与预防措施'],
]
const attributions = ['人为差错', '系统原因', '供应商原因', '航司原因', '平台原因', '其他'].map((value) => ({
  label: value,
  value,
}))
const appealDecisions = [
  { value: 'UNDECIDED', label: '待决策' },
  { value: 'REQUIRED', label: '需要申诉' },
  { value: 'NOT_REQUIRED', label: '不申诉' },
]
</script>
