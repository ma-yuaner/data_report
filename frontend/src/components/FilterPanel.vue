<template>
  <section class="filter-panel" :class="{ 'filter-panel-stacked': stacked }">
    <div v-if="$slots.header" class="filter-heading"><slot name="header" /></div>
    <div v-if="$slots.period" class="filter-period"><slot name="period" /></div>
    <div v-if="$slots.default" class="filter-fields"><slot /></div>
    <div class="filter-actions">
      <span><FilterOutlined /> {{ hint || (instant ? '条件即时生效' : '修改条件后点击查询') }}</span>
      <slot name="actions" />
      <a-button v-if="showReset" :disabled="loading" @click="$emit('reset')"><ReloadOutlined />重置</a-button>
    </div>
    <div v-if="$slots.footer" class="filter-footer"><slot name="footer" /></div>
  </section>
</template>

<script setup lang="ts">
import { FilterOutlined, ReloadOutlined } from '@ant-design/icons-vue'

withDefaults(defineProps<{ instant?: boolean; stacked?: boolean; hint?: string; loading?: boolean; showReset?: boolean }>(), { instant: true, stacked: false, hint: '', loading: false, showReset: true })
defineEmits<{ reset: [] }>()
</script>

<style scoped>
.filter-panel { margin-bottom: 16px; padding: 16px; display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; border: 1px solid #e4e9ef; border-radius: 8px; background: #fff; }
.filter-fields { min-width: 0; flex: 1; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(150px, 100%), 1fr)); gap: 12px; }
.filter-fields :deep(label) { min-width: 0; display: grid; gap: 6px; }
.filter-fields :deep(label > span:first-child) { color: #69768a; font-size: 13px; font-weight: 500; }
.filter-fields :deep(label small) { margin-left: 6px; color: #69768a; font-size: 12px; }
.filter-fields :deep(.ant-picker), .filter-fields :deep(.ant-select), .filter-fields :deep(.ant-input-affix-wrapper) { width: 100%; }
.filter-actions { min-width: 0; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.filter-actions :deep(> div) { display: flex; gap: 8px; flex-wrap: wrap; }
.filter-actions > span { color: #69768a; font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.filter-panel-stacked { display: flex; flex-direction: column; align-items: stretch; gap: 16px; }
.filter-panel-stacked .filter-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.filter-panel-stacked .filter-actions { border-top: 1px solid #edf0f5; padding-top: 14px; }
.filter-panel-stacked .filter-actions > span { flex: 1 1 180px; min-width: 0; }
.filter-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.filter-heading :deep(h2) { margin: 0; font-size: 14px; color: #26344b; }
.filter-heading :deep(span) { color: #69768a; font-size: 12px; }
.filter-period { min-width: 0; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.filter-period :deep(.ant-segmented) { max-width: 100%; overflow-x: auto; }
.filter-period :deep(.ant-segmented-group) { min-width: max-content; }
.filter-footer:empty { display: none; }
@media (max-width: 1200px) { .filter-panel { align-items: stretch; flex-direction: column; }.filter-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }.filter-actions { justify-content: flex-end; } }
@media (max-width: 760px) { .filter-fields { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .filter-panel-stacked .filter-fields { grid-template-columns: 1fr; } }
</style>
