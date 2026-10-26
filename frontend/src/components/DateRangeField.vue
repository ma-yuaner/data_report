<template>
  <div class="shared-date-range" role="group" :aria-label="label">
    <span class="range-label">{{ label }}</span>
    <DateField v-model="start" :allow-clear="allowClear" :disabled="disabled" aria-label="开始日期" placeholder="开始日期" @update:model-value="emit('change')" />
    <span class="range-separator">至</span>
    <DateField v-model="end" :allow-clear="allowClear" :disabled="disabled" aria-label="结束日期" placeholder="结束日期" @update:model-value="emit('change')" />
  </div>
</template>

<script setup lang="ts">
import DateField from './DateField.vue'
const start = defineModel<string>('start', { required: true })
const end = defineModel<string>('end', { required: true })
withDefaults(defineProps<{ label?: string; allowClear?: boolean; disabled?: boolean }>(), { label: '统计期间', allowClear: false, disabled: false })
const emit = defineEmits<{ change: [] }>()
</script>

<style scoped>
.shared-date-range { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.range-label { font-size: 13px; color: #69768a; }
.range-separator { color: #8995a7; }
.shared-date-range :deep(.shared-date-field) { width: 148px; }
@media (max-width: 480px) { .range-label { flex-basis: 100%; } .shared-date-range :deep(.shared-date-field) { flex: 1; width: 0; min-width: 110px; } }
</style>
