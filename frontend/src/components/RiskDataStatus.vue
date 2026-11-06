<template>
  <section class="data-status" aria-label="数据状态与清洗报告">
    <a-alert v-if="warnings.length" type="warning" show-icon message="当前数据范围需要关注" :description="warnings.join('；')" />
    <div class="status-summary">
      <div class="status-facts"><span>已保存的核实结果</span><span>最近同步 {{ formatDateTimeDisplay(freshness.newestSyncedAt) }}</span><span v-if="freshness.preparation">已准备 {{ freshness.preparation.readyDays.length }} 天</span></div>
      <a-button v-if="insufficient > 0" type="link" class="insufficient-link" @click="$emit('inspect-insufficient')">证据不足 {{ insufficient }} 单 · 查看订单</a-button>
    </div>
    <details class="status-details">
      <summary>清洗报告<span v-if="reports.length">（{{ reports.length }} 天<span v-if="insufficientDays">，{{ insufficientDays }} 天存在证据不足</span>）</span></summary>
      <div class="details-content">
        <p class="status-note">以下为各日清洗诊断；每日数量不相加作为跨日去重订单数。证据不足不表示执行失败，清洗完成也不表示业务核实通过。</p>
        <a-table :data-source="reports" :columns="reportColumns" row-key="day" size="small" :scroll="{ x: 700 }" :pagination="reports.length > 7 ? { pageSize: 7, showSizeChanger: false } : false" :locale="{ emptyText: '所选范围尚无清洗诊断报告，不能据此解释为没有问题' }">
          <template #bodyCell="{ column, record }">
            <span v-if="column.key === 'causes'">{{ describeCauses(record.insufficientCauses, record.statuses) }}</span>
          </template>
        </a-table>
      </div>
    </details>
    <details class="status-details">
      <summary>数据与核实说明</summary>
      <div class="details-content status-note">
        <p>查询和详情读取已保存的核实结果；各日以完整成功批次为准，不代表实时数据。最早同步 {{ formatDateTimeDisplay(freshness.oldestSyncedAt) }}。</p>
        <p>系统自动核实，人工只抽查与处理异常。通过无须人工确认；证据不足、执行失败、规则未接入分别列示。</p>
        <p>{{ sampling ? `当前账号已抽查 ${sampling.sampled} 单，其中发现问题 ${sampling.disputed} 单。` : '当前抽查统计尚未读取，不能按0单解释。' }}</p>
        <p>页面每分钟刷新已生效范围，打开订单详情、页面不可见或查询操作中暂停；刷新不触发源系统取证。</p>
      </div>
    </details>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { Alert as AAlert, Button as AButton, Table as ATable } from 'ant-design-vue'
import type { RiskCatalogFreshness } from '@/api/riskVerification'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const props = defineProps<{ freshness: RiskCatalogFreshness; insufficient: number; sampling?: { sampled: number; disputed: number } }>()
defineEmits<{ 'inspect-insufficient': [] }>()
const reports = computed(() => props.freshness.preparation?.reports || [])
const insufficientDays = computed(() => reports.value.filter(report => (report.statuses.insufficient || 0) > 0 || Object.values(report.insufficientCauses).some(value => value > 0)).length)
const warnings = computed(() => {
  const messages: string[] = []
  const attempt = props.freshness.latestAttempt?.status
  if (attempt === 'failed') messages.push('最近同步失败，当前保留上次成功结果；请排查并重新运行清洗任务')
  else if (attempt === 'running') messages.push('同步进行中，当前仍展示各日上次成功结果')
  const missing = [...new Set([...(props.freshness.missingDays || []), ...(props.freshness.preparation?.missingDays || [])])].sort()
  if (missing.length) messages.push(`尚未完成同步或清洗：${missing.join('、')}；其他成功日期仍可查询，缺失不表示零订单`)
  else if (!props.freshness.complete) messages.push('所选范围的数据覆盖尚不完整，请核对同步情况')
  return messages
})
const reportColumns = [{ title: '出票日期', dataIndex: 'day', width: 130 }, { title: '清洗订单数', dataIndex: 'orders', width: 110 }, { title: '清洗耗时（秒）', dataIndex: 'seconds', width: 130 }, { title: '证据诊断', key: 'causes' }]
const causeLabels: Record<string, string> = { MATCH_FACTS_INCOMPLETE: '订单匹配条件不足', NO_APPLICABLE_RULE: '无适用配置', PRIORITY_EVIDENCE: '规则排序依据不足', HISTORY_RECONSTRUCTION: '历史配置无法还原', HISTORY_STATUS_BASELINE_MISSING: '历史状态缺修改前值', PARSER_REVIEW_REQUIRED: '解析能力待自查', HISTORY_LEDGER_INCOMPLETE: '历史记录不完整', SCOPE_INCOMPLETE: '关联范围不完整', PASSENGER_EVIDENCE: '乘机人证据不足', MONEY_EVIDENCE: '金额证据不足', THRESHOLD_EVIDENCE: '止损证据不足', UNCLASSIFIED_EVIDENCE: '待分析原因' }
function describeCauses(insufficientCauses: Record<string, number>, statuses: Record<string, number>) {
  const causes = Object.entries(insufficientCauses).filter(([, count]) => count > 0)
  if (causes.length) return causes.map(([code, count]) => `${causeLabels[code] || code} ${count}单`).join('；')
  return statuses.insufficient ? `证据不足 ${statuses.insufficient} 单，原因待分析` : '未记录证据不足；核实通过与问题见业务结果'
}
</script>
<style scoped>
.data-status { min-width: 0; display: grid; gap: 8px; padding: 12px 16px; border: 1px solid #e4e9ef; border-radius: 8px; background: #fff; }
.status-summary, .status-facts { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 20px; }
.status-summary { justify-content: space-between; }
.status-facts { font-size: 13px; color: #69768a; }
.status-facts > :first-child { color: #182235; font-weight: 500; }
.insufficient-link { padding-inline: 0; color: #ad6800; height: auto; white-space: normal; text-align: left; }
.status-details { min-width: 0; }
summary { cursor: pointer; width: fit-content; max-width: 100%; font-size: 13px; color: #34506f; padding-block: 5px; overflow-wrap: anywhere; }
summary:focus-visible { outline: 2px solid #1677ff; outline-offset: 2px; }
.details-content { padding: 8px 0; min-width: 0; }
.status-note { color: #69768a; font-size: 12px; line-height: 1.7; }
.status-note p { margin: 0 0 6px; }
@media (max-width: 600px) { .data-status { padding: 12px; } .status-facts { gap: 6px 12px; } }
</style>
