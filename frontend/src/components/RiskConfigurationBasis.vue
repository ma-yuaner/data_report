<template>
  <details v-if="configuration?.ruleId" class="configuration-basis">
    <summary>查看采用依据</summary>
    <p><strong>采用规则 {{ configuration.ruleId }} · v{{ configuration.configurationVersion ?? '未记录' }}</strong></p>
    <p v-if="configuration.basis === 'issue_time_configuration' && configuration.asOf && configuration.historyProof">按出票时点 {{ formatDateTimeDisplay(configuration.asOf) }} 的配置核实。</p>
    <p v-else class="muted">本快照未提供完整出票时历史证明，不能仅凭观察到的配置认定出票时有效。</p>
    <p v-if="selected?.updateTime">该配置版本更新时间：{{ formatDateTimeDisplay(selected.updateTime) }}</p>
    <h4>具体匹配条件</h4>
    <dl v-if="conditions.length">
      <div v-for="condition in conditions" :key="condition.field" class="condition">
        <dt>{{ condition.label || condition.field }}</dt>
        <dd>规则要求：{{ condition.value === '' ? '不限' : condition.value }}</dd>
        <dd>本单实际：{{ condition.actual ?? configuration.matchingFacts?.[condition.field] ?? '未记录' }}</dd>
        <dd>{{ conditionLabels[condition.outcome || ''] || '该项匹配结果未记录' }}</dd>
      </div>
    </dl>
    <p v-else class="muted">该历史结果未记录逐项匹配条件，需重新清洗后查看，不能据此补造匹配事实。</p>
    <h4>本票阈值如何取得</h4>
    <p>单票航段数：{{ ticket.segmentCount ?? '未记录' }} 段。</p>
    <p>采用配置项 {{ configuration.jsonPath || '未记录' }}，基础阈值 {{ configuration.baseAmount ?? '未记录' }} 元。</p>
    <p v-if="configuration.extraSegments != null && configuration.extraSegments > 0">超出4段部分：{{ configuration.extraSegments }} 段 × {{ configuration.extraPerSegment ?? '未记录' }} 元。</p>
    <p v-if="configuration.baseAmount != null && configuration.extraSegments != null && configuration.extraSegments > 0 && configuration.extraPerSegment != null">最终阈值：{{ configuration.baseAmount }} ＋ {{ configuration.extraSegments }} × {{ configuration.extraPerSegment }} ＝ {{ ticket.stopLoss ?? '未记录' }} 元。</p>
    <p v-else>最终采用阈值：{{ ticket.stopLoss ?? '未记录' }} 元。</p>
  </details>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { type AutoRiskResult } from '@/api/riskVerification'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const props = defineProps<{ ticket: AutoRiskResult['tickets'][number] }>()
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
.configuration-basis{margin-top:8px;max-width:400px;white-space:normal;overflow-wrap:anywhere}
summary{cursor:pointer;color:#2c68d7}p{margin:8px 0}h4{font-size:13px;margin:14px 0 6px}
dl{margin:0}.condition{border-top:1px solid #e5eaf0;padding:10px 0}.condition dt{font-weight:600;margin-bottom:4px}.condition dd{margin:3px 0}.muted{color:#738298}
</style>
