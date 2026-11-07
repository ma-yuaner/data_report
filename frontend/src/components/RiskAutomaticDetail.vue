<template>
  <a-spin :spinning="busy">
    <div class="auto-detail">
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-alert v-if="latestReadError" type="warning" show-icon message="最新配置观察读取失败，原核查仍可查看" :description="latestReadError" />
      <p v-else-if="latestConfig?.publishedRun" class="muted">最新配置观察：{{ formatDateTimeDisplay(latestConfig.publishedRun.observedAt) }}；{{ previousObservationOnly ? '本次尚未完整更新，当前展示上次成功观察' : '最近完整发布结果' }}。每日06:00触发，不是页面打开时的实时配置。</p>
      <p v-if="latestConfig?.publishedRun?.runDay && latestConfig.publishedRun.runDay < latestConfig.expectedRunDay" class="muted">已到每日触发时点，{{ latestConfig.expectedRunDay }} 的成功观察尚未完整发布；当前显示旧成功结果。任务完成窗口尚未约定。</p>
      <p v-if="latestConfig?.latestAttempt && latestConfig.latestAttempt.status !== 'success'" class="muted">最近刷新尝试：{{ formatDateTimeDisplay(latestConfig.latestAttempt.startedAt) }}；{{ ({ failed: '刷新失败', partial: '部分处理，待续跑', running: '刷新中', skipped: '本次跳过' } as Record<string, string>)[latestConfig.latestAttempt.status] || latestConfig.latestAttempt.status }}<span v-if="latestConfig.latestAttempt.lastError">（{{ latestConfig.latestAttempt.lastError }}）</span>。最后成功观察仍保留。</p>
      <RiskConfigEvidencePanel v-if="issueDate" :order-id="orderId" :issue-date="issueDate" :current-result="currentResult" @pinned="showPinned" @busy-change="evidenceBusy = $event" />
      <a-alert v-if="!supportedReason" type="info" show-icon message="该类型规则尚未接入" description="后续为此类型补充专属证据和规则，不套用佣金亏损公式。" />
      <a-alert v-else-if="!result" type="info" show-icon message="尚未形成自动结果" description="系统正在核实或等待当前批次完成。关闭详情后可查看进度。" />
      <template v-if="result && supportedReason">
        <a-alert :type="outdated ? 'warning' : result.status === 'supported' ? 'success' : result.status === 'problem' || result.status === 'failed' ? 'error' : 'warning'" show-icon :message="pinned ? '正在查看历史核查；人工核实仍以当前证据为准' : outdated ? '源版本已改变，此结果仅供历史参考' : result.summary" />
        <a-alert v-if="isNormal && !outdated && !pinned && result.status === 'supported'" type="success" show-icon message="自动通过（已闭环）" description="所有出票明细均在通用配置止损阈值内，无须再人工确认，可按需抽查。" />
        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="平台">{{ result.platform || '证据缺失' }}</a-descriptions-item>
          <a-descriptions-item label="止损值来源">{{ usesConfiguration ? '原取证配置（逐票查看历史证明）' : '历史日志结果，需更新并核实' }}</a-descriptions-item>
          <a-descriptions-item :label="result.sourceMode === 'prepared_etl' ? '清洗核实时间' : '核实时间'">{{ formatDateTimeDisplay(result.checkedAt) }}</a-descriptions-item>
          <a-descriptions-item label="规则版本">{{ result.ruleVersion }}</a-descriptions-item>
          <a-descriptions-item v-if="!isChild && !isBet && !isNormal" label="核实依据" :span="2">非去哪儿平台优先判为选因有问题；去哪儿且有正佣金时，出票利润＋销售佣金 ≥ －单票止损值；金额为CNY。超过4段按4段配置＋超出段数×25元。</a-descriptions-item>
          <a-descriptions-item v-if="isBet || isNormal" label="核实依据" :span="2">逐票出票利润 ≥ －出票时单票止损值（含等号），不加佣金或预期收益；任一票突破则整单有问题。原始利润为CNY，不合并关联单平均利润。</a-descriptions-item>
          <a-descriptions-item v-if="isChild" label="核实依据" :span="2">必须有儿童或婴儿；携程同OTA订单与关联单汇总出票利润÷总票数，不加佣金；平均利润须满足当前单逐票止损阈值；平均值展示四位小数，判定不按展示值舍入。</a-descriptions-item>
          <template v-if="isChild && result.aggregate">
            <a-descriptions-item label="核算范围">{{ result.aggregate.orderCount }} 单 · {{ result.aggregate.ticketCount }} 票</a-descriptions-item>
            <a-descriptions-item label="儿童／婴儿票数">{{ result.aggregate.childTickets ?? '未核实' }} ／ {{ result.aggregate.infantTickets ?? '未核实' }}</a-descriptions-item>
            <a-descriptions-item label="总出票利润">{{ result.aggregate.totalProfit ?? '证据不足' }} 元</a-descriptions-item>
            <a-descriptions-item label="平均单票利润">{{ result.aggregate.averageProfitDisplay ?? result.aggregate.averageProfit ?? '证据不足' }} 元</a-descriptions-item>
            <a-descriptions-item label="范围内订单" :span="2">{{ result.aggregate.orderCount }} 单（按OTA与关联关系核算）</a-descriptions-item>
          </template>
        </a-descriptions>
        <a-table :data-source="result.tickets" :columns="columns" row-key="id" :pagination="false" :scroll="{ x: 1550 }" size="small">
          <template #bodyCell="{ column, record }">
            <a-tag v-if="column.key === 'status'" :color="record.status === 'supported' ? 'green' : record.status === 'problem' ? 'red' : 'orange'">{{ labels[record.status] || record.status }}</a-tag>
            <template v-else-if="column.key === 'threshold'">{{ record.stopLoss != null ? `${record.stopLoss} 元` : '证据不足' }}</template>
            <template v-else-if="column.key === 'latestThreshold'">{{ latestTicket(record.id)?.latestStopLoss != null ? `${latestTicket(record.id)?.latestStopLoss} 元${previousObservationOnly ? '（上次成功）' : ''}` : latestTicket(record.id)?.lastSuccessful?.latestStopLoss != null ? `${latestTicket(record.id)?.lastSuccessful?.latestStopLoss} 元（上次成功，本次未取得）` : latestReadError ? '读取失败' : latestLoading ? '读取中' : '—' }}</template>
            <template v-else-if="column.key === 'observationStatus'">{{ latestReadError ? '读取失败' : latestLoading ? '读取中' : latestConfigStatus(latestTicket(record.id)?.status) }}<small v-if="previousObservationOnly" class="muted"> · 上次成功，本次未更新</small><small v-if="latestConfig?.publishedRun?.sourceChangedAfterSnapshot" class="muted"> · 后续配置待刷新</small></template>
            <template v-else-if="column.key === 'configuration'">
              <template v-if="record.configuration?.ruleId">规则 {{ record.configuration.ruleId }} · v{{ record.configuration.configurationVersion }}<br />{{ record.segmentCount }} 段 · 阈值 {{ record.stopLoss }} 元</template>
              <template v-else>未可靠匹配<span v-if="record.configuration?.issueWayLabel"> · {{ record.configuration.issueWayLabel }}（{{ record.configuration.issueWay || '缺失' }}）</span><p v-if="record.configuration?.diagnostics?.length" class="muted">历史配置或匹配证据不足，暂不能确定采用规则；请查看待补证据与本票计算原因。</p></template>
              <RiskConfigurationBasis :ticket="record as AutoRiskResult['tickets'][number]" :observation="latestTicket(record.id)" :observation-run="latestConfig?.publishedRun" :previous-only="previousObservationOnly" />
            </template>
          </template>
        </a-table>
        <a-alert v-if="result.missing?.length" type="warning" show-icon :message="`待补证据：${result.missing.join('；')}`" />
        <p class="muted">{{ isBet || isNormal ? '来源：order_info_issue.issue_profit（CNY）与出票时通用配置单票止损值；逐票比较，不加佣金或预期收益。' : isChild ? '来源：范围内各独立订单出票利润（CNY）与票数、乘机人年龄类型；不加佣金，不去重独立出票。阈值沿用当前单出票时配置。' : usesConfiguration ? '来源：出票明细的利润、销售佣金和单票航段关联；止损值取出票时的通用配置。保留配置版本、快照哈希及必要的配置变更引用，不从订单止损日志取值。' : '此为旧版日志核实结果，仅供历史参考；请先完成所选日期清洗，再在列表查询最新结果。' }}</p>
      </template>
      <RiskReviewPanel v-if="issueDate" :order-id="orderId" :issue-date="issueDate" :normal-business="NORMAL_REASON_CODES.includes(reason)" @changed="emit('changed')" @busy-change="reviewBusy = $event" />
    </div>
  </a-spin>
</template>
<script setup lang="ts">
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Alert as AAlert, Descriptions as ADescriptions, DescriptionsItem as ADescriptionsItem, Spin as ASpin, Table as ATable, Tag as ATag } from 'ant-design-vue'
import { riskAutomatic, NORMAL_REASON_CODES, type AutoRiskResult } from '@/api/riskVerification'
import RiskReviewPanel from '@/components/RiskReviewPanel.vue'
import RiskConfigurationBasis from '@/components/RiskConfigurationBasis.vue'
import RiskConfigEvidencePanel from '@/components/RiskConfigEvidencePanel.vue'
import { readLatestConfig, latestConfigStatus, type LatestConfigResponse } from '@/api/riskLatestConfig'
const props = defineProps<{ orderId: string; reason: string; sourceUpdatedAt: string | null; issueDate?: string }>()
const emit = defineEmits<{ changed: []; 'busy-change': [boolean] }>()
const result = ref<AutoRiskResult | null>(null)
const currentResult = ref<AutoRiskResult | null>(null)
const evidenceBusy = ref(false), pinned = ref(false)
const latestConfig = ref<LatestConfigResponse | null>(null), latestReadError = ref(''), latestLoading = ref(false)
const latestTicket = (id: unknown) => latestConfig.value?.observation?.tickets.find(ticket => ticket.ticketId === String(id))
const previousObservationOnly = computed(() => Boolean(latestConfig.value?.publishedRun && latestConfig.value.latestAttempt && latestConfig.value.latestAttempt.runId !== latestConfig.value.publishedRun.runId))
let latestEpoch = 0
watch(() => [result.value?.id, result.value?.historyRunId, props.orderId, props.issueDate], async () => {
  const epoch = ++latestEpoch; latestConfig.value = null; latestReadError.value = ''; latestLoading.value = false
  if (!result.value || !props.issueDate) return
  latestLoading.value = true
  try { const data = await readLatestConfig(props.orderId, props.issueDate, result.value.id, result.value.historyRunId); if (epoch === latestEpoch) latestConfig.value = data }
  catch (failure) { if (epoch === latestEpoch) latestReadError.value = failure instanceof Error ? failure.message : '请联系管理员核对每日观察任务' }
  finally { if (epoch === latestEpoch) latestLoading.value = false }
})
onBeforeUnmount(() => { latestEpoch++ })
function showPinned(original: AutoRiskResult | null) { pinned.value = !!original; result.value = original ? { ...original, isCurrent: original.id === currentResult.value?.id } : currentResult.value }
const busy = ref(false)
const reviewBusy = ref(false)
const error = ref('')
const labels: Record<string, string> = { supported: '自动通过', problem: '疑似问题', insufficient: '证据不足', failed: '执行失败', rule_pending: '规则未接入' }
const effectiveReason = computed(() => (pinned.value ? result.value?.reasonCode : props.reason) || result.value?.reasonCode || '')
const isBet = computed(() => ['RLA068', 'RLA047', 'RLA50', 'RLA046', 'RLA045', 'RLA069', 'RLA070', 'RLA067'].includes(effectiveReason.value))
const isNormal = computed(() => NORMAL_REASON_CODES.includes(effectiveReason.value))
const supportedReason = computed(() => isNormal.value || isBet.value || ['RLA013', 'RLA040'].includes(effectiveReason.value))
const isChild = computed(() => effectiveReason.value === 'RLA040')
const columns = computed(() => [{ title: '出票明细ID', dataIndex: 'id', width: 150 }, { title: '出票利润', dataIndex: 'profit', width: 100 }, ...(!isBet.value && !isNormal.value ? [{ title: '销售佣金', dataIndex: 'commission', width: 100 }] : []), { title: isBet.value || isNormal.value ? '用于比较的原始利润' : isChild.value ? '平均单票利润' : '调整后利润', dataIndex: 'adjustedProfit', width: 130 }, { title: '票段数', dataIndex: 'segmentCount', width: 80 }, { title: '原单票止损值', key: 'threshold', width: 110 }, { title: '最新单票止损值', key: 'latestThreshold', width: 140 }, { title: '观察状态', key: 'observationStatus', width: 150 }, { title: '原采用配置', key: 'configuration', width: 300 }, { title: '结果', key: 'status', width: 110 }, { title: '计算及原因', dataIndex: 'explanation', width: 300 }])
const usesConfiguration = computed(() => result.value?.ruleVersion?.startsWith('qunar-commission-loss-config-v'))
const normalize = (value: string | null) => value?.replace(' ', 'T') || null
const outdated = computed(() => Boolean(result.value && (result.value.isCurrent === false || (props.sourceUpdatedAt !== null && normalize(result.value.sourceUpdatedAt) !== normalize(props.sourceUpdatedAt)) || (!!props.reason && result.value.reasonCode !== props.reason))))
const hasUnsavedDrafts = computed(() => false)
defineExpose({ hasUnsavedDrafts, reload: load })
watch([busy, reviewBusy, evidenceBusy], ([own, review, evidence]) => emit('busy-change', own || review || evidence))
onMounted(load)
async function load() {
  busy.value = true; error.value = ''; if (!pinned.value) result.value = null
  try { currentResult.value = await riskAutomatic.result(props.orderId, props.issueDate); if (!pinned.value) result.value = currentResult.value; else if (result.value) result.value = { ...result.value, isCurrent: result.value.id === currentResult.value?.id } }
  catch (failure) { error.value = failure instanceof Error ? failure.message : '核实结果读取失败' }
  finally { busy.value = false }
}
</script>
<style scoped>
.auto-detail, section { display: grid; gap: 16px; }
.muted { color: #69768a; font-size: 13px; }
h3 { margin-bottom: 0; }
</style>
