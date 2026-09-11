<template>
  <div class="page-wrap">
    <PageHeader eyebrow="MANAGEMENT OVERVIEW" title="经营总览" description="从经营结果出发，逐层定位利润、履约和风险问题">
      <a-button><DownloadOutlined />导出当前视图</a-button>
    </PageHeader>

    <DataStateBar
      :label="overview?.status.label ?? '正在检查数据状态'"
      message="所有数值均为界面演示，不代表公司真实经营结果"
      :freshness="overview?.status.freshness ?? '检查中'"
      :metric-state="overview?.status.metricState ?? '检查中'"
    />
    <FilterBar />

    <a-spin :spinning="loading">
      <a-alert v-if="error" type="error" show-icon :message="error" class="section-gap" />
      <template v-if="overview">
        <div class="kpi-grid">
          <KpiCard v-for="item in overview.kpis" :key="item.key" :item="item" />
        </div>

        <div class="dashboard-grid main-grid">
          <a-card class="panel-card" :bordered="false" title="订单与出票趋势">
            <template #extra><span class="panel-caption">演示数据 · 最近7天</span></template>
            <BaseChart :option="trendOption" chart-label="最近七天订单量与出票量趋势图" />
          </a-card>
          <a-card class="panel-card" :bordered="false" title="业务链路数据覆盖">
            <template #extra><router-link to="/assets">查看资产</router-link></template>
            <BaseChart :option="lifecycleOption" chart-label="各业务环节数据覆盖度图" />
          </a-card>
        </div>

        <a-card class="panel-card focus-card" :bordered="false" title="本期重点关注">
          <template #extra><router-link to="/issues">进入异常工作台</router-link></template>
          <a-list :data-source="overview.focus">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta :description="item.type">
                  <template #title><span class="focus-title"><a-tag :color="item.level === 'P0' ? 'error' : 'warning'">{{ item.level }}</a-tag>{{ item.title }}</span></template>
                </a-list-item-meta>
                <router-link :to="item.action.includes('数据') ? '/assets' : '/issues'">{{ item.action }} <RightOutlined /></router-link>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </template>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import { DownloadOutlined, RightOutlined } from '@ant-design/icons-vue'
import { getOverview, type OverviewData } from '@/api/dashboard'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import FilterBar from '@/components/FilterBar.vue'
import KpiCard from '@/components/KpiCard.vue'
import BaseChart from '@/components/BaseChart.vue'

const overview = ref<OverviewData>()
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try { overview.value = await getOverview() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '数据加载失败' }
  finally { loading.value = false }
})

const trendOption = computed<EChartsCoreOption>(() => ({
  color: ['#3178f6', '#55b6a9'],
  tooltip: { trigger: 'axis' },
  legend: { data: ['订单量', '出票量'], top: 0, right: 0 },
  grid: { left: 44, right: 18, top: 45, bottom: 28 },
  xAxis: { type: 'category', boundaryGap: false, data: overview.value?.trend.dates ?? [], axisLine: { lineStyle: { color: '#d7deea' } } },
  yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf0f5' } } },
  series: [
    { name: '订单量', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7, areaStyle: { opacity: 0.08 }, data: overview.value?.trend.orders ?? [] },
    { name: '出票量', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7, data: overview.value?.trend.tickets ?? [] },
  ],
}))

const lifecycleOption = computed<EChartsCoreOption>(() => ({
  color: ['#3178f6'],
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}<br/>数据覆盖（演示）：{c}%' },
  grid: { left: 82, right: 28, top: 16, bottom: 24 },
  xAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: '#edf0f5' } }, axisLabel: { formatter: '{value}%' } },
  yAxis: { type: 'category', data: overview.value?.lifecycle.map(item => item.stage).reverse() ?? [], axisTick: { show: false }, axisLine: { show: false } },
  series: [{ type: 'bar', barWidth: 12, data: overview.value?.lifecycle.map(item => item.value).reverse() ?? [], itemStyle: { borderRadius: 8 }, showBackground: true, backgroundStyle: { color: '#edf1f7', borderRadius: 8 } }],
}))
</script>
