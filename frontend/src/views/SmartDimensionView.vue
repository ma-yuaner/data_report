<template>
  <div class="page-wrap smart-page">
    <PageHeader eyebrow="SMART DIMENSION ANALYSIS" title="维度分析" description="按一个或多个业务维度组合分析出票、智能参与、成功、使用和利润表现" />
    <SmartAnalysisFilters :loading="loading" @query="queryFromStart" @reset="resetPage" />
    <DataStateBar :label="stateLabel" :message="stateMessage" :freshness="data?.updatedAt || '尚未读取'" metric-state="分组后重新计算比率" />
    <a-alert v-if="data?.error" class="smart-alert" type="error" show-icon :message="data.error" />

    <a-card :bordered="false" class="panel-card smart-dimension-panel">
      <div class="dimension-toolbar">
        <label><span>分析维度</span><a-select v-model:value="groups" mode="multiple" :options="dimensionOptions" :max-tag-count="4" placeholder="至少选择一个维度" @change="queryFromStart" /></label>
        <label><span>排序指标</span><a-select v-model:value="sortBy" :options="sortOptions" @change="queryFromStart" /></label>
        <label><span>排序方向</span><a-select v-model:value="direction" :options="directionOptions" @change="queryFromStart" /></label>
        <a-button type="primary" :loading="loading" @click="queryFromStart"><SearchOutlined />刷新分析</a-button>
      </div>

      <div v-if="data?.available && data.hasData" class="dimension-total-grid">
        <div><span>当前范围出票量</span><strong>{{ count(data.totals.ticketCount) }} 张</strong></div>
        <div><span>智能使用出票量</span><strong>{{ count(active(data.totals).usedCount) }} 张</strong></div>
        <div><span>智能使用率</span><strong>{{ percent(active(data.totals).useRate) }}</strong></div>
        <div><span>智能利润</span><strong>{{ money(active(data.totals).profit) }} 元</strong></div>
      </div>

      <a-table :columns="columns" :data-source="data?.rows || []" :loading="loading" row-key="key" :pagination="false" :scroll="{ x: tableWidth }" :locale="{ emptyText: '当前范围暂无维度组合记录' }">
        <template #bodyCell="{ column, record }">
          <template v-if="String(column.key).startsWith('dimension-')"><span class="dimension-value">{{ record.path[column.dimensionIndex]?.name || '未填写' }}</span></template>
          <template v-else-if="column.key === 'ticketCount'">{{ count(record.metrics.ticketCount) }}</template>
          <template v-else-if="column.key === 'totalProfit'"><span :class="{ negative: Number(record.metrics.totalProfit) < 0 }">{{ money(record.metrics.totalProfit) }}</span></template>
          <template v-else-if="column.key === 'segmentCount'">{{ count(record.metrics.segmentCount) }}</template>
          <template v-else-if="column.key === 'participated'">{{ count(active(record.metrics).participatedCount) }}</template>
          <template v-else-if="column.key === 'succeeded'">{{ count(active(record.metrics).succeededCount) }}</template>
          <template v-else-if="column.key === 'used'">{{ count(active(record.metrics).usedCount) }}</template>
          <template v-else-if="column.key === 'useRate'">{{ percent(active(record.metrics).useRate) }}</template>
          <template v-else-if="column.key === 'smartProfit'"><span :class="{ negative: Number(active(record.metrics).profit) < 0 }">{{ money(active(record.metrics).profit) }}</span></template>
          <template v-else-if="column.key === 'averageProfit'">{{ money(active(record.metrics).averageProfit) }}</template>
          <template v-else-if="column.key === 'action'"><a-button type="link" size="small" @click="openDetails(record.path)">查看票单 →</a-button></template>
        </template>
      </a-table>
      <div class="dimension-pagination">
        <span>共 {{ count(data?.total) }} 种组合</span>
        <a-pagination v-model:current="page" v-model:pageSize="pageSize" :total="data?.total || 0" :page-size-options="['10','20','50','100']" show-size-changer @change="load" />
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message, Pagination as APagination } from 'ant-design-vue'
import { SearchOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import SmartAnalysisFilters from '@/components/SmartAnalysisFilters.vue'
import { dimensionOptions, smartAnalysisApi, type SmartDimensionData, type SmartDimensionPath, type SmartMetrics } from '@/api/smartAnalysis'
import { useSmartAnalysisStore } from '@/stores/smartAnalysis'

const store = useSmartAnalysisStore()
const router = useRouter()
const data = ref<SmartDimensionData>()
const loading = ref(false)
const groups = ref<string[]>(['airline', 'platform'])
const sortBy = ref('smartProfit')
const direction = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const pageSize = ref(20)
const integer = new Intl.NumberFormat('zh-CN')
const currency = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const sortOptions = [
  { label: '智能利润', value: 'smartProfit' }, { label: '智能使用出票量', value: 'usedCount' },
  { label: '全部出票量', value: 'ticketCount' }, { label: '全部预估利润', value: 'totalProfit' },
  { label: '总航段数', value: 'segments' },
]
const directionOptions = [{ label: '降序', value: 'desc' }, { label: '升序', value: 'asc' }]
const activeKey = computed(() => store.smartType === 'all' ? 'smart' : store.smartType)
const active = (metrics: SmartMetrics) => metrics[activeKey.value]
const count = (value: number | null | undefined) => value == null ? '—' : integer.format(value)
const money = (value: string | null | undefined) => value == null ? '—' : currency.format(Number(value))
const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const stateLabel = computed(() => data.value?.available && data.value.hasData ? '真实Hive数据' : data.value?.available ? '当前范围暂无数据' : '数据不可用')
const stateMessage = computed(() => data.value?.available && data.value.hasData ? `${data.value.source} · ${groups.value.map(key => dimensionOptions.find(item => item.value === key)?.label).join(' × ')}` : data.value?.error || '查询无记录不认定为真实零')
const columns = computed(() => [
  ...(data.value?.dimensions || groups.value.map(key => ({ key, label: dimensionOptions.find(item => item.value === key)?.label || key }))).map((item, index) => ({ title: item.label, key: `dimension-${item.key}`, dimensionIndex: index, width: 125, fixed: index === 0 ? 'left' as const : undefined })),
  { title: '出票量', key: 'ticketCount', width: 100 },
  { title: '预估利润 / 元', key: 'totalProfit', width: 125 },
  { title: '总航段数', key: 'segmentCount', width: 105 },
  { title: '参与出票量', key: 'participated', width: 110 },
  { title: '成功出票量', key: 'succeeded', width: 110 },
  { title: '使用出票量', key: 'used', width: 110 },
  { title: '使用率', key: 'useRate', width: 95 },
  { title: '智能利润 / 元', key: 'smartProfit', width: 125 },
  { title: '智能单张利润 / 元', key: 'averageProfit', width: 145 },
  { title: '明细', key: 'action', width: 110, fixed: 'right' as const },
])
const tableWidth = computed(() => columns.value.reduce((sum, column) => sum + Number(column.width || 100), 0))

async function load() {
  if (!groups.value.length) { message.warning('请至少选择一个分析维度'); return }
  loading.value = true
  try {
    data.value = await smartAnalysisApi.dimensions({ ...store.applied }, {
      groupBy: groups.value, smartType: store.smartType, sortBy: sortBy.value,
      direction: direction.value, page: page.value, pageSize: pageSize.value,
    })
  } catch (error) { data.value = undefined; message.error(error instanceof Error ? error.message : '维度分析加载失败') }
  finally { loading.value = false }
}
function queryFromStart() { page.value = 1; void load() }
function resetPage() { groups.value = ['airline', 'platform']; sortBy.value = 'smartProfit'; direction.value = 'desc'; queryFromStart() }
function openDetails(path: SmartDimensionPath[]) {
  store.applyDimensionPath(path)
  void router.push({ path: '/smart-analysis/details', query: { stage: 'all', smartType: store.smartType } })
}
onMounted(load)
</script>

<style scoped>
.smart-alert { margin: 14px 0; }
.smart-dimension-panel { margin-top: 16px; }
.dimension-toolbar { display: grid; grid-template-columns: minmax(280px,1fr) 180px 120px auto; align-items: end; gap: 12px; margin-bottom: 16px; }
.dimension-toolbar label { display: grid; gap: 6px; color: #718096; font-size: 11px; }
.dimension-toolbar :deep(.ant-select) { width: 100%; }
.dimension-total-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; margin-bottom: 16px; }
.dimension-total-grid div { padding: 13px 15px; display: grid; gap: 5px; border-radius: 8px; background: #f5f8fc; }
.dimension-total-grid span { color: #7a8798; font-size: 10px; }
.dimension-total-grid strong { color: #324159; font-size: 16px; }
.dimension-value { color: #344258; font-weight: 600; }
.negative { color: #c14f5e; }
.dimension-pagination { padding-top: 16px; display: flex; align-items: center; justify-content: space-between; color: #7d8999; font-size: 11px; }
@media (max-width: 1000px) { .dimension-toolbar { grid-template-columns: 1fr 1fr; } .dimension-total-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (max-width: 620px) { .dimension-toolbar, .dimension-total-grid { grid-template-columns: 1fr; } .dimension-pagination { align-items: flex-start; flex-direction: column; gap: 12px; } }
</style>
