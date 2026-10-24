<template>
  <details v-if="latest" open class="adm-draft-comparison">
    <summary>核对当前草稿与服务端最新记录（仅显示不同项）</summary>
    <div class="adm-sheet-preview" tabindex="0" aria-label="草稿和最新记录对照">
      <table>
        <thead>
          <tr>
            <th>字段</th>
            <th>服务端最新值</th>
            <th>当前草稿</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key">
            <td>{{ names[row.key] || row.key }}</td>
            <td>{{ row.latest }}</td>
            <td>{{ row.draft }}</td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="3">草稿与最新记录一致</td>
          </tr>
        </tbody>
      </table>
    </div>
  </details>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { Fields } from './api'
const props = defineProps<{ latest: Fields | null; draft: Fields }>()
const names: Record<string, string> = {
  admNo: 'ADM 单号',
  supplierName: '下发方',
  supplierType: '下发方类型',
  currency: '币种',
  originalAmount: '原始金额',
  amount: '明细金额',
  description: '问题描述',
  remark: '备注',
  issuedDate: '下发日期',
  deadline: '截止日期',
  analysis: '分析内容',
  finance: '财务设置',
  businessType: '业务类型',
  platform: '平台',
  shop: '店铺',
  site: '细分站点',
  orderNo: '订单号',
  ticketNo: '票号',
  pnr: 'PNR',
  system: '系统',
  pcc: 'PCC',
  matchStatus: '归属核实状态',
  matchEvidence: '归属依据',
  diffType: '差异分类',
  diffSecondType: '差异二级分类',
  differenceDescription: '差异说明',
  appealDecision: '申诉决策',
  appealReason: '申诉决策说明',
  recoveryRequired: '是否需恢复',
  attribution: '结案归因',
}
const display = (value: unknown) =>
  value == null || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
const rows = computed(() =>
  Object.keys(props.draft)
    .filter((key) => names[key] && JSON.stringify(props.draft[key]) !== JSON.stringify(props.latest?.[key]))
    .map((key) => ({ key, draft: display(props.draft[key]), latest: display(props.latest?.[key]) })),
)
</script>
