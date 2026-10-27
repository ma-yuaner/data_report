<template>
  <header class="topbar">
    <div><strong>{{ title }}</strong><span class="version">{{ version }} · {{ status }}</span></div>
    <div class="toolbar">
      <button @click="emit('export')">导出体验与验收记录</button>
      <label class="file-button">导入记录<input type="file" accept=".json" @change="emit('import', $event)" /></label>
      <button v-if="canDetach" @click="emit('detach')">右侧单独窗口 ↗</button>
      <button @click="emit('update:showDocs', !showDocs)">{{ showDocs ? '收起说明' : '显示说明' }}</button>
      <slot />
    </div>
  </header>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  version: string
  status?: string
  canDetach?: boolean
  showDocs: boolean
}>(), { status: '待你审核', canDetach: true })
const emit = defineEmits<{
  export: []
  import: [event: Event]
  detach: []
  'update:showDocs': [value: boolean]
}>()
</script>
