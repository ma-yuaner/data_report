<template>
  <section class="adm-initial-lines">
    <h3>订单明细 · {{ model.length }} 条</h3>
    <p class="adm-muted">可先存主单，也可在这里逐条录入。每条订单独立说明，保存后分别分配、上传附件和处理。</p>
    <details v-for="(line, index) in model" :key="line._draftKey" :open="line._draftKey === expanded">
      <summary>订单 {{ index + 1 }} · {{ line.orderNo || line.ticketNo || '待填写' }}</summary>
      <FormGrid>
        <label>业务类型<a-select v-model:value="line.businessType" :options="businessTypes" /></label>
        <label v-for="field in identifiers" :key="field[0]"
          >{{ field[1] }}<a-input v-model:value="line[field[0]]" :maxlength="200"
        /></label>
        <label>币种<a-input v-model:value="line.currency" :maxlength="3" /></label>
        <label
          >本条分摊金额<a-input
            v-model:value="line.amount"
            inputmode="decimal"
            placeholder="可留空，不自动平分主单金额"
        /></label>
        <label class="adm-span"
          >本订单问题说明<a-textarea v-model:value="line.description" :rows="2" :maxlength="10000"
        /></label>
        <label class="adm-span"
          >本订单处理说明 / 计划<a-textarea
            v-model:value="line.analysis.proposal"
            :rows="2"
            :maxlength="10000"
            placeholder="仅记录计划，不代表已处理或已结案"
        /></label>
      </FormGrid>
      <a-button danger type="text" :disabled="disabled" @click="remove(index)">移除本条未保存订单</a-button>
    </details>
    <a-button block :disabled="disabled || model.length >= 1000" @click="add">＋ 添加订单</a-button>
  </section>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import FormGrid from '@/components/FormGrid.vue'
import type { Fields } from './api'
const model = defineModel<Fields[]>({ required: true })
const props = defineProps<{ currency: string; disabled?: boolean }>()
const expanded = ref<number | null>(null)
let nextKey = 0
const businessTypes = [
  { value: 'UNKNOWN', label: '待确认' },
  { value: 'ISSUE', label: '出票' },
  { value: 'REFUND', label: '退票' },
  { value: 'CHANGE', label: '改签' },
]
const identifiers = [
  ['platform', '平台'],
  ['orderNo', '订单号'],
  ['ticketNo', '票号'],
  ['pnr', 'PNR / 编码'],
]
function add() {
  if (props.disabled || model.value.length >= 1000) return
  const key = ++nextKey
  model.value = [
    ...model.value,
    { _draftKey: key, businessType: 'UNKNOWN', currency: props.currency || 'CNY', amount: '', analysis: {} },
  ]
  expanded.value = key
}
function remove(index: number) {
  if (!props.disabled) model.value = model.value.filter((_, position) => position !== index)
}
</script>
