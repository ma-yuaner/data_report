<template>
  <PlacementField label="参考舱位" state="只读参考" hint="ERP近一个月维护，仅作参考；窗口内每30秒自动刷新，不保存、不参与业务规则。">
    <a-textarea :value="display" disabled :auto-size="{ minRows: 1, maxRows: 3 }" aria-label="航司近期参考舱位（只读）" />
    <div class="reference-actions">
      <a-button type="link" size="small" :loading="loading" :disabled="!active || !airline?.trim() || loading" @click="load">{{ error ? '重试' : '刷新' }}</a-button>
      <span v-if="lastReadAt">最近读取：{{ lastReadAt }}</span>
    </div>
    <p v-if="error" class="reference-message reference-error" role="status">{{ error }}{{ lastReadAt ? '；当前展示为上次读取结果。' : '' }}</p>
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
const lastReadAt = ref('')
let version = 0
let refreshTimer: ReturnType<typeof setInterval> | undefined
const display = computed(() => !props.airline?.trim() ? '选择航司后展示' : lastReadAt.value ? (cabins.value.length ? cabins.value.join('\n') : '暂无近期参考舱位') : loading.value ? '正在读取参考舱位…' : error.value ? '暂不可用' : '暂无近期参考舱位')
async function load() {
  const airline = props.airline?.trim().toUpperCase()
  if (!props.active || !airline || loading.value) return
  const current = ++version
  loading.value = true
  error.value = ''
  try {
    const result = await fetchCabinReference(airline)
    if (current !== version || !props.active) return
    cabins.value = result.cabins
    hasUnspecified.value = result.hasUnspecified
    lastReadAt.value = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
  } catch (reason) {
    if (current === version && props.active) error.value = reason instanceof Error ? reason.message : '参考舱位读取失败'
  } finally { if (current === version) loading.value = false }
}
function stopRefresh() {
  if (refreshTimer !== undefined) clearInterval(refreshTimer)
  refreshTimer = undefined
}
watch(() => [props.active, props.airline] as const, () => {
  stopRefresh()
  version++
  cabins.value = []
  hasUnspecified.value = false
  lastReadAt.value = ''
  error.value = ''
  loading.value = false
  if (!props.active || !props.airline?.trim()) return
  void load()
  refreshTimer = setInterval(() => { void load() }, 30_000)
}, { immediate: true })
onBeforeUnmount(() => { version++; stopRefresh() })
</script>

<style scoped>
.reference-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 4px; font-size: 12px; color: #8a95a8; }
.reference-message { margin: 5px 0 0; font-size: 12px; color: #8a95a8; }.reference-error { color: #b54708; }
</style>
