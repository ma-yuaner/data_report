<template>
  <template v-if="configuration?.ruleId">
    <a-button type="link" size="small" class="basis-trigger" @click="open = true">查看采用依据</a-button>
    <a-modal v-model:open="open" title="采用依据" :width="800" :footer="null" :destroy-on-close="true" :mask-closable="false" :style="{ maxWidth: 'calc(100vw - 32px)', top: '5vh' }" :body-style="{ maxHeight: '75vh', overflowY: 'auto' }">
    <div class="configuration-basis">
    <div class="basis-heading"><span>出票明细 {{ ticket.id }}</span><strong>采用规则 {{ configuration.ruleId }} <span class="muted">· v{{ configuration.configurationVersion ?? '未记录' }}</span></strong></div>
    <a-alert v-if="configuration.basis === 'issue_time_configuration' && configuration.asOf && configuration.historyProof" type="info" show-icon :message="`按出票时点 ${formatDateTimeDisplay(configuration.asOf)} 的配置核实`" />
    <a-alert v-else type="warning" show-icon message="出票时历史证明不完整" description="本快照未提供完整出票时历史证明，不能仅凭观察到的配置认定出票时有效。" />
    <p v-if="selected?.updateTime">该配置版本更新时间：{{ formatDateTimeDisplay(selected.updateTime) }}</p>
    <h4>具体匹配条件</h4>
    <div v-if="conditions.length" class="conditions-wrap"><table class="conditions-table">
      <thead><tr><th scope="col">条件</th><th scope="col">规则要求</th><th scope="col">本单实际</th><th scope="col">匹配结果</th></tr></thead>
      <tbody><tr v-for="condition in conditions" :key="condition.field"><th scope="row">{{ condition.label || condition.field }}</th><td>{{ condition.value === '' ? '不限' : condition.value }}</td><td>{{ condition.actual ?? configuration.matchingFacts?.[condition.field] ?? '未记录' }}</td><td>{{ conditionLabels[condition.outcome || ''] || '该项匹配结果未记录' }}</td></tr></tbody>
    </table></div>
    <p v-else class="muted">该历史结果未记录逐项匹配条件，需重新清洗后查看，不能据此补造匹配事实。</p>
    <h4>本票阈值如何取得</h4>
    <p>单票航段数：{{ ticket.segmentCount ?? '未记录' }} 段。</p>
    <p>采用配置项 {{ configuration.jsonPath || '未记录' }}，基础阈值 {{ configuration.baseAmount ?? '未记录' }} 元。</p>
    <p v-if="configuration.extraSegments != null && configuration.extraSegments > 0">超出4段部分：{{ configuration.extraSegments }} 段 × {{ configuration.extraPerSegment ?? '未记录' }} 元。</p>
    <p v-if="configuration.baseAmount != null && configuration.extraSegments != null && configuration.extraSegments > 0 && configuration.extraPerSegment != null">最终阈值：{{ configuration.baseAmount }} ＋ {{ configuration.extraSegments }} × {{ configuration.extraPerSegment }} ＝ {{ ticket.stopLoss ?? '未记录' }} 元。</p>
    <div class="threshold-result"><span>最终采用阈值</span><strong>{{ ticket.stopLoss ?? '未记录' }} 元</strong></div>
    </div>
    </a-modal>
  </template>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, Modal as AModal } from 'ant-design-vue'
import { type AutoRiskResult } from '@/api/riskVerification'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const props = defineProps<{ ticket: AutoRiskResult['tickets'][number] }>()
const open = ref(false)
watch(() => props.ticket, () => { open.value = false })
const configuration = computed(() => props.ticket.configuration)
// Read only the selected rule's recorded conditions, never the other candidate rows.
const selected = computed(() => configuration.value?.candidateTrace?.find(item => String(item.ruleId) === String(configuration.value?.ruleId)))
const conditions = computed(() => selected.value?.conditions || [])
const conditionLabels: Record<string, string> = {
  matched: '匹配符合', excluded: '该项不符合，请核对清洗结果', unknown: '该项证据不足',
  rank_only: '此类规则不按该项限制适用范围',
}
</script>
<style scoped>
.basis-trigger{display:block;padding-left:0;height:auto;margin-top:6px}
.configuration-basis{white-space:normal;overflow-wrap:anywhere;color:#253247}
.basis-heading{display:grid;gap:6px;margin-bottom:16px;padding-right:16px}.basis-heading>span{font-size:12px;color:#69768a}.basis-heading strong{font-size:16px}
p{margin:10px 0;line-height:1.7}h4{font-size:14px;margin:20px 0 10px}.muted{color:#69768a;font-size:13px;font-weight:400}
.conditions-wrap{overflow-x:auto}.conditions-table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px}.conditions-table th,.conditions-table td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #e5eaf0;overflow-wrap:anywhere}.conditions-table thead{background:#f5f7fa}.conditions-table th{font-weight:500}
.threshold-result{display:flex;justify-content:space-between;align-items:baseline;gap:16px;background:#f0f5ff;border:1px solid #dce6f5;padding:12px 14px;border-radius:6px;margin-top:14px}.threshold-result strong{font-size:20px;color:#245bbb;text-align:right}
@media(max-width:520px){.conditions-table th,.conditions-table td{padding:8px 4px;font-size:12px}.threshold-result strong{font-size:17px}}
</style>
