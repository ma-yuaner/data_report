<template>
  <PlacementField label="参考舱位" state="只读参考" hint="ERP近一个月维护，仅作参考；不保存、不参与业务规则。">
    <a-textarea :value="display" disabled :auto-size="{ minRows: 1, maxRows: 3 }" aria-label="航司近期参考舱位（只读）" />
    <p v-if="error" class="reference-message reference-error" role="status">{{ error }}<a-button type="link" size="small" :disabled="loading" @click="load">重试</a-button></p>
    <p v-else-if="hasUnspecified" class="reference-message">部分来源记录未明确配置具体舱位。</p>
  </PlacementField>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import PlacementField from '@/components/PlacementField.vue'
import { fetchCabinReference } from '@/api/placementCabinReference'

const props = defineProps<{ airline?: string; active: boolean }>()
const cabins = ref<string[]>([])
const hasUnspecified = ref(false)
const loading = ref(false)
const error = ref('')
let version = 0
const display = computed(() => !props.airline ? '选择航司后展示' : loading.value ? '正在读取参考舱位…' : error.value ? '暂不可用' : cabins.value.length ? cabins.value.join('、') : '暂无近期参考舱位')
async function load() {
  const current = ++version
  cabins.value = []; hasUnspecified.value = false; error.value = ''; loading.value = false
  const airline = props.airline?.trim().toUpperCase()
  if (!props.active || !airline) return
  loading.value = true
  try {
    const result = await fetchCabinReference(airline)
    if (current !== version || !props.active) return
    cabins.value = result.cabins; hasUnspecified.value = result.hasUnspecified
  } catch (reason) {
    if (current === version && props.active) error.value = reason instanceof Error ? reason.message : '参考舱位读取失败'
  } finally { if (current === version) loading.value = false }
}
watch(() => [props.active, props.airline] as const, () => { void load() }, { immediate: true })
onBeforeUnmount(() => { version++ })
</script>

<style scoped>
.reference-message { margin: 5px 0 0; font-size: 12px; color: #8a95a8; }.reference-error { color: #b54708; }
</style>
