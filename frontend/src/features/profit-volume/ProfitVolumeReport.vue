<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FilterScope } from '@/api/comprehensive'
import { fetchProfitVolume, profitGroups, type Drilldown, type ProfitGroup, type ProfitMetric, type ProfitVolumeData } from '@/api/profitVolume'

const props = defineProps<{ scope: FilterScope; scopeLabel: string }>()
const emit = defineEmits<{ drill: [selection: Drilldown] }>()
const data = ref<ProfitVolumeData>()
const loading = ref(false)
const error = ref('')
const missingDays = ref<string[]>([])
const retry = ref(0)
const metrics = [
  { key: 'segmentCount', label: '航段数' },
  { key: 'profit', label: '售前利润' },
  { key: 'perSegmentProfit', label: '单段利润' },
] as const
const columns = [
  { title: '出票日期', key: 'date', fixed: 'left' as const, width: 133 },
  ...(Object.entries(profitGroups) as [ProfitGroup, string][]).flatMap(([group, title]) =>
    metrics.map(({ key, label }) => ({
      key: `${group}-${key}`, title: group === 'total' ? (key === 'segmentCount' ? '总航段量' : '总' + label)
        : title + (key === 'segmentCount' ? '' : '-') + label,
      align: 'right' as const, width: 121, group, metric: key, className: 'metric-' + group,
    })),
  ),
]
const rows = computed(() => data.value ? [...data.value.rows, { ...data.value.summary, date: '区间合计' }] : [])
const hasRecords = computed(() => Boolean(data.value?.summary.total.recordCount))
const formatter = new Intl.NumberFormat('zh-CN', {
  style: 'currency', currency: 'CNY', currencySign: 'accounting', maximumFractionDigits: 0,
})
const counts = new Intl.NumberFormat('zh-CN')
function format(value: string | number | null, metric: keyof ProfitMetric) {
  if (value == null) return '—'
  return (metric === 'segmentCount' ? counts : formatter).format(Number(value))
}
watch([() => props.scope, retry], async ([scope], _old, onCleanup) => {
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  loading.value = true
  data.value = undefined
  error.value = ''
  missingDays.value = []
  try {
    const result = await fetchProfitVolume(scope, controller.signal)
    if (controller.signal.aborted) return
    if (result.available) data.value = result
    else {
      error.value = result.error
      missingDays.value = result.missingDays ?? []
    }
  } catch (failure) {
    if (!controller.signal.aborted) error.value = failure instanceof Error ? failure.message : '盈/冲查询失败'
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}, { immediate: true })
</script>

<template>
  <section class="profit-volume">
    <p>出票日期 {{ scope.startDate }} 至 {{ scope.endDate }} · CNY · {{ scopeLabel }}</p>
    <a-alert v-if="error" type="warning" show-icon :message="error">
      <template #description v-if="missingDays.length">未同步 {{ missingDays.length }} 天，首日 {{ missingDays[0] }}。</template>
      <template #action><a-button size="small" @click="retry++">重试</a-button></template>
    </a-alert>
    <a-spin v-else :spinning="loading" tip="正在查询盈/冲">
      <a-empty v-if="!loading && !hasRecords" description="所选范围已同步，没有符合条件的出票记录" />
      <template v-if="data">
        <a-alert v-if="data.adsReconciliation !== 'unavailable'" class="quality" :type="data.adsReconciliation === 'matched' ? 'info' : 'warning'" show-icon
          :message="data.adsReconciliation === 'matched' ? '同范围出票指标已与综合 ADS 对上' : '同批综合 ADS 对账有差异'">
          <template #description>
            已知利润按源精度汇总，逐笔投影至四位后合计 {{ data.summary.total.adsProjectedKnownProfit }} 元，
            原精度减四位投影差 {{ data.summary.total.knownProfitProjectionDifference }} 元。
            <span v-if="data.adsDifferenceDays.length">差异日期共 {{ data.adsDifferenceDays.length }} 天，首日 {{ data.adsDifferenceDays[0] }}。</span>
          </template>
        </a-alert>
        <a-alert v-if="data.summary.total.unrecognizedTicketRecords" class="quality" type="info" show-icon
          :message="`当前范围有 ${data.summary.total.unrecognizedTicketRecords} 条票号待识别，仍计入对应航段和利润。`" />
        <a-alert v-if="data.summary.unclassified.recordCount || data.summary.total.segmentMissingCount"
          class="quality" type="warning" show-icon message="当前范围存在未归组或缺失数据">
          <template #description>
            未归组 {{ data.summary.unclassified.recordCount }} 条，涉及航段 {{ format(data.summary.unclassified.segmentCount, 'segmentCount') }}。
            利润缺失 {{ data.summary.total.profitMissingCount }} 条，航段缺失 {{ data.summary.total.segmentMissingCount }} 条。
            未归组记录计入整体，缺失或零分母的受影响指标显示「—」。
          </template>
        </a-alert>
        <a-table v-if="hasRecords" size="small" :columns="columns" :data-source="rows" row-key="date" :pagination="false" :scroll="{ x: 1222, y: 440 }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'date'">
              <a-button v-if="record.date !== '区间合计' && record.total.recordCount" type="link" size="small"
                @click="emit('drill', { date: record.date, group: 'total', snapshotVersion: data.snapshotVersion })">{{ record.date }}</a-button>
              <span v-else>{{ record.date }}</span><small v-if="!record.total.recordCount">零出票</small>
            </template>
            <template v-else>
              <a-button v-if="column.metric === 'profit' && record.date !== '区间合计' && record[column.group].recordCount"
                type="link" size="small" :class="{ negative: Number(record[column.group][column.metric]) < 0 }" :aria-label="`${record.date} ${profitGroups[column.group as ProfitGroup]} 分析`"
                @click="emit('drill', { date: record.date, group: column.group, snapshotVersion: data.snapshotVersion })">{{ format(record[column.group][column.metric], column.metric) }}</a-button>
              <span v-else :class="{ negative: Number(record[column.group][column.metric]) < 0 }">{{ format(record[column.group][column.metric], column.metric) }}</span>
            </template>
          </template>
        </a-table>
      </template>
    </a-spin>
  </section>
</template>

<style scoped>
.profit-volume p { color: #52627a; margin: 0 0 12px; }
.quality { margin-bottom: 12px; }
.profit-volume :deep(td) { font-variant-numeric: tabular-nums; }
.profit-volume :deep(td small) { display: block; color: #52627a; }
.profit-volume :deep(td .ant-btn) { display: block; margin-left: auto; padding-inline: 0; }
.profit-volume :deep(.metric-gain) { background: #e4f4f4; }
.profit-volume :deep(.metric-loss) { background: #fbe9ee; }
.profit-volume :deep(.metric-total) { background: #fcf3db; }
.negative { color: #ae3228; }
</style>
