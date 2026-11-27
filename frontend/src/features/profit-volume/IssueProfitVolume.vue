<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Drawer as ADrawer } from 'ant-design-vue'
import type { ComprehensiveDetailData, DimensionKey, FilterScope } from '@/api/comprehensive'
import { fetchProfitVolumeDetails, fetchProfitVolumeDimension, profitGroups, type Drilldown, type ProfitGroup, type ProfitMetric } from '@/api/profitVolume'
import ProfitVolumeReport from './ProfitVolumeReport.vue'

const props = defineProps<{ startDate: string; endDate: string }>()
const labels = { platform: '平台', site: '站点', airline: '航司', product: '产品', policy: '政策员', supplier: '供应商', gds: 'GDS' } as const
const keys = Object.keys(labels) as DimensionKey[]
const groups = Object.keys(profitGroups) as ProfitGroup[]
const baseScope = computed<FilterScope>(() => ({
  preset: 'custom', startDate: props.startDate, endDate: props.endDate,
  platform: '', site: '', airline: '', product: '', policy: '', supplier: '', gds: '',
}))
const drill = ref<Drilldown>()
const filters = ref<Partial<Record<DimensionKey, {value: string; label: string}>>>({})
const scope = computed<FilterScope>(() => ({ ...baseScope.value,
  ...Object.fromEntries(Object.entries(filters.value).map(([key, value]) => [key, value.value])),
}))
const open = ref(false)
const available = computed(() => keys.filter(key => !filters.value[key]))
const dimension = ref<DimensionKey>('platform')
const details = ref(false)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const total = ref<ProfitMetric>()
const rows = ref<(ProfitMetric & {value: string; label: string})[]>([])
const detailData = ref<ComprehensiveDetailData & { ticketCount: number; unrecognizedTicketRecords: number }>()
const detailColumns = [
  { key: 'ticketNumber', title: '客票号', fixed: 'left' as const, width: 155 },
  { key: 'ticketRaw', title: '源票号', width: 165 },
  { key: 'orderReference', title: '订单号', width: 145 },
  ...[['ota_cname','平台'],['ota_site_cname','站点'],['airline_code','航司'],['ticket_product_raw','产品'],
    ['policy_operator','政策员'],['supplier_name','供应商'],['gds_code','GDS']]
    .map(([key,title]) => ({key,title,width:110})),
  { key: 'segmentCount', title: '航段数', width: 90 },
  { key: 'presaleProfit', title: '售前利润（元）', width: 145 },
].map(column => ({...column,dataIndex:column.key}))
const columns = [
  { title: '维度项', dataIndex: 'label', key: 'label' },
  { title: '可识别票数', dataIndex: 'ticketCount', key: 'ticketCount' },
  { title: '未识别记录', dataIndex: 'unrecognizedTicketRecords', key: 'unrecognizedTicketRecords' },
  { title: '航段数', dataIndex: 'segmentCount', key: 'segmentCount' },
  { title: '售前利润（元）', dataIndex: 'profit', key: 'profit' },
  { title: '单段利润（元/段）', dataIndex: 'perSegmentProfit', key: 'perSegmentProfit' },
  { title: '操作', key: 'action' },
]
const format = (value: unknown) => value ?? '—'
function startDrill(selection: Drilldown) {
  drill.value = selection
  filters.value = {}
  dimension.value = 'platform'
  page.value = 1
  details.value = false
  open.value = true
}
function narrow(row: {value: string; label: string}) {
  filters.value = { ...filters.value, [dimension.value]: {value: row.value, label: row.label} }
  dimension.value = available.value[0] ?? dimension.value
}
function clear(key: DimensionKey) {
  const next = {...filters.value}
  delete next[key]
  filters.value = next
  dimension.value = key
}
function changeGroup(group: ProfitGroup) {
  if (drill.value && drill.value.group !== group) drill.value = { ...drill.value, group }
}
watch(baseScope, () => { open.value = false })
watch([open, drill, scope, dimension, details, page], async (_, _old, onCleanup) => {
  const currentDrill = drill.value
  if (!open.value || !currentDrill) return
  const request = new AbortController()
  onCleanup(() => request.abort())
  loading.value = true
  error.value = ''
  try {
    if (details.value) {
      const result = await fetchProfitVolumeDetails(scope.value, currentDrill, page.value, 50, request.signal)
      if (request.signal.aborted) return
      if ('columns' in result && result.available) detailData.value = result
      else { detailData.value = undefined; error.value = result.error }
    } else {
      const result = await fetchProfitVolumeDimension(scope.value, currentDrill, dimension.value, request.signal)
      if (request.signal.aborted) return
      if (result.available) { rows.value = result.rows; total.value = result.total }
      else { rows.value = []; total.value = undefined; error.value = result.error }
    }
  } catch (failure) {
    if (!request.signal.aborted) error.value = failure instanceof Error ? failure.message : '查询失败'
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
})
</script>

<template>
  <ProfitVolumeReport :scope="baseScope" scope-label="出票分析" @drill="startDrill" />
  <a-drawer v-model:open="open" :width="'min(100%, 1180px)'" :title="details ? '逐票出票明细' : '出票日维度分析'">
    <a-space wrap class="scope">
      <strong>{{ drill?.date }} · {{ drill && profitGroups[drill.group] }}</strong>
      <a-tag v-for="key in keys.filter(key => filters[key])" :key="key" :closable="!details" @close.prevent="clear(key)">
        {{ labels[key] }} {{ filters[key]?.label }}
      </a-tag>
    </a-space>
    <a-alert v-if="error" type="warning" :message="error" show-icon />
    <a-spin v-else :spinning="loading">
      <template v-if="details">
        <a-button @click="details = false">返回维度分析</a-button>
        <p v-if="detailData">共 {{ detailData.ticketCount }} 票 · {{ detailData.total }} 条出票记录 · {{ detailData.unrecognizedTicketRecords }} 条票号待识别</p>
        <a-table class="results" :columns="detailColumns" :data-source="detailData?.rows ?? []" row-key="recordKey" size="small"
          :scroll="{ x: 1470, y: 480 }" :pagination="{ current: page, pageSize: 50, total: detailData?.total ?? 0, showSizeChanger: false, showTotal: (value: number) => `共 ${value} 条记录`, onChange: (value: number) => page = value }">
          <template #bodyCell="{ text }">{{ format(text) }}</template>
        </a-table>
      </template>
      <template v-else>
        <a-space class="scope">
          <a-button v-for="group in groups" :key="group" :type="drill?.group === group ? 'primary' : 'default'" @click="changeGroup(group)">{{ profitGroups[group] }}</a-button>
        </a-space>
        <br />
        <a-space wrap>
          <a-button v-for="key in available" :key="key" :type="dimension === key ? 'primary' : 'default'" @click="dimension = key">按{{ labels[key] }}</a-button>
        </a-space>
        <p v-if="total" class="results">共 {{ total.ticketCount }} 票 · {{ total.unrecognizedTicketRecords }} 条票号待识别 · {{ format(total.segmentCount) }} 段 · {{ format(total.profit) }} 元</p>
        <a-table v-if="available.length" :columns="columns" :data-source="rows" row-key="value" size="small" :scroll="{ x: 640 }">
          <template #bodyCell="{ column, text, record }">
            <a-button v-if="column.key === 'action'" type="link" @click="narrow(record)">按此项下钻</a-button>
            <template v-else>{{ format(text) }}</template>
          </template>
        </a-table>
        <a-button class="results" type="primary" :disabled="!total?.recordCount || loading" @click="page = 1; detailData = undefined; details = true">查看逐票明细</a-button>
      </template>
    </a-spin>
  </a-drawer>
</template>

<style scoped>
.scope { margin-bottom: 16px; }
.results { margin-top: 12px; }
</style>
