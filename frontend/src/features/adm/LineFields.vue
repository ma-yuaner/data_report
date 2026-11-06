<template>
  <FormGrid>
    <label
      >业务类型<a-select
        v-model:value="model.businessType"
        :options="options(config?.businessTypes, ['ISSUE', 'REFUND', 'CHANGE', 'UNKNOWN'])"
    /></label>
    <label>OTA平台<a-select v-model:value="model.platformCode" allow-clear show-search :options="platformOptions" /></label>
    <label>供应商<a-select v-model:value="model.supplierCode" allow-clear show-search :options="supplierOptions" /></label>
    <label v-for="field in identifiers" :key="field[0]"
      >{{ field[1] }}<a-input v-model:value="model[field[0]]"
    /></label>
    <label>业务归属部门<a-select v-model:value="model.departmentCode" show-search :options="departmentOptions" /></label>
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
    <label
      >差异一级分类<a-select
        v-model:value="model.diffType"
        allow-clear
        show-search
        :options="differenceTypeOptions"
        placeholder="请选择启用的 ADM 差异类型"
    /></label>
    <label>差异二级分类<a-input v-model:value="model.diffSecondType" /></label>
    <label>航司<a-input v-model:value="model.airline" /></label>
    <label>票号数量<a-input v-model:value="model.ticketCount" inputmode="numeric" /></label>
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
    <label class="adm-span"
      >订单核查情况及原因说明（操作员填写）<a-textarea
        v-model:value="model.investigationNote"
        :rows="3"
        placeholder="请记录编码恢复或日志核查结果、订单实际情况、问题原因及判断依据"
    /></label>
    <label v-for="field in analysisFields" :key="field[0]" class="adm-span"
      >{{ field[1] }}<a-textarea v-model:value="model.analysis[field[0]]" :rows="3"
    /></label>
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
const props = defineProps<{ config: AdmConfig | null }>()
const platformOptions = computed(() =>
  (props.config?.references?.platforms || []).map((item) => ({ value: item.code, label: item.label })),
)
const supplierOptions = computed(() =>
  (props.config?.references?.suppliers || []).map((item) => ({ value: item.code, label: item.label })),
)
const differenceTypeOptions = computed(() =>
  (props.config?.references?.differenceTypes || []).map((item) => ({ value: item.code, label: item.label })),
)
const departmentOptions = computed(() =>
  (props.config?.people?.departments || []).map((item) => ({ value: item.code, label: `${item.code}/${item.name}` })),
)
const identifiers = [
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
</script>
