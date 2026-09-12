<template>
  <div class="page-wrap problems-page">
    <PageHeader eyebrow="PROBLEM CENTER" title="经营问题中心" description="从出、退、改、增负利润结果中发现问题，并保留可核对的业务记录证据">
      <a-button :loading="loading" @click="loadData"><ReloadOutlined />刷新数据</a-button>
    </PageHeader>

    <DataStateBar
      :label="data?.mode === 'live' ? 'Hive实际数据' : '演示数据'"
      :message="data?.source ?? '正在检查经营问题'"
      :freshness="data ? `查询时间 ${data.generatedAt.slice(11, 19)}` : '查询中'"
      metric-state="业务估算负利润"
    />

    <div class="profit-filter">
      <div class="profit-filter-fields">
        <a-segmented v-model:value="periodPreset" :options="periodOptions" @change="applyPreset" />
        <span class="filter-label">业务发生日期</span>
        <a-date-picker v-model:value="startDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
        <span class="date-separator">至</span>
        <a-date-picker v-model:value="endDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
        <a-button type="primary" :loading="loading" @click="loadData"><SearchOutlined />查询</a-button>
      </div>
      <span class="filter-tip">默认今日；这里只发现问题，不直接判定责任</span>
    </div>

    <a-alert v-if="error" type="error" show-icon :message="error" class="section-gap" />
    <a-alert v-else-if="data && !data.available" type="warning" show-icon message="部分业务查询失败，汇总不按0展示，请查看各业务状态。" class="section-gap" />

    <a-spin :spinning="loading">
      <template v-if="data">
        <div class="problem-summary-grid">
          <a-card class="issue-summary-card" :bordered="false">
            <span>负利润记录</span><strong class="negative">{{ summaryCount }}</strong><small>四类业务记录合计</small>
          </a-card>
          <a-card class="issue-summary-card" :bordered="false">
            <span>负利润金额</span><strong class="negative">{{ summaryLoss }}</strong><small>负利润绝对值合计</small>
          </a-card>
          <a-card class="issue-summary-card" :bordered="false">
            <span>涉及业务</span><strong>{{ data.summary?.affectedBusinessCount ?? '—' }}</strong><small>最多4类业务</small>
          </a-card>
          <a-card class="issue-summary-card" :bordered="false">
            <span>数据完整性</span><strong>{{ data.summary ? `${data.summary.availableBusinessCount}/4` : '不完整' }}</strong><small>查询成功的业务来源</small>
          </a-card>
        </div>

        <div class="problem-domain-grid">
          <a-card v-for="item in data.businesses" :key="item.key" class="problem-domain-card" :class="`metric-${item.key}`" :bordered="false">
            <div class="problem-domain-head"><strong>{{ item.name }}负利润</strong><a-tag :color="item.available ? 'success' : 'error'">{{ item.available ? '已检查' : '失败' }}</a-tag></div>
            <div class="problem-domain-values">
              <span><small>记录数</small><b>{{ item.negativeCount === null ? '—' : formatCount(item.negativeCount) }}</b></span>
              <span><small>负利润金额</small><b>{{ item.lossAmount === null ? '—' : money(item.lossAmount) }}</b></span>
            </div>
            <a-progress :percent="item.lossShare" :show-info="false" :stroke-color="item.available ? '#d65a64' : '#a0a9b6'" />
            <small class="problem-share">{{ item.available ? `占已识别负利润 ${item.lossShare.toFixed(2)}%` : item.error }}</small>
          </a-card>
        </div>

        <a-card class="panel-card problem-evidence-card" :bordered="false" title="负利润证据明细 Top 20">
          <template #extra><span class="panel-caption">按单条利润从低到高</span></template>
          <a-table :columns="columns" :data-source="data.items" :pagination="false" :row-key="rowKey" size="middle" :scroll="{ x: 1450 }">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'business'"><a-tag>{{ record.businessName }}</a-tag></template>
              <template v-else-if="column.key === 'id'"><div class="problem-id"><strong>{{ record.orderNo || '—' }}</strong><code>{{ record.eventId || '—' }}</code></div></template>
              <template v-else-if="column.key === 'ticket'">{{ record.ticketNo || '—' }}</template>
              <template v-else-if="column.key === 'profit'"><strong class="loss-value">-{{ money(Math.abs(record.profit)) }}</strong></template>
              <template v-else-if="column.key === 'time'">{{ record.occurredAt.slice(0, 19) || '—' }}</template>
            </template>
          </a-table>
          <div class="problem-note"><InfoCircleOutlined />{{ data.notes.join(' ') }}</div>
        </a-card>
      </template>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { InfoCircleOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { getProfitProblems, type ProfitProblemData, type ProfitProblemItem } from '@/api/dashboard'
import DataStateBar from '@/components/DataStateBar.vue'
import PageHeader from '@/components/PageHeader.vue'

const formatDate = (value: Date) => {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
const now = new Date()
const startDate = ref(formatDate(now))
const endDate = ref(formatDate(now))
const periodPreset = ref('today')
const data = ref<ProfitProblemData>()
const loading = ref(false)
const error = ref('')
const periodOptions = [
  { label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' },
  { label: '本月', value: 'month' }, { label: '本年', value: 'year' },
  { label: '自定义', value: 'custom' },
]
const columns = [
  { title: '业务', key: 'business', width: 85, fixed: 'left' },
  { title: '订单/事件', key: 'id', width: 210, fixed: 'left' },
  { title: '票号', key: 'ticket', width: 150 },
  { title: '平台', dataIndex: 'platform', key: 'platform', width: 150 },
  { title: '供应商', dataIndex: 'supplier', key: 'supplier', width: 190 },
  { title: '航司', dataIndex: 'airline', key: 'airline', width: 90 },
  { title: '操作人', dataIndex: 'operator', key: 'operator', width: 130 },
  { title: '发生时间', key: 'time', width: 170 },
  { title: '负利润金额', key: 'profit', width: 150, fixed: 'right' },
]
const rowKey = (record: ProfitProblemItem) => `${record.businessKey}-${record.eventId}`

const money = (value: number) => `${new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)} 元`
const formatCount = (value: number) => new Intl.NumberFormat('zh-CN').format(value)
const summaryCount = computed(() => data.value?.summary ? formatCount(data.value.summary.negativeCount) : '—')
const summaryLoss = computed(() => data.value?.summary ? money(data.value.summary.lossAmount) : '—')

const applyPreset = (value: string | number) => {
  const preset = String(value)
  const today = new Date()
  let start = today
  let end = today
  if (preset === 'yesterday') { start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1); end = start }
  else if (preset === 'month') start = new Date(today.getFullYear(), today.getMonth(), 1)
  else if (preset === 'year') start = new Date(today.getFullYear(), 0, 1)
  else if (preset === 'custom') return
  startDate.value = formatDate(start)
  endDate.value = formatDate(end)
  loadData()
}
const markCustom = () => { periodPreset.value = 'custom' }
const loadData = async () => {
  loading.value = true
  error.value = ''
  try { data.value = await getProfitProblems({ startDate: startDate.value, endDate: endDate.value }) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '经营问题加载失败' }
  finally { loading.value = false }
}
onMounted(loadData)
</script>
