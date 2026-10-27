<template>
  <aside class="prd" :aria-label="label">
    <div class="prd-heading">
      <span>{{ label }}</span><strong>{{ title }}</strong><small>{{ subtitle }}</small>
    </div>
    <div class="prd-tabs" aria-label="说明分类">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: modelValue === tab.id }"
        :aria-pressed="modelValue === tab.id" @click="emit('update:modelValue', tab.id)">{{ tab.title }}</button>
    </div>
    <div class="prd-content"><slot :tab="modelValue" /></div>
    <div v-if="$slots.footer" class="prd-footer"><slot name="footer" /></div>
  </aside>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: string
  title: string
  subtitle: string
  tabs: readonly { id: string; title: string }[]
  label?: string
}>(), { label: '右侧 · 当前步骤 PRD' })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
