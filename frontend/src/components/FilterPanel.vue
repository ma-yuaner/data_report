<template>
  <section class="filter-panel" :class="{ 'filter-panel-stacked': stacked }">
    <div v-if="$slots.header" class="filter-heading"><slot name="header" /></div>
    <div v-if="$slots.period" class="filter-period"><slot name="period" /></div>
    <div class="filter-fields"><slot /></div>
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
.filter-panel { margin-bottom: 16px; padding: 16px; display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; border: 1px solid #e4e9ef; border-radius: 14px; background: #fff; box-shadow: 0 7px 24px rgba(31, 49, 73, .035); }
.filter-fields { min-width: 0; flex: 1; display: grid; grid-template-columns: repeat(5, minmax(150px, 1fr)); gap: 12px; }
.filter-fields :deep(label) { min-width: 0; display: grid; gap: 6px; }
.filter-fields :deep(label > span:first-child) { color: #69768a; font-size: 13px; font-weight: 500; }
.filter-fields :deep(label small) { margin-left: 6px; color: #8995a7; font-size: 12px; }
.filter-fields :deep(.ant-picker), .filter-fields :deep(.ant-select), .filter-fields :deep(.ant-input-affix-wrapper) { width: 100%; }
.filter-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.filter-actions :deep(> div) { display: flex; gap: 8px; flex-wrap: wrap; }
.filter-actions > span { color: #69768a; font-size: 12px; }
.filter-panel-stacked { display: flex; flex-direction: column; align-items: stretch; gap: 16px; }
.filter-panel-stacked .filter-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.filter-panel-stacked .filter-actions { border-top: 1px solid #edf0f5; padding-top: 14px; }
.filter-panel-stacked .filter-actions > span { flex: 1; min-width: 180px; }
.filter-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.filter-heading :deep(h2) { margin: 0; font-size: 14px; color: #26344b; }
.filter-heading :deep(span) { color: #69768a; font-size: 12px; }
.filter-period { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.filter-footer:empty { display: none; }
@media (max-width: 1200px) { .filter-panel { align-items: stretch; flex-direction: column; }.filter-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }.filter-actions { justify-content: flex-end; } }
@media (max-width: 760px) { .filter-fields { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .filter-panel-stacked .filter-fields { grid-template-columns: 1fr; } }
</style>
