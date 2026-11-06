<template>
  <section class="evidence-panel">
    <div class="actions"><strong>配置证据留存</strong><a-button v-if="canReview && !saved" :loading="busy" :disabled="loading || !currentResult || currentResult.isCurrent === false" @click="save">保存本次核对配置证据</a-button><a-button v-if="canCheck && saved" :loading="busy" :disabled="loading" @click="observe">观察最新单票止损值</a-button></div>
    <a-alert v-if="error" type="error" show-icon :message="error" />
    <p v-if="loading" class="muted">正在读取已保存的原核对证据。</p>
    <p v-if="!saved && !loading && !error" class="muted">尚未固定原核对。保存后保留原配置、单票止损及核对结论，后续清洗或配置更新不覆盖该证据。</p>
    <template v-if="saved">
      <p>原核对已固定于 {{ formatDateTimeDisplay(saved.savedAt) }} · 保存账号 {{ saved.savedBy }}。</p>
      <a-alert v-if="currentResult && saved.original.id !== currentResult.id" type="warning" show-icon message="当前清洗事实已变化，下表保留已固定的原核对；人工重新核实仍以当前事实为准" />
      <p v-for="ticket in saved.original.tickets" :key="`basis-${ticket.id}`" class="muted">票 {{ ticket.id }}：{{ ticket.configuration?.basis === 'issue_time_configuration' && ticket.configuration?.asOf && ticket.configuration?.historyProof ? '已记录出票时配置历史证明' : '历史有效性未证实，仅保留原取证值，不自动视为出票时有效' }}。</p>
      <p class="muted">最新值仅为原关联规则的当前观察，未重新匹配本单，不参与原单核算。源更新时间和本次观察时间不等于该变更实际生效时间。</p>
      <p v-if="latest">最近观察 {{ formatDateTimeDisplay(latest.observedAt) }} · {{ latest.hasUnavailable ? '部分最新值未取得，不能解释为无变化' : latest.changed ? '有数值或配置版本变化' : latest.hasUnknownComparison ? '比较依据不全，不能确认全部配置是否变化' : '本次未发现可确认的数值或配置变化' }}</p>
      <p v-else class="muted">尚未观察最新值，不能解释为配置未变化。</p>
      <details v-if="observations.length"><summary>配置观察与变化记录（最近 {{ observations.length }} 次）</summary><div v-for="item in observations" :key="item.id" class="observation"><strong>{{ formatDateTimeDisplay(item.observedAt) }} · 观察账号 {{ item.observedBy }}</strong><p v-for="ticket in item.tickets" :key="ticket.ticketId">票 {{ ticket.ticketId }} / 规则 {{ ticket.ruleId || '未关联' }}：原值 {{ value(ticket.originalStopLoss) }}；上次 {{ value(ticket.beforeStopLoss) }} → 本次 {{ value(ticket.latestStopLoss) }}<br />源版本 {{ ticket.sourceVersion ?? '未知' }}；源更新时间 {{ formatDateTimeDisplay(ticket.sourceUpdatedAt) }}；当前配置登记有效期 {{ formatDateTimeDisplay(ticket.sourceStart) }} 至 {{ formatDateTimeDisplay(ticket.sourceEnd) }}。{{ ticket.effectiveTimeBasis }}。{{ ticket.reason }}<span v-if="ticket.sourceCurrentlyEffective !== true">；当前规则非有效启用或有效期无法确认</span></p></div><p v-if="saved.historyTruncated">仅展示最近500次观察，更早历史仍保留。</p></details>
    </template>
  </section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, message } from 'ant-design-vue'
import { type AutoRiskResult } from '@/api/riskVerification'
import { riskConfigEvidence, type ConfigEvidence, type ConfigObservation } from '@/api/riskConfigEvidence'
import { reviewKey } from '@/api/riskFollowup'
import { useRiskPermissions } from '@/composables/useRiskPermissions'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const props = defineProps<{ orderId: string; issueDate: string; currentResult: AutoRiskResult | null }>()
const emit = defineEmits<{ pinned: [AutoRiskResult | null]; observed: [ConfigObservation | null]; 'busy-change': [boolean] }>()
const { canReview, canCheck } = useRiskPermissions()
const saved = ref<ConfigEvidence | null>(null), latest = ref<ConfigObservation | null>(null), observations = ref<ConfigObservation[]>([])
const busy = ref(false), loading = ref(false), error = ref('')
let epoch = 0, requestId = ''
const value = (v: string | null) => v == null ? '未取得' : `${v} 元`
watch([busy, loading], ([b, l]) => emit('busy-change', b || l))
watch(() => props.currentResult?.id, () => { void load() }, { immediate: true })
onBeforeUnmount(() => { epoch++ })
function apply(v: ConfigEvidence | null) { saved.value = v; latest.value = v?.latest || null; observations.value = v?.observations || []; emit('pinned', v?.original || null); emit('observed', latest.value) }
async function load() {
  const token = ++epoch; loading.value = true; error.value = ''
  try { const v = await riskConfigEvidence.get(props.orderId, props.issueDate); if (token === epoch) apply(v) }
  catch (e) { if (token === epoch) error.value = e instanceof Error ? e.message : '配置证据读取失败' }
  finally { if (token === epoch) loading.value = false }
}
async function save() {
  if (busy.value || !props.currentResult) return
  busy.value = true; error.value = ''
  try { const v = await riskConfigEvidence.save(props.orderId, props.issueDate, props.currentResult.id); apply(v); message.success(v.alreadySaved ? '已有原核对证据，已保留原记录' : '原核对证据已保存') }
  catch (e) { error.value = e instanceof Error ? e.message : '证据保存失败' }
  finally { busy.value = false }
}
async function observe() {
  if (busy.value || !saved.value) return
  busy.value = true; error.value = ''
  try { requestId ||= reviewKey(); const v = await riskConfigEvidence.observe(props.orderId, props.issueDate, requestId); latest.value = v; observations.value = [v, ...observations.value.filter(o => o.id !== v.id)].slice(0, 500); emit('observed', v); requestId = ''; message.success('最新观察已保存，原核对未改变') }
  catch (e) { error.value = e instanceof Error ? e.message : '观察失败，保留上次成功提醒' }
  finally { busy.value = false }
}
</script>
<style scoped>.evidence-panel{padding:16px;border:1px solid #dce6f5;border-radius:6px;background:#fafcff}.actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.muted{color:#738298;font-size:12px}p{margin:10px 0;overflow-wrap:anywhere}summary{cursor:pointer;color:#2c68d7}.observation{border-top:1px solid #e5eaf0;padding:12px 0}</style>
