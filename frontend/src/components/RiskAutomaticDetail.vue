<template>
  <a-spin :spinning="busy">
    <div class="auto-detail">
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <RiskProblemTags ref="tagPanel" :order-id="orderId" @busy-change="tagBusy = $event" />
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
              <template v-if="record.configuration?.ruleId">规则 {{ record.configuration.ruleId }} · v{{ record.configuration.configurationVersion }}<br />权重：{{ record.configuration.weight ?? "旧结果未记录" }}<br />出票时点：{{ formatDateTimeDisplay(record.configuration.asOf) }}<br />{{ record.configuration.jsonPath }}：{{ record.configuration.baseAmount }} 元；超出 {{ record.configuration.extraSegments }} 段×{{ record.configuration.extraPerSegment }} 元</template>
              <template v-else>
                未可靠匹配<span v-if="record.configuration?.issueWayLabel"> · {{ record.configuration.issueWayLabel }}（{{ record.configuration.issueWay || '缺失' }}）</span>
                <details v-if="record.configuration?.diagnostics?.length">
                  <summary>查看 {{ record.configuration.diagnostics.length }} 条未知候选（已阻断）</summary>
                  <p v-for="item in record.configuration.diagnostics" :key="`${item.ruleId}-${item.stage}`">规则 {{ item.ruleId }} · {{ item.stage === 'history' ? '历史还原' : '条件匹配' }}：{{ item.reason }}</p>
                </details>
              </template>
              <details v-if="record.configuration?.candidateTrace?.length" class="match-trace">
                <summary>查看订单条件与 {{ record.configuration.candidateTrace.length }} 条候选轨迹</summary>
                <p>排序：{{ record.configuration.sortBasis || '权重、更新时间、规则ID降序；未知候选仍阻断' }}</p>
                <dl class="fact-grid"><div v-for="(value, key) in record.configuration.matchingFacts" :key="key"><dt>{{ factLabels[key] || key }}</dt><dd>{{ value }}</dd></div></dl>
                <p v-for="(problem, key) in record.configuration.matchingFactProblems" :key="key">{{ factLabels[key] || key }}：{{ problem }}</p>
                <div v-for="item in record.configuration.candidateTrace" :key="item.ruleId" class="trace-item">
                  <strong>规则 {{ item.ruleId }} · {{ traceLabels[item.outcome] || item.outcome }}<span v-if="item.weight != null"> · 权重 {{ item.weight }}</span></strong>
                  <p v-if="item.reason">{{ item.reason }}</p>
                  <p v-if="item.updateTime">配置更新时间：{{ formatDateTimeDisplay(item.updateTime) }}</p>
                  <p v-for="condition in item.conditions || []" :key="condition.field">{{ condition.label }}：配置 {{ condition.value }} / 订单 {{ condition.actual ?? '缺少可靠事实' }} · {{ traceLabels[condition.outcome || ''] || condition.outcome }}</p>
                </div>
              </details>
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
const ATextarea = AInput.TextArea
const props = defineProps<{ orderId: string; reason: string; sourceUpdatedAt: string | null; issueDate?: string }>()
const emit = defineEmits<{ changed: []; 'busy-change': [boolean] }>()
const result = ref<AutoRiskResult | null>(null)
const busy = ref(false)
const tagBusy = ref(false)
const tagPanel = ref<InstanceType<typeof RiskProblemTags>>()
const error = ref('')
const saved = ref('')
const sampleOutcome = ref('confirmed')
const sampleReason = ref('')
const factLabels: Record<string, string> = { ota_code: '平台', ota_site_code: '站点', product_type: '产品类型', manual_flag: '人工标记', issue_supplier_code: '出票供应商', issue_gds: '出票GDS', issue_pcc: '出票PCC', airline: '航司', issue_way: '出票方式', cabin: '子舱位', cabin_grade: '舱等', flight_number: '航班号', origin: '主航段出发地', destination: '主航段目的地' }
const traceLabels: Record<string, string> = { rank_only: '仅参与权重，不筛选该类规则', selected: '最终选中', matched: '条件符合（尚未最终选中）', lower_priority: '条件符合，优先级较低', excluded: '不适用', unknown: '证据不足' }
const labels: Record<string, string> = { supported: '核实通过', problem: '有问题', insufficient: '证据不足', failed: '执行失败', rule_pending: '规则未接入' }
const isBet = computed(() => ['RLA068', 'RLA047', 'RLA50', 'RLA046', 'RLA045', 'RLA069', 'RLA070', 'RLA067'].includes(props.reason))
const supportedReason = computed(() => isBet.value || ['RLA013', 'RLA040'].includes(props.reason))
const isChild = computed(() => props.reason === 'RLA040')
const columns = computed(() => [{ title: '出票明细ID', dataIndex: 'id', width: 150 }, { title: '出票利润', dataIndex: 'profit', width: 100 }, ...(!isBet.value ? [{ title: '销售佣金', dataIndex: 'commission', width: 100 }] : []), { title: isBet.value ? '用于比较的原始利润' : isChild.value ? '平均单票利润' : '调整后利润', dataIndex: 'adjustedProfit', width: 130 }, { title: '票段数', dataIndex: 'segmentCount', width: 80 }, { title: '单票止损值', key: 'threshold', width: 110 }, { title: '出票时配置', key: 'configuration', width: 300 }, { title: '结果', key: 'status', width: 110 }, { title: '计算及原因', dataIndex: 'explanation', width: 300 }])
const usesConfiguration = computed(() => result.value?.ruleVersion?.startsWith('qunar-commission-loss-config-v'))
const normalize = (value: string | null) => value?.replace(' ', 'T') || null
const outdated = computed(() => Boolean(result.value && (result.value.isCurrent === false || normalize(result.value.sourceUpdatedAt) !== normalize(props.sourceUpdatedAt) || result.value.reasonCode !== props.reason)))
const hasUnsavedDrafts = computed(() => Boolean(sampleReason.value.trim() || tagPanel.value?.hasUnsavedDrafts))
defineExpose({ hasUnsavedDrafts, reload: load })
watch([busy, tagBusy], ([own, tags]) => emit('busy-change', own || tags))
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
.match-trace { margin-top: 10px; overflow-wrap: anywhere; }
.fact-grid { display: grid; gap: 6px; margin: 12px 0; }
.fact-grid dd { margin: 0; }
.fact-grid dt { color: #69768a; }
.trace-item { border-top: 1px solid #e5eaf0; padding: 10px 0; }
.trace-item p { margin: 6px 0; }
.muted { color: #69768a; font-size: 13px; }
h3 { margin-bottom: 0; }
</style>
