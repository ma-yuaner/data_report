<template>
  <FormGrid>
    <label
      >{{ modelValue.preliminary ? 'ADM号（未提供可空，生成预罚临时号）' : 'ADM号 *'
      }}<a-input :value="modelValue.admNo" @update:value="set('admNo', $event)"
    /></label>
    <label
      >来源主体 *<a-select
        :value="modelValue.sourceType"
        :options="options(['航司', '供应商', '平台'])"
        @update:value="set('sourceType', $event)"
    /></label>
    <label>供应商 *<a-input :value="modelValue.supplier" @update:value="supplierChanged" /></label>
    <label>航司代码 *<a-input :value="modelValue.airline" @update:value="set('airline', $event)" /></label>
    <label
      >下发日期 *<DateField :model-value="modelValue.issuedOn" @update:model-value="set('issuedOn', $event)"
    /></label>
    <label
      >供应回复截止 *<DateField :model-value="modelValue.replyDue" @update:model-value="set('replyDue', $event)"
    /></label>
    <label
      >具体错误类型 *<a-select
        :value="modelValue.diffType"
        :options="options(types || specificTypes)"
        @update:value="set('diffType', $event)"
    /></label>
    <label
      ><a-checkbox :checked="modelValue.preliminary" @update:checked="set('preliminary', $event)"
        >预罚核实演练（邮件为准、群辅助）</a-checkbox
      ></label
    >
    <label class="form-span"
      >ADM内容 *<a-textarea :value="modelValue.description" :rows="3" @update:value="set('description', $event)"
    /></label>
    <label>主单原币金额 *<a-input :value="modelValue.amount" @update:value="set('amount', $event)" /></label>
    <label
      >币种 *<a-select
        :value="modelValue.currency"
        :options="options(['CNY', 'HKD', 'JPY', 'USD', 'EUR'])"
        @update:value="currencyChanged"
    /></label>
    <label v-if="modelValue.currency !== 'CNY'"
      >演练参考汇率（1原币=多少CNY）<a-input
        :value="modelValue.rate"
        placeholder="可留空，不假定为0"
        @update:value="set('rate', $event)"
    /></label>
    <label
      >人民币参考值<strong>{{ reference || '未换算' }}</strong
      ><small>汇率源待确认；本页使用手工演练值，非实时汇率或结算结果。</small></label
    >
    <label class="form-span"
      >备注<a-textarea :value="modelValue.remark" :rows="2" @update:value="set('remark', $event)"
    /></label>
  </FormGrid>
  <h3>关联订单子项</h3>
  <p class="muted">
    一行可填多个票号（用分号分隔）。不同平台或需独立办理时由你添加子项。预罚无订单可移除全部子项，先建立核实任务；正式转换前补齐。
  </p>
  <button @click="recognize">识别本地演示票号 / 订单候选</button>
  <p v-if="candidateMessage" class="callout">{{ candidateMessage }}</p>
  <article v-for="(row, index) in rows" :key="index" class="intake-row">
    <div class="section-heading">
      <strong>子项 {{ index + 1 }}</strong
      ><button v-if="rows.length > 1 || modelValue.preliminary" @click="remove(index)">移除此项</button>
    </div>
    <FormGrid>
      <label>订单号 *<a-input :value="row.orderNo" @update:value="change(index, 'orderNo', $event)" /></label>
      <label>票号（无票可空）<a-input :value="row.ticketNo" @update:value="change(index, 'ticketNo', $event)" /></label>
      <label
        >平台 *<a-select
          :value="row.platform"
          :options="options(['平台A', '平台B'])"
          @update:value="change(index, 'platform', String($event))"
      /></label>
      <label
        >业务 *<a-select
          :value="row.business"
          :options="options(['出票', '退票', '改签'])"
          @update:value="change(index, 'business', String($event))"
      /></label>
      <label>原币金额 *<a-input :value="row.amount" @update:value="change(index, 'amount', $event)" /></label>
      <label>PNR<a-input :value="row.pnr" @update:value="change(index, 'pnr', $event)" /></label>
    </FormGrid>
  </article>
  <button :disabled="rows.length >= 20" @click="add">＋ 添加订单子项</button>
  <p class="callout">本版单条ADM录入，子项先交组长接收，再由组长转交并督办。具体错误类型为演练字典，正式字典待补。</p>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import FormGrid from '../../src/components/FormGrid.vue'
import DateField from '../../src/components/DateField.vue'
import { rowsFromText, rowsToText, referenceAmount, specificTypes, type IntakeRow } from './intake'
import type { SimState } from './model'
const props = defineProps<{ modelValue: Record<string, any>; types?: string[]; state?: SimState }>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, any>] }>()
const options = (values: string[]) => values.map((value) => ({ value, label: value }))
const set = (key: string, value: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: value })
const rows = computed(() => rowsFromText(props.modelValue.rows || ''))
const reference = computed(() => {
  try {
    return referenceAmount(props.modelValue.amount, props.modelValue.currency, props.modelValue.rate || '')
  } catch {
    return ''
  }
})
function change(index: number, key: keyof IntakeRow, value: string) {
  const result = rows.value
  result[index]![key] = value
  set('rows', rowsToText(result))
}
function add() {
  set(
    'rows',
    rowsToText([
      ...rows.value,
      { orderNo: '', ticketNo: '', platform: '平台A', business: '出票', amount: '', pnr: '' },
    ]),
  )
}
function remove(index: number) {
  set('rows', rowsToText(rows.value.filter((_, rowIndex) => rowIndex !== index)))
}
function currencyChanged(value: unknown) {
  const currency = String(value)
  const rate =
    currency === 'CNY' ? '1' : props.state?.rules?.rates.find((item) => item.currency === currency)?.rate || ''
  emit('update:modelValue', { ...props.modelValue, currency, rate })
}
function supplierChanged(value: string) {
  const supplier = props.state?.rules?.suppliers.find((item) => item.name === value)
  emit('update:modelValue', {
    ...props.modelValue,
    supplier: value,
    ...(supplier ? { currency: supplier.currency, rate: supplier.rate } : {}),
  })
}
const candidateMessage = ref('')
function recognize() {
  let found = 0
  const next = rows.value.map((row) => {
    const candidates =
      props.state?.cases
        .filter((item) => !item.historyOnly)
        .flatMap((item) => item.lines)
        .filter(
          (line) => (row.orderNo && line.orderNo === row.orderNo) || (row.ticketNo && row.ticketNo === line.ticketNo),
        ) || []
    const unique = [...new Map(candidates.map((line) => [`${line.orderNo}|${line.platform}`, line])).values()]
    if (unique.length !== 1) return row
    found++
    const line = unique[0]!
    return {
      ...row,
      orderNo: line.orderNo,
      platform: line.platform,
      business: line.business,
      pnr: line.pnr,
      ticketNo: row.ticketNo || line.ticketNo,
    }
  })
  set('rows', rowsToText(next))
  candidateMessage.value = `已带出${found}条本地唯一候选，请人工核对。未命中或多候选保持原值；未连接真实订单接口。`
}
</script>
