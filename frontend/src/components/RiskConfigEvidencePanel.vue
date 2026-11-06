<template>
  <a-alert v-if="error" type="warning" show-icon message="历史核查读取失败，当前结果仍可查看" :description="error"><template #action><a-button size="small" :loading="loading" @click="load">重试</a-button></template></a-alert>
  <details v-if="items.length" class="check-history">
    <summary>历史核查记录（{{ items.length }} 个版本）</summary>
    <p class="muted">核查结果由清洗任务自动留存。查看历史不会改变当前结果或人工核实依据。</p>
    <div v-for="item in items" :key="item.versionKey" class="history-row"><span>{{ formatDateTimeDisplay(item.result.checkedAt) }}<br /><a-tag>{{ labels[item.result.status] || item.result.status }}</a-tag>{{ item.result.summary }}</span><a-button size="small" @click="emit('pinned', item.result)">查看当次核查</a-button></div>
    <a-button type="link" @click="emit('pinned', null)">返回当前核查</a-button>
    <p v-if="truncated" class="muted">仅展示最近50个变化版本，较早历史仍保留。</p>
  </details>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, Tag as ATag } from 'ant-design-vue'
import { type AutoRiskResult } from '@/api/riskVerification'
import { riskConfigEvidence } from '@/api/riskConfigEvidence'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const props = defineProps<{ orderId: string; issueDate: string; currentResult: AutoRiskResult | null }>()
const emit = defineEmits<{ pinned: [AutoRiskResult | null]; 'busy-change': [boolean] }>()
const items = ref<{ versionKey: string; result: AutoRiskResult }[]>([]), loading = ref(false), error = ref(''), truncated = ref(false)
const labels: Record<string,string> = { supported: '自动通过', problem: '疑似问题', insufficient: '证据不足', failed: '执行失败' }
let epoch = 0
watch(loading, value => emit('busy-change', value))
watch(() => props.currentResult?.id, () => { void load() }, { immediate: true })
onBeforeUnmount(() => { epoch++ })
async function load() {
 const token = ++epoch; loading.value = true; error.value = ''
 try { const history = await riskConfigEvidence.history(props.orderId, props.issueDate); if (token !== epoch) return; items.value = history.items.filter(item => item.validTo !== null || item.result.id !== props.currentResult?.id); truncated.value = history.truncated }
 catch (e) { if (token === epoch) { items.value = []; error.value = e instanceof Error ? e.message : '请重试或联系管理员核对清洗历史' } }
 finally { if (token === epoch) loading.value = false }
}
</script>
<style scoped>
.check-history{border-bottom:1px solid #e5eaf0;padding:12px 0}summary{cursor:pointer;color:#2c68d7}.muted{color:#738298;font-size:12px}.history-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 0;border-top:1px solid #edf0f4;overflow-wrap:anywhere}.history-row .ant-btn{flex-shrink:0}@media(max-width:600px){.history-row{align-items:flex-start;flex-direction:column}}
</style>
