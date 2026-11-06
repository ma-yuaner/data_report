<template>
  <a-spin :spinning="busy">
    <div class="auto-detail">
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <RiskReviewPanel v-if="issueDate" :order-id="orderId" :issue-date="issueDate" @changed="emit('changed')" @busy-change="reviewBusy = $event" />
      <details><summary>历史问题标签</summary><RiskProblemTags ref="tagPanel" :order-id="orderId" @busy-change="tagBusy = $event" /></details>
      <a-alert v-if="!supportedReason" type="info" show-icon message="该类型规则尚未接入" description="后续为此类型补充专属证据和规则，不套用佣金亏损公式。" />
      <a-alert v-else-if="!result" type="info" show-icon message="尚未形成自动结果" description="系统正在核实或等待当前批次完成。关闭详情后可查看进度。" />
      <template v-if="result && supportedReason">
        <a-alert :type="outdated ? 'warning' : result.status === 'supported' ? 'success' : result.status === 'problem' || result.status === 'failed' ? 'error' : 'warning'" show-icon :message="outdated ? '源版本已改变，此结果仅供历史参考' : result.summary" />
        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="平台">{{ result.platform || '证据缺失' }}</a-descriptions-item>
          <a-descriptions-item label="止损值来源">{{ usesConfiguration ? '出票时通用配置（逐票见下表）' : '历史日志结果，需更新并核实' }}</a-descriptions-item>
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
            <a-descriptions-item label="范围内订单" :span="2">{{ result.aggregate.scope.map(item => `${item.orderId}（${item.ticketCount}票）`).join('、') }}</a-descriptions-item>
          </template>
        </a-descriptions>
        <a-table :data-source="result.tickets" :columns="columns" row-key="id" :pagination="false" :scroll="{ x: 1220 }" size="small">
          <template #bodyCell="{ column, record }">
            <a-tag v-if="column.key === 'status'" :color="record.status === 'supported' ? 'green' : record.status === 'problem' ? 'red' : 'orange'">{{ labels[record.status] || record.status }}</a-tag>
            <template v-else-if="column.key === 'threshold'">{{ record.stopLoss != null ? `${record.stopLoss} 元` : '证据不足' }}</template>
            <template v-else-if="column.key === 'configuration'">
              <template v-if="record.configuration?.ruleId">规则 {{ record.configuration.ruleId }} · v{{ record.configuration.configurationVersion }}<br />{{ record.segmentCount }} 段 · 阈值 {{ record.stopLoss }} 元<RiskConfigurationBasis :ticket="record as AutoRiskResult['tickets'][number]" /></template>
              <template v-else>未可靠匹配<span v-if="record.configuration?.issueWayLabel"> · {{ record.configuration.issueWayLabel }}（{{ record.configuration.issueWay || '缺失' }}）</span><p v-if="record.configuration?.diagnostics?.length" class="muted">历史配置或匹配证据不足，暂不能确定采用规则；请查看待补证据与本票计算原因。</p></template>
            </template>
          </template>
        </a-table>
        <a-alert v-if="result.missing?.length" type="warning" show-icon :message="`待补证据：${result.missing.join('；')}`" />
        <p class="muted">{{ isBet ? '来源：order_info_issue.issue_profit（CNY）与出票时通用配置单票止损值；逐票比较，不加佣金或预期收益。' : isChild ? '来源：范围内各独立订单出票利润（CNY）与票数、乘机人年龄类型；不加佣金，不去重独立出票。阈值沿用当前单出票时配置。' : usesConfiguration ? '来源：出票明细的利润、销售佣金和单票航段关联；止损值取出票时的通用配置。保留配置版本、快照哈希及必要的配置变更引用，不从订单止损日志取值。' : '此为旧版日志核实结果，仅供历史参考；请先完成所选日期清洗，再在列表查询最新结果。' }}</p>
        <section v-if="!outdated && canReview">
          <h3>人工抽查（可选）</h3>
          <a-radio-group v-model:value="sampleOutcome"><a-radio value="confirmed">确认无误</a-radio><a-radio value="disputed">发现问题</a-radio></a-radio-group>
          <a-textarea v-model:value="sampleReason" :rows="3" :maxlength="2000" placeholder="抽查说明，例如证据与原单一致，或发现的具体差异" />
          <a-button type="primary" :loading="busy" :disabled="!sampleReason.trim()" @click="saveSample">保存抽查</a-button>
          <p>抽查独立留痕，不覆盖自动计算结果。{{ saved }}</p>
        </section>
        <section v-if="result.samples?.length">
          <h3>已保存的人工抽查</h3>
          <p v-for="item in result.samples" :key="item.id">{{ formatDateTimeDisplay(item.at) }} · {{ item.outcome === 'confirmed' ? '确认无误' : '发现问题' }} · {{ item.reason }}</p>
        </section>
      </template>
    </div>
  </a-spin>
</template>
<script setup lang="ts">
import { useRiskPermissions } from '@/composables/useRiskPermissions'
const { canReview } = useRiskPermissions()
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'

import { computed, onMounted, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, Descriptions as ADescriptions, DescriptionsItem as ADescriptionsItem, Input as AInput, Radio as ARadio, RadioGroup as ARadioGroup, Spin as ASpin, Table as ATable, Tag as ATag } from 'ant-design-vue'
import { riskAutomatic, type AutoRiskResult } from '@/api/riskVerification'
import RiskProblemTags from '@/components/RiskProblemTags.vue'
import RiskReviewPanel from '@/components/RiskReviewPanel.vue'
import RiskConfigurationBasis from '@/components/RiskConfigurationBasis.vue'
const ATextarea = AInput.TextArea
const props = defineProps<{ orderId: string; reason: string; sourceUpdatedAt: string | null; issueDate?: string }>()
const emit = defineEmits<{ changed: []; 'busy-change': [boolean] }>()
const result = ref<AutoRiskResult | null>(null)
const busy = ref(false)
const tagBusy = ref(false)
const reviewBusy = ref(false)
const tagPanel = ref<InstanceType<typeof RiskProblemTags>>()
const error = ref('')
const saved = ref('')
const sampleOutcome = ref('confirmed')
const sampleReason = ref('')
const labels: Record<string, string> = { supported: '自动通过', problem: '疑似问题', insufficient: '证据不足', failed: '执行失败', rule_pending: '规则未接入' }
const effectiveReason = computed(() => props.reason || result.value?.reasonCode || '')
const isBet = computed(() => ['RLA068', 'RLA047', 'RLA50', 'RLA046', 'RLA045', 'RLA069', 'RLA070', 'RLA067'].includes(effectiveReason.value))
const supportedReason = computed(() => isBet.value || ['RLA013', 'RLA040'].includes(effectiveReason.value))
const isChild = computed(() => effectiveReason.value === 'RLA040')
const columns = computed(() => [{ title: '出票明细ID', dataIndex: 'id', width: 150 }, { title: '出票利润', dataIndex: 'profit', width: 100 }, ...(!isBet.value ? [{ title: '销售佣金', dataIndex: 'commission', width: 100 }] : []), { title: isBet.value ? '用于比较的原始利润' : isChild.value ? '平均单票利润' : '调整后利润', dataIndex: 'adjustedProfit', width: 130 }, { title: '票段数', dataIndex: 'segmentCount', width: 80 }, { title: '单票止损值', key: 'threshold', width: 110 }, { title: '出票时配置', key: 'configuration', width: 300 }, { title: '结果', key: 'status', width: 110 }, { title: '计算及原因', dataIndex: 'explanation', width: 300 }])
const usesConfiguration = computed(() => result.value?.ruleVersion?.startsWith('qunar-commission-loss-config-v'))
const normalize = (value: string | null) => value?.replace(' ', 'T') || null
const outdated = computed(() => Boolean(result.value && (result.value.isCurrent === false || (props.sourceUpdatedAt !== null && normalize(result.value.sourceUpdatedAt) !== normalize(props.sourceUpdatedAt)) || (!!props.reason && result.value.reasonCode !== props.reason))))
const hasUnsavedDrafts = computed(() => Boolean(sampleReason.value.trim() || tagPanel.value?.hasUnsavedDrafts))
defineExpose({ hasUnsavedDrafts, reload: load })
watch([busy, tagBusy, reviewBusy], ([own, tags, review]) => emit('busy-change', own || tags || review))
onMounted(load)
async function load() {
  busy.value = true; error.value = ''; result.value = null
  try { result.value = await riskAutomatic.result(props.orderId, props.issueDate) }
  catch (failure) { error.value = failure instanceof Error ? failure.message : '核实结果读取失败' }
  finally { busy.value = false }
}
async function saveSample() {
  if (busy.value || !result.value || outdated.value) return
  busy.value = true; error.value = ''
  try {
    await riskAutomatic.sample(props.orderId, result.value.id, sampleOutcome.value, sampleReason.value, props.issueDate)
    sampleReason.value = ''; saved.value = '已保存'; emit('changed'); result.value = await riskAutomatic.result(props.orderId, props.issueDate)
  } catch (failure) { error.value = failure instanceof Error ? failure.message : '抽查保存失败' }
  finally { busy.value = false }
}
</script>
<style scoped>
.auto-detail, section { display: grid; gap: 16px; }
.muted { color: #69768a; font-size: 13px; }
h3 { margin-bottom: 0; }
</style>
