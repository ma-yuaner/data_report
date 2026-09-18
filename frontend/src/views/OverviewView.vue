<template>
  <div class="page-wrap profit-overview">
    <PageHeader eyebrow="PROFIT OVERVIEW" title="经营总览" description="聚焦出票、退票、改签与增值服务的业务估算利润">
      <a-button :loading="loading" @click="loadOverview"><ReloadOutlined />刷新数据</a-button>
    </PageHeader>

    <DataStateBar
      :label="overview?.status.label ?? '正在连接数据源'"
      :message="overview ? `${overview.source} · 金额为业务估算口径` : '正在获取经营利润数据'"
      :freshness="overview?.status.freshness ?? '查询中'"
      :metric-state="overview?.status.metricState ?? '业务估算口径'"
    />

    <div class="profit-filter">
      <div class="profit-filter-fields">
        <a-segmented v-model:value="periodPreset" :options="periodOptions" @change="applyPreset" />
        <span class="filter-label">统计期间</span>
        <a-date-picker v-model:value="startDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
        <span class="date-separator">至</span>
        <a-date-picker v-model:value="endDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
        <a-button type="primary" :loading="loading" @click="loadOverview"><SearchOutlined />查询</a-button>
      </div>
      <span class="filter-tip">各业务按自身发生时间统计，结束日期包含当天</span>
    </div>

    <a-alert v-if="error" type="error" show-icon :message="error" class="section-gap" />

    <a-spin :spinning="overviewLoading">
      <template v-if="overview">
        <section class="total-profit-card" :class="{ 'is-unavailable': !overview.totalProfit.available, 'is-negative': Number(overview.totalProfit.value) < 0 }">
          <div>
            <span class="total-profit-label">总预估利润</span>
            <strong>{{ formatProfit(overview.totalProfit.value, overview.totalProfit.available) }}</strong>
            <small>{{ overview.period.startDate }} 至 {{ overview.period.endDate }} · 单位：元</small>
          </div>
          <div class="total-profit-formula">
            <span v-for="(item, index) in overview.metrics" :key="item.key">
              <b v-if="index">+</b>{{ item.label }}利润
            </span>
          </div>
        </section>

        <div class="profit-metric-grid">
          <a-card
            v-for="item in overview.metrics"
            :key="item.key"
            class="profit-metric-card"
            :class="[`metric-${item.key}`, { 'is-unavailable': !item.available }]"
            :bordered="false"
          >
            <div class="metric-heading">
              <span class="metric-icon"><component :is="metricIcons[item.key]" /></span>
              <div><small>{{ item.label.toUpperCase() }}</small><h2>{{ item.label }}利润</h2></div>
              <a-tag :color="item.available ? 'success' : 'error'">{{ item.available ? '已获取' : '获取失败' }}</a-tag>
            </div>
            <div class="metric-profit" :class="{ 'is-negative': Number(item.profit) < 0 }">{{ formatProfit(item.profit, item.available) }}</div>
            <div class="metric-volume" v-if="item.available">
              <span><small>{{ item.countLabel }}</small><strong>{{ formatCount(item.count) }}</strong></span>
              <span v-if="item.segmentLabel"><small>{{ item.segmentLabel }}</small><strong>{{ formatCount(item.segmentCount) }}</strong></span>
            </div>
            <a-alert v-else type="error" show-icon :message="item.error ?? '查询失败'" />
            <div class="metric-foot">时间字段：{{ item.timeField }}</div>
          </a-card>
        </div>

        <a-card class="panel-card profit-notes" :bordered="false" title="当前统计口径">
          <a-row :gutter="[18, 12]">
            <a-col v-for="(note, index) in overview.notes" :key="note" :xs="24" :md="12">
              <div class="profit-note"><span>{{ index + 1 }}</span>{{ note }}</div>
            </a-col>
          </a-row>
        </a-card>
      </template>
    </a-spin>

    <section class="risk-profit-section">
      <div class="risk-profit-title">
        <div>
          <span>RISK PROFIT RECONCILIATION</span>
          <h2>风控利润核对</h2>
          <p>独立汇总出票、退票、改签核对表，不改变上方经营总览口径</p>
        </div>
        <a-tag color="purple">{{ riskSummary?.source ?? '正在连接核对数据源' }}</a-tag>
      </div>
      <div class="profit-filter">
        <div class="profit-filter-fields">
          <a-segmented v-model:value="periodPreset" :options="periodOptions" @change="applyPreset" />
          <span class="filter-label">统计期间</span>
          <a-date-picker v-model:value="startDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
          <span class="date-separator">至</span>
          <a-date-picker v-model:value="endDate" value-format="YYYY-MM-DD" :allow-clear="false" @change="markCustom" />
          <a-button type="primary" :loading="loading" @click="loadOverview"><SearchOutlined />查询</a-button>
        </div>
        <span class="filter-tip">与上方估算利润共用统计期间，结束日期包含当天</span>
      </div>
      <a-alert v-if="riskError" type="error" show-icon :message="riskError" class="section-gap" />
      <a-spin :spinning="riskLoading">
        <template v-if="riskSummary">
          <div class="risk-profit-grid">
            <a-card
              v-for="item in riskSummary.metrics"
              :key="item.key"
              class="risk-profit-card"
              :class="[`metric-${item.key}`, { 'is-unavailable': !item.available }]"
              :bordered="false"
            >
              <div class="risk-profit-card-head">
                <div><span>{{ item.label }}</span><small>预估利润核对</small></div>
                <a-tag :color="item.available ? 'success' : 'error'">{{ item.available ? '已获取' : '获取失败' }}</a-tag>
              </div>
              <strong :class="{ 'is-negative': Number(item.estimatedProfit) < 0 }">
                {{ formatProfit(item.estimatedProfit, item.available) }}
              </strong>
              <div v-if="item.available" class="risk-profit-count">
                <span>总票数</span><b>{{ formatCount(item.ticketCount) }}</b>
              </div>
              <a-alert v-else type="error" show-icon :message="item.error ?? '查询失败'" />
              <div class="risk-profit-foot">
                <span>{{ riskSummary.period.monthLabel }}</span>
                <code>{{ item.timeField }}</code>
              </div>
            </a-card>
          </div>
          <div class="risk-profit-source">
            <span>{{ riskSummary.source }} · {{ riskSummary.period.startDate }} 至 {{ riskSummary.period.endDate }}</span>
            <span>票数：sum(ticket_num) · 利润：sum(estimated_profit_cny)</span>
          </div>
        </template>
      </a-spin>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { DatePicker as ADatePicker } from 'ant-design-vue'
import {
  CheckCircleOutlined, PlusCircleOutlined, ReloadOutlined, SearchOutlined,
  SendOutlined, SwapOutlined,
} from '@ant-design/icons-vue'
import {
  getOverview, getRiskProfitSummary,
  type OverviewData, type ProfitMetric, type RiskProfitSummaryData,
} from '@/api/dashboard'
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
const overview = ref<OverviewData>()
const riskSummary = ref<RiskProfitSummaryData>()
const overviewLoading = ref(false)
const riskLoading = ref(false)
const loading = computed(() => overviewLoading.value || riskLoading.value)
const error = ref('')
const riskError = ref('')

let riskRequestId = 0

onBeforeUnmount(() => {
  ++riskRequestId
})

const metricIcons: Record<ProfitMetric['key'], object> = {
  issue: SendOutlined,
  refund: CheckCircleOutlined,
  change: SwapOutlined,
  ancillary: PlusCircleOutlined,
}

const periodOptions = [
  { label: '今日', value: 'today' },
  { label: '昨日', value: 'yesterday' },
  { label: '本月', value: 'month' },
  { label: '本年', value: 'year' },
  { label: '自定义', value: 'custom' },
]

const applyPreset = (value: string | number) => {
  const preset = String(value)
  const today = new Date()
  let start = today
  let end = today
  if (preset === 'yesterday') {
    start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1)
    end = start
  } else if (preset === 'month') {
    start = new Date(today.getFullYear(), today.getMonth(), 1)
  } else if (preset === 'year') {
    start = new Date(today.getFullYear(), 0, 1)
  } else if (preset === 'custom') {
    return
  }
  startDate.value = formatDate(start)
  endDate.value = formatDate(end)
  loadOverview()
}

const markCustom = () => { periodPreset.value = 'custom' }

const formatProfit = (value: number | null, available: boolean) => {
  if (!available || value === null) return '暂不可用'
  return `${new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)} 元`
}

const formatCount = (value: number | null) => value === null ? '—' : new Intl.NumberFormat('zh-CN').format(value)

const loadCoreOverview = async () => {
  error.value = ''
  overviewLoading.value = true
  try {
    overview.value = await getOverview({ startDate: startDate.value, endDate: endDate.value })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '利润数据加载失败'
  } finally {
    overviewLoading.value = false
  }
}

const loadRiskProfit = async () => {
  const requestId = ++riskRequestId
  riskError.value = ''
  riskLoading.value = true
  try {
    const result = await getRiskProfitSummary({ startDate: startDate.value, endDate: endDate.value })
    if (requestId === riskRequestId) riskSummary.value = result
  } catch (reason) {
    if (requestId !== riskRequestId) return
    riskSummary.value = undefined
    riskError.value = reason instanceof Error ? reason.message : '风控利润核对数据加载失败'
  } finally {
    if (requestId === riskRequestId) riskLoading.value = false
  }
}

const loadOverview = async () => {
  await Promise.all([loadCoreOverview(), loadRiskProfit()])
}

onMounted(loadOverview)
</script>
