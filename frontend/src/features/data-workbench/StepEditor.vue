<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { Dataset, Field, Step } from './types'
const props = defineProps<{ fields: Field[]; datasets: Dataset[]; edit?: Step }>()
const emit = defineEmits<{ apply: [Step]; cancel: [] }>()
const state = reactive({
  op: 'trim',
  columns: [] as string[],
  column: '',
  type: 'decimal',
  from: '',
  to: '',
  operator: 'eq',
  value: '',
  name: '',
  kind: 'subtract',
  left: '',
  right: '',
  then: '',
  else: '',
  keys: [] as string[],
  fn: 'sum',
  rightSourceId: '',
  leftKeys: [] as string[],
  rightKeys: [] as string[],
  how: 'left',
  mapping: {} as Record<string, string>,
})
const error = reactive({ message: '' })
const options = computed(() => props.fields.map((f) => ({ value: f.id, label: `${f.name} · ${f.id}` })))
const right = computed(() => props.datasets.find((d) => d.id === state.rightSourceId))
const rightOptions = computed(
  () => right.value?.fields.map((f) => ({ value: f.id, label: `${f.name} · ${f.id}` })) || [],
)
const operations = [
  { value: 'trim', label: '去除首尾空格' },
  { value: 'replace', label: '精确值替换' },
  { value: 'cast', label: '转换类型' },
  { value: 'filter', label: '筛选行' },
  { value: 'derive', label: '新增计算字段' },
  { value: 'group', label: '分组汇总' },
  { value: 'join', label: '关联数据集' },
  { value: 'append', label: '追加数据集' },
  { value: 'select', label: '保留字段' },
]
const comparisons = [
  { value: 'eq', label: '等于' },
  { value: 'ne', label: '不等于' },
  { value: 'gt', label: '大于' },
  { value: 'gte', label: '大于等于' },
  { value: 'lt', label: '小于' },
  { value: 'lte', label: '小于等于' },
  { value: 'contains', label: '包含' },
  { value: 'is_null', label: '为空值' },
  { value: 'not_null', label: '不为空值' },
]
watch(
  () => props.edit,
  (value) => {
    if (value) {
      Object.assign(state, JSON.parse(JSON.stringify(value)))
      const aggs = value.aggregations as { column: string; fn: string; name: string }[] | undefined
      if (aggs?.[0]) Object.assign(state, aggs[0])
    }
  },
  { immediate: true },
)
function resetRightFields() {
  state.rightKeys = []
  state.mapping = {}
}
function apply() {
  error.message = ''
  const unique =
    globalThis.crypto?.randomUUID?.().replaceAll('-', '') ||
    `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
  const s: Step = { id: props.edit?.id || `s${unique}`, op: state.op }
  if (['trim', 'select'].includes(s.op)) {
    if (!state.columns.length) return void (error.message = '请选择至少一个字段')
    s.columns = [...state.columns]
  }
  if (['replace', 'cast', 'filter'].includes(s.op)) {
    if (!state.column) return void (error.message = '请选择字段')
    s.column = state.column
  }
  if (s.op === 'replace') Object.assign(s, { from: state.from, to: state.to })
  if (s.op === 'cast') s.type = state.type
  if (s.op === 'filter') Object.assign(s, { operator: state.operator, value: state.value })
  if (s.op === 'derive') {
    if (!state.name.trim() || !state.left) return void (error.message = '请填写新字段名称和左字段')
    Object.assign(s, {
      name: state.name.trim(),
      kind: state.kind,
      left: state.left,
      ...(state.right ? { right: state.right } : { value: state.value }),
      operator: state.operator,
      then: state.then,
      else: state.else,
    })
  }
  if (s.op === 'group') {
    if (!state.column || !state.name.trim()) return void (error.message = '请选择汇总字段并填写输出名称')
    Object.assign(s, {
      keys: [...state.keys],
      aggregations: [{ column: state.column, fn: state.fn, name: state.name.trim() }],
    })
  }
  if (['join', 'append'].includes(s.op)) {
    if (!state.rightSourceId) return void (error.message = '请选择右侧数据集')
    s.rightSourceId = state.rightSourceId
  }
  if (s.op === 'join') {
    if (!state.leftKeys.length || state.leftKeys.length !== state.rightKeys.length)
      return void (error.message = '左右关联字段数量必须相同且不为空，按选择顺序一一对应')
    Object.assign(s, { leftKeys: [...state.leftKeys], rightKeys: [...state.rightKeys], how: state.how })
  }
  if (s.op === 'append') {
    if (props.fields.some((f) => !state.mapping[f.id])) return void (error.message = '请为每个左字段显式选择右字段')
    s.mapping = { ...state.mapping }
  }
  emit('apply', s)
}
</script>
<template>
  <form class="step-editor" @submit.prevent="apply">
    <label>操作<a-select v-model:value="state.op" :options="operations" /></label>
    <label v-if="['trim', 'select'].includes(state.op)"
      >字段<a-select v-model:value="state.columns" mode="multiple" :options="options" option-filter-prop="label"
    /></label>
    <label v-if="['replace', 'cast', 'filter', 'group'].includes(state.op)"
      >字段<a-select v-model:value="state.column" :options="options" show-search option-filter-prop="label"
    /></label>
    <template v-if="state.op === 'replace'"
      ><label>原值<a-input v-model:value="state.from" /></label><label>替换为<a-input v-model:value="state.to" /></label
      ><small>精确替换整个值，不是正则或子串替换。</small></template
    >
    <label v-if="state.op === 'cast'"
      >目标类型<a-select
        v-model:value="state.type"
        :options="[
          { value: 'text', label: '文本' },
          { value: 'decimal', label: '精确数值（6位小数）' },
          { value: 'date', label: '日期' },
        ]"
    /></label>
    <template v-if="state.op === 'filter' || (state.op === 'derive' && state.kind === 'condition')"
      ><label>比较方式<a-select v-model:value="state.operator" :options="comparisons" /></label
      ><label v-if="!['is_null', 'not_null'].includes(state.operator)"
        >比较值<a-input v-model:value="state.value" /></label
    ></template>
    <template v-if="state.op === 'derive'">
      <label>新字段名称<a-input v-model:value="state.name" /></label>
      <label
        >计算方式<a-select
          v-model:value="state.kind"
          :options="[
            { value: 'add', label: '加' },
            { value: 'subtract', label: '减' },
            { value: 'multiply', label: '乘' },
            { value: 'divide', label: '除（6位小数）' },
            { value: 'concat', label: '文本拼接' },
            { value: 'condition', label: '条件分类' },
          ]"
      /></label>
      <label
        >左字段<a-select v-model:value="state.left" :options="options" show-search option-filter-prop="label"
      /></label>
      <template v-if="state.kind !== 'condition'"
        ><label
          >右字段（留空则使用固定值）<a-select
            v-model:value="state.right"
            allow-clear
            :options="options"
            show-search
            option-filter-prop="label" /></label
        ><label v-if="!state.right">固定值<a-input v-model:value="state.value" /></label
      ></template>
      <template v-else
        ><label>满足条件时<a-input v-model:value="state.then" /></label
        ><label>否则<a-input v-model:value="state.else" /></label
      ></template>
    </template>
    <template v-if="state.op === 'group'"
      ><label
        >分组字段（可为空，汇总全表）<a-select v-model:value="state.keys" mode="multiple" :options="options" /></label
      ><label
        >汇总方式<a-select
          v-model:value="state.fn"
          :options="[
            { value: 'sum', label: '合计' },
            { value: 'count', label: '计数' },
            { value: 'min', label: '最小值' },
            { value: 'max', label: '最大值' },
          ]" /></label
      ><label>汇总字段名称<a-input v-model:value="state.name" /></label
    ></template>
    <template v-if="['join', 'append'].includes(state.op)"
      ><label
        >右侧数据集<a-select
          v-model:value="state.rightSourceId"
          :options="datasets.map((d) => ({ value: d.id, label: d.name }))"
          @change="resetRightFields" /></label
    ></template>
    <template v-if="state.op === 'join'"
      ><label>左关联字段（按顺序）<a-select v-model:value="state.leftKeys" mode="multiple" :options="options" /></label
      ><label
        >右关联字段（对应顺序）<a-select
          v-model:value="state.rightKeys"
          mode="multiple"
          :options="rightOptions" /></label
      ><label
        >关联方式<a-select
          v-model:value="state.how"
          :options="[
            { value: 'left', label: '左关联' },
            { value: 'inner', label: '仅匹配项' },
            { value: 'full', label: '全部保留' },
            { value: 'anti', label: '仅左侧未匹配' },
          ]" /></label
      ><small>执行前由服务端校验关联基数；超限不可绕过，请增加关联字段或先汇总。</small></template
    >
    <template v-if="state.op === 'append'"
      ><label v-for="field in fields" :key="field.id"
        >{{ field.name }} · {{ field.id }} 对应右字段<a-select
          v-model:value="state.mapping[field.id]"
          :options="rightOptions" /></label
      ><small>追加保留重复行，不自动去重。</small></template
    >
    <p v-if="error.message" role="alert" class="editor-error">{{ error.message }}</p>
    <div class="editor-actions">
      <a-button @click="emit('cancel')">取消</a-button
      ><a-button type="primary" html-type="submit">{{ edit ? '更新步骤' : '加入步骤' }}</a-button>
    </div>
  </form>
</template>
<style scoped>
.step-editor {
  display: grid;
  gap: 14px;
}
.step-editor label {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.step-editor :deep(.ant-select) {
  width: 100%;
  min-width: 0;
}
.step-editor small {
  color: #64748b;
  line-height: 1.6;
}
.editor-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  position: sticky;
  bottom: 0;
  background: white;
  padding: 12px 0;
}
.editor-error {
  color: #b42318;
  overflow-wrap: anywhere;
}
</style>
