<template>
  <div class="page-wrap assets-page">
    <PageHeader eyebrow="DATA ASSETS" title="数据资产" description="明确目前有哪些业务表、能提供哪些指标，以及数据更新到什么时间">
      <a-button :loading="loading" @click="loadData"><ReloadOutlined />刷新状态</a-button>
    </PageHeader>

    <DataStateBar
      :label="data?.mode === 'live' ? '实际数据资产' : '资产配置清单'"
      :message="data?.source ?? '正在读取数据资产'"
      :freshness="data ? `检查时间 ${data.generatedAt.slice(11, 19)}` : '检查中'"
      metric-state="当前有效口径"
    />

    <a-alert v-if="error" type="error" show-icon :message="error" class="section-gap" />

    <div class="asset-summary">
      <div><DatabaseOutlined /><span><strong>{{ data?.assets.length ?? 0 }}</strong>核心业务表</span></div>
      <div><BookOutlined /><span><strong>{{ data?.metrics.length ?? 0 }}</strong>已登记指标</span></div>
      <div><FundProjectionScreenOutlined /><span><strong>{{ data?.analysisTaskCount ?? 0 }}</strong>历史分析任务</span></div>
      <div><CheckCircleOutlined /><span><strong>{{ readyCount }}</strong>数据源可用</span></div>
    </div>

    <a-spin :spinning="loading">
      <a-tabs v-model:active-key="activeTab" class="business-tabs">
        <a-tab-pane key="tables" tab="业务数据表">
          <a-card class="panel-card" :bordered="false">
            <a-table :columns="assetColumns" :data-source="data?.assets ?? []" :pagination="false" row-key="key" :scroll="{ x: 1180 }">
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'object'">
                  <div class="asset-object"><strong>{{ record.domain }}</strong><code>{{ record.database }}.{{ record.table }}</code></div>
                </template>
                <template v-else-if="column.key === 'metrics'">
                  <a-space :size="[4, 4]" wrap><a-tag v-for="metric in record.metrics" :key="metric">{{ metric }}</a-tag></a-space>
                </template>
                <template v-else-if="column.key === 'latest'">
                  <span>{{ formatTime(record.latestDataTime) }}</span>
                </template>
                <template v-else-if="column.key === 'columnCount'">
                  <span>{{ record.columnCount ?? '待同步确认' }}</span>
                </template>
                <template v-else-if="column.key === 'state'">
                  <a-tag :color="stateMeta(record.state).color">{{ stateMeta(record.state).label }}</a-tag>
                </template>
              </template>
            </a-table>
          </a-card>
        </a-tab-pane>

        <a-tab-pane key="metrics" tab="指标口径">
          <a-card class="panel-card" :bordered="false">
            <a-table :columns="metricColumns" :data-source="data?.metrics ?? []" :pagination="false" row-key="name" :scroll="{ x: 850 }">
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'name'"><strong>{{ record.name }}</strong></template>
                <template v-else-if="column.key === 'formula'"><code class="metric-formula">{{ record.formula }}</code></template>
                <template v-else-if="column.key === 'status'"><a-tag color="success">当前使用</a-tag></template>
              </template>
            </a-table>
          </a-card>
        </a-tab-pane>

        <a-tab-pane key="analyses" tab="分析资产">
          <a-card class="panel-card" :bordered="false">
            <a-alert type="info" show-icon message="已将历史脚本、SQL和自动报送去重归并为能力域；任务数量不等同于独立指标数量。" class="section-gap" />
            <a-table :columns="analysisColumns" :data-source="data?.analyses ?? []" :pagination="false" row-key="domain" :scroll="{ x: 900 }">
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'domain'"><strong>{{ record.domain }}</strong></template>
                <template v-else-if="column.key === 'maturity'"><a-tag :color="maturityColor(record.maturity)">{{ record.maturity }}</a-tag></template>
              </template>
            </a-table>
          </a-card>
        </a-tab-pane>

        <a-tab-pane key="freshness" tab="更新状态">
          <a-card class="panel-card" :bordered="false">
            <a-table :columns="freshnessColumns" :data-source="data?.assets ?? []" :pagination="false" row-key="key">
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'table'"><code>{{ record.table }}</code></template>
                <template v-else-if="column.key === 'latest'">{{ formatTime(record.latestDataTime) }}</template>
                <template v-else-if="column.key === 'state'"><a-tag :color="stateMeta(record.state).color">{{ stateMeta(record.state).label }}</a-tag></template>
                <template v-else-if="column.key === 'error'">{{ record.error ?? '—' }}</template>
              </template>
            </a-table>
          </a-card>
        </a-tab-pane>
      </a-tabs>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BookOutlined, CheckCircleOutlined, DatabaseOutlined, FundProjectionScreenOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { getAssetCatalog, type AssetCatalogData, type DataAssetItem } from '@/api/dashboard'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'

const activeTab = ref('tables')
const data = ref<AssetCatalogData>()
const loading = ref(false)
const error = ref('')
const readyCount = computed(() => data.value?.assets.filter(item => item.state === 'ready').length ?? 0)

const assetColumns = [
  { title: '业务与数据表', key: 'object', width: 260 },
  { title: '关键指标', key: 'metrics', width: 290 },
  { title: '时间字段', dataIndex: 'timeField', key: 'timeField', width: 155 },
  { title: '字段数', dataIndex: 'columnCount', key: 'columnCount', width: 90 },
  { title: '当前业务条件', dataIndex: 'condition', key: 'condition', width: 260 },
  { title: '最新业务时间', key: 'latest', width: 170 },
  { title: '状态', key: 'state', width: 100 },
]
const metricColumns = [
  { title: '指标名称', key: 'name', width: 170 },
  { title: '计算方式', key: 'formula', width: 330 },
  { title: '时间口径', dataIndex: 'timeField', key: 'timeField', width: 180 },
  { title: '指标阶段', dataIndex: 'stage', key: 'stage', width: 130 },
  { title: '状态', key: 'status', width: 110 },
]
const freshnessColumns = [
  { title: '业务', dataIndex: 'domain', key: 'domain' },
  { title: '数据表', key: 'table' },
  { title: '最新业务时间', key: 'latest' },
  { title: '可用状态', key: 'state' },
  { title: '说明', key: 'error' },
]
const analysisColumns = [
  { title: '分析能力域', key: 'domain', width: 170 },
  { title: '任务数', dataIndex: 'taskCount', key: 'taskCount', width: 90 },
  { title: '成熟度', key: 'maturity', width: 120 },
  { title: '代表性内容', dataIndex: 'representative', key: 'representative', width: 310 },
  { title: '数据中心处理', dataIndex: 'plan', key: 'plan', width: 220 },
]

const stateMeta = (state: DataAssetItem['state']) => ({
  configured: { label: '已配置', color: 'processing' }, ready: { label: '可用', color: 'success' },
  empty: { label: '暂无数据', color: 'warning' }, warning: { label: '时间异常', color: 'warning' },
  error: { label: '检查失败', color: 'error' },
}[state])
const formatTime = (value: string | null) => value ? value.slice(0, 19) : '待实际连接确认'
const maturityColor = (value: string) => value.includes('已接入') ? 'success' : value.includes('可接入') || value.includes('成熟') ? 'processing' : value.includes('部分') ? 'cyan' : value.includes('专项') || value.includes('基础') ? 'default' : 'warning'

const loadData = async () => {
  loading.value = true
  error.value = ''
  try { data.value = await getAssetCatalog() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '数据资产加载失败' }
  finally { loading.value = false }
}

onMounted(loadData)
</script>
