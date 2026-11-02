<template>
  <div class="location-select">
    <a-select :value="type" :options="typeOptions" :aria-label="`${label}类型`" @change="changeType" />
    <a-input v-if="type === 'LEGACY'" :value="code" :aria-label="label" placeholder="原城市或机场编码" @update:value="emit('update:code', $event)" />
    <a-select v-else :value="code || undefined" :options="options" :loading="loading" :filter-option="false" show-search allow-clear
      :aria-label="label" :placeholder="type === 'COUNTRY' ? '国家二字码，如 CN' : type === 'CITY' ? '城市三字码，如 SHA' : '机场码或名称，如 PVG'"
      :not-found-content="loading ? '加载中' : error ? '加载失败，请重试' : '没有匹配地点'"
      @search="search" @change="emit('update:code', String($event || ''))" @focus="load('')" />
  </div>
  <p v-if="error" class="location-error">{{ error }} <a-button type="link" size="small" @click="load(keyword)">重试</a-button></p>
  <p v-else class="location-hint">{{ type === 'LEGACY' ? '历史条件保持原匹配方式；切换类型后按新类型匹配。' : '留空表示不限；城市、国家覆盖其下有效机场。' }}<span v-if="truncated"> 输入关键词查看更多。</span></p>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { fetchPlacementLocations, type PlacementLocationType } from '@/api/smartPlacement'

const props = withDefaults(defineProps<{ type?: PlacementLocationType; code?: string; label: string }>(), { type: 'AIRPORT', code: '' })
const emit = defineEmits<{ 'update:type': [value: PlacementLocationType]; 'update:code': [value: string] }>()
const rows = ref<{ value: string; label: string }[]>([])
const loading = ref(false)
const error = ref('')
const truncated = ref(false)
let requestNo = 0
let timer: ReturnType<typeof setTimeout> | undefined
const keyword = ref('')
const typeOptions = computed(() => [
  { value: 'AIRPORT', label: '机场' }, { value: 'CITY', label: '城市' }, { value: 'COUNTRY', label: '国家' },
  ...(props.type === 'LEGACY' ? [{ value: 'LEGACY', label: '历史条件' }] : []),
])
const regionNames = new Intl.DisplayNames(['zh-CN'], { type: 'region' })
function display(row: { value: string; label: string }) {
  if (props.type !== 'COUNTRY' || !/^[A-Z]{2}$/.test(row.value)) return row
  return { ...row, label: `${regionNames.of(row.value) || row.value}（${row.value}）` }
}
const options = computed(() => {
  const values = rows.value.map(display).filter(row => props.type !== 'COUNTRY' || !keyword.value || row.label.toUpperCase().includes(keyword.value.toUpperCase()))
  if (props.code && !values.some(row => row.value === props.code)) values.unshift(display({ value: props.code, label: props.code }))
  return values
})
function changeType(value: PlacementLocationType) {
  emit('update:code', '')
  emit('update:type', value)
}
async function load(value: string) {
  if (props.type === 'LEGACY') return
  const current = ++requestNo
  keyword.value = value
  loading.value = true; error.value = ''
  try {
    const result = await fetchPlacementLocations(props.type, props.type === 'COUNTRY' ? '' : value)
    if (current !== requestNo) return
    rows.value = result.rows; truncated.value = result.truncated
  } catch (failure) {
    if (current !== requestNo) return
    rows.value = []; error.value = failure instanceof Error ? failure.message : '地点加载失败'
  } finally { if (current === requestNo) loading.value = false }
}
function search(value: string) {
  if (props.type === 'COUNTRY') { keyword.value = value; return }
  clearTimeout(timer)
  ++requestNo
  timer = setTimeout(() => { void load(value) }, 250)
}
watch(() => props.type, () => { clearTimeout(timer); ++requestNo; rows.value = []; error.value = ''; loading.value = false; truncated.value = false; void load('') }, { immediate: true })
onBeforeUnmount(() => { clearTimeout(timer); ++requestNo })
</script>

<style scoped>
.location-select { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 8px; min-width: 0; }
.location-select > * { min-width: 0; width: 100%; }
.location-hint, .location-error { margin: 6px 0 0; font-size: 12px; line-height: 1.6; }
.location-hint { color: #7d8999; }.location-error { color: #c43f4f; }
</style>
