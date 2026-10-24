<template>
  <div class="adm-form-grid">
    <label>ADM 单号 <span class="required">*</span><a-input v-model:value="model.admNo" :maxlength="100" /></label>
    <label>下发方 <span class="required">*</span><a-input v-model:value="model.supplierName" :maxlength="200" /></label>
    <label>下发方类型<a-select v-model:value="model.supplierType" :options="supplierTypes" /></label>
    <label>下发方编码<a-input v-model:value="model.supplierCode" :maxlength="200" /></label>
    <label>航司（多个逗号分隔）<a-input v-model:value="model.airline" :maxlength="200" /></label>
    <label
      >原票号数量<a-input v-model:value="model.ticketCount" inputmode="numeric" placeholder="未知留空，不等于订单条数"
    /></label>
    <label
      >人民币金额<a-input
        v-model:value="model.originalAmountCny"
        inputmode="decimal"
        placeholder="人工核实值；不自动换算"
    /></label>
    <label>业务大类<a-select v-model:value="model.businessCategory" :options="businessCategories" /></label>
    <label
      >币种 <span class="required">*</span><a-input v-model:value="model.currency" :maxlength="3" placeholder="CNY"
    /></label>
    <label
      >下发原始金额 <span class="required">*</span
      ><a-input v-model:value="model.originalAmount" inputmode="decimal" placeholder="十进制金额，如 123.45"
    /></label>
    <label>下发日期<input v-model="model.issuedDate" type="date" class="adm-native" /></label>
    <label>处理截止时间（北京时间）<input v-model="deadlineInput" type="datetime-local" class="adm-native" /></label>
    <label class="adm-span"
      >问题描述<a-textarea
        v-model:value="model.description"
        :rows="3"
        placeholder="下发背景、涉及范围、疑问及待核实事项"
    /></label>
    <label class="adm-span"
      >主单备注<a-textarea v-model:value="model.remark" :rows="2" placeholder="仅有主单权限的人员可见"
    /></label>
    <label v-for="field in analysisFields" :key="field[0]" class="adm-span"
      >主单{{ field[1] }}<a-textarea v-model:value="model.analysis[field[0]]" :rows="3"
    /></label>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { Fields } from './api'
const model = defineModel<Fields>({ required: true })
const businessCategories = [
  { value: '', label: '待分类' },
  { value: '0', label: '票务' },
  { value: '1', label: '业务' },
  { value: '2', label: '客服' },
]
const deadlineInput = computed({
  get: () =>
    model.value.deadline?.length === 10 ? `${model.value.deadline}T23:59` : (model.value.deadline || '').slice(0, 16),
  set: (value: string) => {
    model.value.deadline = value
  },
})
const supplierTypes = ['SUPPLIER', 'AIRLINE', 'PLATFORM', 'OTHER'].map((value, index) => ({
  value,
  label: ['供应商', '航司', '平台', '其他'][index],
}))
const analysisFields = [
  ['facts', '事实核实'],
  ['dispute', '争议点'],
  ['cause', '原因分析'],
  ['proposal', '处理方案'],
  ['conclusion', '最终结论'],
  ['prevention', '改进与预防措施'],
]
</script>
