<template>
  <a-spin :spinning="busy">
    <div class="auto-detail">
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <RiskConfigEvidencePanel v-if="issueDate" :order-id="orderId" :issue-date="issueDate" :current-result="currentResult" @pinned="showPinned" @observed="latestObservation = $event" @busy-change="evidenceBusy = $event" />
      <details><summary>历史问题标签</summary><RiskProblemTags ref="tagPanel" :order-id="orderId" @busy-change="tagBusy = $event" /></details>
      <a-alert v-if="!supportedReason" type="info" show-icon message="该类型规则尚未接入" description="后续为此类型补充专属证据和规则，不套用佣金亏损公式。" />
      <a-alert v-else-if="!result" type="info" show-icon message="尚未形成自动结果" description="系统正在核实或等待当前批次完成。关闭详情后可查看进度。" />
      <template v-if="result && supportedReason">
        <a-alert :type="outdated ? 'warning' : result.status === 'supported' ? 'success' : result.status === 'problem' || result.status === 'failed' ? 'error' : 'warning'" show-icon :message="outdated ? '源版本已改变，此结果仅供历史参考' : result.summary" />
        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="平台">{{ result.platform || '证据缺失' }}</a-descriptions-item>
          <a-descriptions-item label="止损值来源">{{ usesConfiguration ? '原取证配置（逐票查看历史证明）' : '历史日志结果，需更新并核实' }}</a-descriptions-item>
          <a-descriptions-item :label="result.sourceMode === 'prepared_etl' ? '清洗核实时间' : '核实时间'">{{ formatDateTimeDisplay(result.checkedAt) }}</a-descriptions-item>
          <a-descriptions-item label="规则版本">{{ result.ruleVersion }}</a-descriptions-item>
          <a-descriptions-item v-if="!isChild && !isBet" label="核实依据" :span="2">非去哪儿平台优先判为选因有问题；去哪儿且有正佣金时，出票利润＋销售佣金 ≥ －单票止损值；金额为CNY。超过4段按4段配置＋超出段数×25元。</a-descriptions-item>
          <a-descriptions-item v-if="isBet" label="核实依据" :span="2">逐票出票利润 ≥ －出票时单票止损值（含等号），不加佣金或预期收益；任一票突破则整单有问题。原始利润为CNY，不合并关联单平均利润。</a-descriptions-item>
          <a-descriptions-item v-if="isChild" label="核实依据" :span="2">必须有儿童或婴儿；携程同OTA订单与关联单汇总出票利润÷总票数，不加佣金；平均利润须满足当前单逐票止损阈值；平均值展示四位小数，判定不按展示值舍入。</a-descriptions-item>
          <template v-if="isChild && result.aggregate">
            <a-descriptions-item label="核算范围">{{ result.aggregate.orderCount }} 单 · {{ result.aggregate.ticketCount }} 票</a-descriptions-item>
            <a-descriptions-item label="儿童／婴儿票数">{{ result.aggregate.childTickets ?? '未核实' }} ／ {{ result.aggregate.infantTickets ?? '未核实' }}</a-descriptions-item>
            <a-descriptions-item label="总出票利润">{{ result.aggregate.totalProfit ?? '证据不足' }} 元</a-descriptions-item>
            <a-descriptions-item label="平均单票利润">{{ result.aggregate.averageProfitDisplay ?? result.aggregate.averageProfit ?? '证据不足' }} 元</a-descriptions-item>
            <a-descriptions-item label="范围内订单" :span="2">{{ result.aggregate.orderCount }} 单（按OTA与关联关系核算）</a-descriptions-item>
          </template>
        </a-descriptions>
        <a-table :data-source="result.tickets" :columns="columns" row-key="id" :pagination="false" :scroll="{ x: 1220 }" size="small">
          <template #bodyCell="{ column, record }">
            <a-tag v-if="column.key === 'status'" :color="record.status === 'supported' ? 'green' : record.status === 'problem' ? 'red' : 'orange'">{{ labels[record.status] || record.status }}</a-tag>
            <template v-else-if="column.key === 'threshold'">{{ record.stopLoss != null ? `${record.stopLoss} 元` : '证据不足' }}</template>
            <template v-else-if="column.key === 'latestStopLoss'"><template v-if="latestTicket(record.id)">{{ latestTicket(record.id)?.latestStopLoss != null ? `${latestTicket(record.id)?.latestStopLoss} 元` : '未取得' }}<small v-if="latestTicket(record.id)?.differentFromOriginal" class="muted">与原单票止损不同（仅提醒）</small><small class="muted">{{ latestTicket(record.id)?.valueChanged ? '较上次值变化' : latestTicket(record.id)?.configurationChanged ? '配置信息变化' : '' }}</small><small class="muted">观察 {{ formatDateTimeDisplay(latestTicket(record.id)?.observedAt) }}</small><small v-if="latestTicket(record.id)?.sourceCurrentlyEffective !== true" class="muted">当前规则非有效启用或有效期无法确认</small><p v-if="latestTicket(record.id)?.latestStopLoss == null">{{ latestTicket(record.id)?.reason }}</p></template><span v-else>尚未观察</span></template>
            <template v-else-if="column.key === 'configuration'">
              <template v-if="record.configuration?.ruleId">规则 {{ record.configuration.ruleId }} · v{{ record.configuration.configurationVersion }}<br />{{ record.segmentCount }} 段 · 阈值 {{ record.stopLoss }} 元<RiskConfigurationBasis :ticket="record as AutoRiskResult['tickets'][number]" /></template>
              <template v-else>未可靠匹配<span v-if="record.configuration?.issueWayLabel"> · {{ record.configuration.issueWayLabel }}（{{ record.configuration.issueWay || '缺失' }}）</span><p v-if="record.configuration?.diagnostics?.length" class="muted">历史配置或匹配证据不足，暂不能确定采用规则；请查看待补证据与本票计算原因。</p></template>
            </template>
          </template>
        </a-table>
        <a-alert v-if="result.missing?.length" type="warning" show-icon :message="`待补证据：${result.missing.join('；')}`" />
        <p class="muted">{{ isBet ? '来源：order_info_issue.issue_profit（CNY）与出票时通用配置单票止损值；逐票比较，不加佣金或预期收益。' : isChild ? '来源：范围内各独立订单出票利润（CNY）与票数、乘机人年龄类型；不加佣金，不去重独立出票。阈值沿用当前单出票时配置。' : usesConfiguration ? '来源：出票明细的利润、销售佣金和单票航段关联；止损值取出票时的通用配置。保留配置版本、快照哈希及必要的配置变更引用，不从订单止损日志取值。' : '此为旧版日志核实结果，仅供历史参考；请先完成所选日期清洗，再在列表查询最新结果。' }}</p>
      </template>
      <RiskReviewPanel v-if="issueDate" :order-id="orderId" :issue-date="issueDate" @changed="emit('changed')" @busy-change="reviewBusy = $event" />
    </div>
  </a-spin>
</template>
<script setup lang="ts">
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'

import { computed, onMounted, ref, watch } from 'vue'
import { Alert as AAlert, Descriptions as ADescriptions, DescriptionsItem as ADescriptionsItem, Spin as ASpin, Table as ATable, Tag as ATag } from 'ant-design-vue'
import { riskAutomatic, type AutoRiskResult } from '@/api/riskVerification'
import RiskProblemTags from '@/components/RiskProblemTags.vue'
import RiskReviewPanel from '@/components/RiskReviewPanel.vue'
import RiskConfigurationBasis from '@/components/RiskConfigurationBasis.vue'
import RiskConfigEvidencePanel from '@/components/RiskConfigEvidencePanel.vue'
import { type ConfigObservation } from '@/api/riskConfigEvidence'
const props = defineProps<{ orderId: string; reason: string; sourceUpdatedAt: string | null; issueDate?: string }>()
const emit = defineEmits<{ changed: []; 'busy-change': [boolean] }>()
const result = ref<AutoRiskResult | null>(null)
const currentResult = ref<AutoRiskResult | null>(null)
const latestObservation = ref<ConfigObservation | null>(null), evidenceBusy = ref(false), pinned = ref(false)
function showPinned(original: AutoRiskResult | null) { pinned.value = !!original; result.value = original ? { ...original, isCurrent: original.id === currentResult.value?.id } : currentResult.value }
function latestTicket(id: string) { return latestObservation.value?.tickets.find(item => String(item.ticketId) === String(id)) }
const busy = ref(false)
const tagBusy = ref(false)
const reviewBusy = ref(false)
const tagPanel = ref<InstanceType<typeof RiskProblemTags>>()
const error = ref('')
const labels: Record<string, string> = { supported: '自动通过', problem: '疑似问题', insufficient: '证据不足', failed: '执行失败', rule_pending: '规则未接入' }
const effectiveReason = computed(() => props.reason || result.value?.reasonCode || '')
const isBet = computed(() => ['RLA068', 'RLA047', 'RLA50', 'RLA046', 'RLA045', 'RLA069', 'RLA070', 'RLA067'].includes(effectiveReason.value))
const supportedReason = computed(() => isBet.value || ['RLA013', 'RLA040'].includes(effectiveReason.value))
const isChild = computed(() => effectiveReason.value === 'RLA040')
const columns = computed(() => [{ title: '出票明细ID', dataIndex: 'id', width: 150 }, { title: '出票利润', dataIndex: 'profit', width: 100 }, ...(!isBet.value ? [{ title: '销售佣金', dataIndex: 'commission', width: 100 }] : []), { title: isBet.value ? '用于比较的原始利润' : isChild.value ? '平均单票利润' : '调整后利润', dataIndex: 'adjustedProfit', width: 130 }, { title: '票段数', dataIndex: 'segmentCount', width: 80 }, { title: pinned.value ? '原单票止损值' : '单票止损值', key: 'threshold', width: 110 }, { title: '最新单票止损值（仅提醒）', key: 'latestStopLoss', width: 200 }, { title: '原采用配置', key: 'configuration', width: 300 }, { title: '结果', key: 'status', width: 110 }, { title: '计算及原因', dataIndex: 'explanation', width: 300 }])
const usesConfiguration = computed(() => result.value?.ruleVersion?.startsWith('qunar-commission-loss-config-v'))
const normalize = (value: string | null) => value?.replace(' ', 'T') || null
const outdated = computed(() => Boolean(result.value && (result.value.isCurrent === false || (props.sourceUpdatedAt !== null && normalize(result.value.sourceUpdatedAt) !== normalize(props.sourceUpdatedAt)) || (!!props.reason && result.value.reasonCode !== props.reason))))
const hasUnsavedDrafts = computed(() => Boolean(tagPanel.value?.hasUnsavedDrafts))
defineExpose({ hasUnsavedDrafts, reload: load })
watch([busy, tagBusy, reviewBusy, evidenceBusy], ([own, tags, review, evidence]) => emit('busy-change', own || tags || review || evidence))
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
