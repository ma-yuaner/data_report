<template>
  <section class="filter-panel">
    <div class="filter-fields"><slot /></div>
    <div class="filter-actions"><span><FilterOutlined /> 条件即时生效</span><a-button @click="$emit('reset')"><ReloadOutlined />重置</a-button></div>
  </section>
</template>

<script setup lang="ts">
import { FilterOutlined, ReloadOutlined } from '@ant-design/icons-vue'

defineEmits<{ reset: [] }>()
</script>

<style scoped>
.filter-panel { margin-bottom: 16px; padding: 16px; display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; border: 1px solid #e4e9ef; border-radius: 14px; background: #fff; box-shadow: 0 7px 24px rgba(31, 49, 73, .035); }
.filter-fields { min-width: 0; flex: 1; display: grid; grid-template-columns: repeat(5, minmax(150px, 1fr)); gap: 12px; }
.filter-fields :deep(label) { min-width: 0; display: grid; gap: 6px; }
.filter-fields :deep(label > span:first-child) { color: #69768a; font-size: 10px; font-weight: 600; }
.filter-fields :deep(.ant-picker), .filter-fields :deep(.ant-select), .filter-fields :deep(.ant-input-affix-wrapper) { width: 100%; }
.filter-actions { display: flex; align-items: center; gap: 12px; }
.filter-actions > span { color: #96a0af; font-size: 10px; white-space: nowrap; }
@media (max-width: 1200px) { .filter-panel { align-items: stretch; flex-direction: column; }.filter-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }.filter-actions { justify-content: flex-end; } }
@media (max-width: 760px) { .filter-fields { grid-template-columns: 1fr; } }
</style>
