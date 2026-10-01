<template>
  <a-table
    :loading="loading"
    :columns="columns"
    :data-source="rows"
    row-key="recordKey"
    :pagination="false"
    :scroll="{ x: 1420 }"
    :locale="{ emptyText: '当前条件没有订单明细，不生成模拟记录' }"
  >
    <template #bodyCell="{ column, record }">
      <template v-if="column.key === 'date'">{{ record.businessDate }}</template>
      <template v-else-if="column.key === 'order'"><div class="order-id"><strong>{{ record.otaOrderNo || '—' }}</strong><small>{{ record.issueTicketNo || '无票号' }}</small></div></template>
      <template v-else-if="column.key === 'channel'"><div class="order-id"><strong>{{ record.platform || '未填写' }}</strong><small>{{ record.site || '未填写站点' }}</small></div></template>
      <template v-else-if="column.key === 'airline'">{{ record.airline || '—' }}</template>
      <template v-else-if="column.key === 'department'">{{ record.department || '—' }}</template>
      <template v-else-if="column.key === 'policy'">{{ record.policyOperator || '—' }}</template>
      <template v-else-if="column.key === 'reason'">{{ record.reason || '—' }}</template>
      <template v-else-if="column.key === 'verify'">{{ record.verifyResult || '—' }}</template>
      <template v-else-if="column.key === 'tickets'">{{ count(record.ticketCount) }}</template>
      <template v-else-if="column.key === 'profit'"><strong :class="{ negative: negative(record.estimatedProfit) }">{{ money(record.estimatedProfit) }}</strong></template>
      <template v-else-if="column.key === 'action'"><a-button type="link" size="small" @click="emit('openOrder', record)">查看详情</a-button></template>
    </template>
  </a-table>
  <div class="pagination-row">
    <span>按{{ timeField }}倒序，亏损金额较低的记录优先</span>
    <a-pagination
      :current="page"
      :page-size="pageSize"
      :total="total"
      :show-size-changer="true"
      :page-size-options="['20', '30', '50', '100']"
      show-less-items
      @change="changePage"
      @showSizeChange="changePage"
    />
  </div>
</template>

<script setup lang="ts">
import { Pagination as APagination } from 'ant-design-vue'
import type { RiskOrderRow } from '@/api/riskBusiness'

defineProps<{
  rows: RiskOrderRow[]
  total: number
  page: number
  pageSize: number
  timeField: string
  loading?: boolean
}>()

const emit = defineEmits<{
  openOrder: [row: RiskOrderRow]
  changePage: [page: number, pageSize: number]
}>()

const moneyFormatter = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const countFormatter = new Intl.NumberFormat('zh-CN')
const money = (value: string | number | null | undefined) => value == null ? '—' : moneyFormatter.format(Number(value))
const count = (value: number | null | undefined) => value == null ? '—' : countFormatter.format(value)
const negative = (value: string | null | undefined) => value != null && Number(value) < 0
const changePage = (page: number, pageSize: number) => emit('changePage', page, pageSize)

const columns = [
  { title: '日期', key: 'date', width: 115, fixed: 'left' as const },
  { title: 'OTA订单 / 票号', key: 'order', width: 190 },
  { title: '平台 / 站点', key: 'channel', width: 170 },
  { title: '航司', key: 'airline', width: 80 },
  { title: '业务部门', key: 'department', width: 130 },
  { title: '政策员', key: 'policy', width: 100 },
  { title: '盈亏原因', key: 'reason', width: 150 },
  { title: '核实结果', key: 'verify', width: 120 },
  { title: '票数', key: 'tickets', width: 80 },
  { title: '预估利润 / 元', key: 'profit', width: 140 },
  { title: '详情', key: 'action', width: 100, fixed: 'right' as const },
]
</script>

<style scoped>
.order-id { display: grid; gap: 3px; }
.order-id strong { color: #334155; font-size: 11px; }
.order-id small { color: #8793a5; font-size: 9px; }
.negative { color: #c44752 !important; }
.pagination-row { padding-top: 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.pagination-row > span { color: #8995a7; font-size: 11px; }
@media (max-width: 600px) { .pagination-row { align-items: stretch; flex-direction: column; } }
</style>
