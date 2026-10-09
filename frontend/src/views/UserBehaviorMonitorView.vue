<template>
  <div class="page-wrap behavior-page">
    <PageHeader eyebrow="PRODUCT ANALYTICS" title="用户行为监控" description="观察页面使用、用户路径、查询质量和有效停留，辅助判断页面是否需要优化">
      <a-tag color="blue">仅管理员可见</a-tag>
    </PageHeader>

    <section class="behavior-filter">
      <div><span>统计期间</span><a-date-picker v-model:value="startDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" /><span>至</span><a-date-picker v-model:value="endDate" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" /></div>
      <a-button type="primary" :loading="loading" @click="load"><SearchOutlined />查询</a-button>
    </section>
    <a-alert v-if="error" class="behavior-alert" type="warning" show-icon :message="error" description="请先执行 docs/sql/user-behavior-telemetry.sql；建表后无需重新发布代码。" />

    <a-spin :spinning="loading" tip="正在读取用户行为数据">
      <div class="behavior-summary-grid">
        <a-card v-for="item in summaryCards" :key="item.label" :bordered="false" class="behavior-summary-card">
          <span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.note }}</small>
        </a-card>
      </div>

      <div class="behavior-chart-grid">
        <a-card :bordered="false" class="panel-card"><template #title>访问趋势</template><template #extra><span class="panel-caption">访问次数与使用人数</span></template>
          <BaseChart v-if="data?.available" :option="trendOption" chart-label="每日页面访问次数和用户数趋势" /><a-empty v-else description="建表并产生访问数据后显示趋势" />
        </a-card>
        <a-card :bordered="false" class="panel-card behavior-quality-card"><template #title>体验判断原则</template>
          <div class="quality-list"><div><b>失败率</b><span>查询失败高，优先排查接口和数据源</span></div><div><b>无数据率</b><span>判断筛选器、默认范围或数据覆盖是否合理</span></div><div><b>快速退出</b><span>10秒内离开且无操作，仅作为体验线索</span></div><div><b>下钻行为</b><span>查看用户能否顺利从汇总定位到明细</span></div></div>
        </a-card>
      </div>

      <a-card :bordered="false" class="panel-card behavior-section"><template #title>页面使用与质量</template><template #extra><span class="panel-caption">按访问次数降序；低使用量不直接等于页面不好用</span></template>
        <a-table :columns="pageColumns" :data-source="data?.pages || []" row-key="pageCode" :pagination="{ pageSize: 20, showSizeChanger: true }" :scroll="{ x: 1180 }" :locale="{ emptyText: '暂无页面访问记录' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'page'"><div class="behavior-page-name"><strong>{{ record.pageTitle }}</strong><code>{{ record.pageCode }}</code></div></template>
            <template v-else-if="column.key === 'active'">{{ duration(record.averageActiveDurationMs) }}</template>
            <template v-else-if="column.key === 'load'"><span :class="{ 'quality-risk': record.averageLoadDurationMs > 3000 }">{{ duration(record.averageLoadDurationMs) }}</span></template>
            <template v-else-if="column.key === 'failure'"><span :class="{ 'quality-risk': record.queryFailureRate >= 5 }">{{ percent(record.queryFailureRate) }}</span></template>
            <template v-else-if="column.key === 'empty'">{{ percent(record.emptyResultRate) }}</template>
          </template>
        </a-table>
      </a-card>

      <div class="behavior-detail-grid">
        <a-card :bordered="false" class="panel-card behavior-section"><template #title>用户主要使用页面</template>
          <a-table :columns="userColumns" :data-source="data?.users || []" row-key="userId" :pagination="{ pageSize: 10 }" :scroll="{ x: 620 }" :locale="{ emptyText: '暂无用户行为记录' }">
            <template #bodyCell="{ column, record }"><template v-if="column.key === 'user'"><div class="behavior-page-name"><strong>{{ record.displayName }}</strong><code>#{{ record.userId }} · {{ record.role }}</code></div></template><template v-else-if="column.key === 'active'">{{ duration(record.activeDurationMs) }}</template><template v-else-if="column.key === 'primary'"><div class="behavior-page-name"><strong>{{ record.primaryPageTitle || '—' }}</strong><code>{{ record.primaryPageCode }}</code></div></template></template>
          </a-table>
        </a-card>
        <a-card :bordered="false" class="panel-card behavior-section"><template #title>常见页面流转</template>
          <a-table :columns="pathColumns" :data-source="data?.paths || []" :row-key="pathKey" :pagination="{ pageSize: 10 }" :locale="{ emptyText: '暂无跨页面访问路径' }">
            <template #bodyCell="{ column, record }"><template v-if="column.key === 'path'"><span class="path-flow"><code>{{ record.fromPageCode }}</code><ArrowRightOutlined /><strong>{{ record.toPageTitle }}</strong></span></template></template>
          </a-table>
        </a-card>
      </div>

      <a-card :bordered="false" class="panel-card behavior-section"><template #title>最近关键行为</template><template #extra><span class="panel-caption">不采集密码、Token、订单号、票号、乘客姓名和具体筛选值</span></template>
        <a-table :columns="eventColumns" :data-source="data?.recentEvents || []" :row-key="eventKey" :pagination="{ pageSize: 15 }" :scroll="{ x: 900 }" :locale="{ emptyText: '暂无关键行为事件' }">
          <template #bodyCell="{ column, record }"><template v-if="column.key === 'event'">{{ eventLabel(record.eventType) }}</template><template v-else-if="column.key === 'status'"><a-tag :color="record.resultStatus === 'failed' ? 'red' : record.resultStatus === 'empty' ? 'orange' : 'green'">{{ statusLabel(record.resultStatus) }}</a-tag></template><template v-else-if="column.key === 'duration'">{{ record.durationMs == null ? '—' : duration(record.durationMs) }}</template></template>
        </a-table>
      </a-card>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { DatePicker as ADatePicker, Empty as AEmpty } from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { ArrowRightOutlined, SearchOutlined } from '@ant-design/icons-vue'
import type { EChartsCoreOption } from 'echarts/core'
import PageHeader from '@/components/PageHeader.vue'
import BaseChart from '@/components/BaseChart.vue'
import { telemetryApi, type TelemetryDashboard } from '@/api/telemetry'

function businessToday() { return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }) }
function daysAgo(day: string, days: number) { return new Date(Date.parse(day) - days * 86400000).toISOString().slice(0, 10) }
const today = businessToday()
const startDate = ref(daysAgo(today, 29))
const endDate = ref(today)
const data = ref<TelemetryDashboard>()
const loading = ref(false)
const error = ref('')
const integer = new Intl.NumberFormat('zh-CN')
const count = (value: number | null | undefined) => integer.format(value || 0)
const percent = (value: number | null | undefined) => `${Number(value || 0).toFixed(2)}%`
function duration(value: number | null | undefined) {
  const milliseconds = Number(value || 0)
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`
  const seconds = milliseconds / 1000
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`
  const minutes = seconds / 60
  if (minutes < 60) return `${minutes.toFixed(1)} 分钟`
  return `${(minutes / 60).toFixed(1)} 小时`
}
const summaryCards = computed(() => {
  const summary = data.value?.summary
  return [
    { label: '页面访问次数', value: count(summary?.visits), note: '一次进入页面计一次' },
    { label: '使用人数', value: count(summary?.users), note: '按登录用户去重' },
    { label: '覆盖页面', value: count(summary?.pages), note: '有实际访问的页面' },
    { label: '平均活跃时长', value: duration(summary?.averageActiveDurationMs), note: '只累计可见活跃时间' },
    { label: '平均加载耗时', value: duration(summary?.averageLoadDurationMs), note: '页面路由切换完成耗时' },
    { label: '查询失败率', value: percent(summary?.queryFailureRate), note: '失败 ÷ 成功与失败查询' },
    { label: '无数据率', value: percent(summary?.emptyResultRate), note: '无结果 ÷ 成功查询' },
  ]
})
const trendOption = computed<EChartsCoreOption>(() => ({
  animation: false, tooltip: { trigger: 'axis' }, legend: { top: 0, left: 0 }, grid: { left: 50, right: 42, top: 48, bottom: 32 },
  xAxis: { type: 'category', data: data.value?.trend.map(item => item.date) || [] },
  yAxis: [{ type: 'value', name: '访问次数' }, { type: 'value', name: '人数' }],
  series: [
    { name: '访问次数', type: 'bar', barMaxWidth: 24, data: data.value?.trend.map(item => item.visits) || [], itemStyle: { color: '#397cf6', borderRadius: [4, 4, 0, 0] } },
    { name: '使用人数', type: 'line', yAxisIndex: 1, data: data.value?.trend.map(item => item.users) || [], itemStyle: { color: '#2f9b78' }, lineStyle: { color: '#2f9b78' } },
  ],
}))
const pageColumns = [
  { title: '页面', key: 'page', width: 210, fixed: 'left' as const }, { title: '访问次数', dataIndex: 'visits', width: 95, sorter: (a: any, b: any) => a.visits - b.visits },
  { title: '使用人数', dataIndex: 'users', width: 90 }, { title: '平均活跃', key: 'active', width: 110 }, { title: '平均加载', key: 'load', width: 100 },
  { title: '有效操作', dataIndex: 'actions', width: 90 }, { title: '快速退出', dataIndex: 'quickExits', width: 90 },
  { title: '查询失败率', key: 'failure', width: 110 }, { title: '无数据率', key: 'empty', width: 100 },
]
const userColumns = [{ title: '用户', key: 'user', width: 150 }, { title: '访问次数', dataIndex: 'visits', width: 90 }, { title: '覆盖页面', dataIndex: 'pageCount', width: 90 }, { title: '活跃时长', key: 'active', width: 110 }, { title: '主要页面', key: 'primary', width: 180 }]
const pathColumns = [{ title: '访问路径', key: 'path' }, { title: '次数', dataIndex: 'visits', width: 80 }]
const eventColumns = [{ title: '时间（北京时间）', dataIndex: 'occurredAt', width: 165 }, { title: '用户', dataIndex: 'displayName', width: 110 }, { title: '页面', dataIndex: 'pageCode', width: 150 }, { title: '事件', key: 'event', width: 105 }, { title: '操作对象', dataIndex: 'elementName', width: 180 }, { title: '结果', key: 'status', width: 85 }, { title: '耗时', key: 'duration', width: 90 }]
const eventLabels: Record<string, string> = { element_click: '点击', filter_apply: '应用筛选', period_change: '时间切换', dimension_change: '维度切换', sort_change: '排序切换', tab_change: 'Tab切换', query_success: '查询成功', query_failed: '查询失败', empty_result: '无数据', drilldown_open: '打开下钻', detail_open: '打开明细', export: '导出', frontend_error: '前端错误' }
const statusLabels: Record<string, string> = { success: '成功', failed: '失败', cancelled: '取消', empty: '无数据', unknown: '记录' }
const eventLabel = (value: string) => eventLabels[value] || value
const statusLabel = (value: string) => statusLabels[value] || value
const pathKey = (record: TelemetryDashboard['paths'][number]) => `${record.fromPageCode}>${record.toPageCode}`
const eventKey = (record: TelemetryDashboard['recentEvents'][number], index: number) => `${record.occurredAt}-${record.userId}-${index}`
async function load() {
  if (!startDate.value || !endDate.value || endDate.value < startDate.value) { error.value = '请选择有效的统计期间。'; return }
  loading.value = true
  error.value = ''
  try { data.value = await telemetryApi.dashboard(startDate.value, endDate.value); error.value = data.value.error }
  catch (failure) { error.value = failure instanceof Error ? failure.message : '用户行为监控加载失败' }
  finally { loading.value = false }
}
onMounted(() => void load())
</script>

<style scoped>
.behavior-page { padding-bottom: 34px; }
.behavior-filter { min-height: 62px; margin-bottom: 14px; padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; gap: 14px; border: 1px solid #e4e9f0; border-radius: 12px; background: #fff; }
.behavior-filter > div { display: flex; align-items: center; gap: 9px; color: #68758a; font-size: 12px; }
.behavior-filter :deep(.ant-picker) { width: 142px; }
.behavior-alert { margin-bottom: 14px; }
.behavior-summary-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 11px; margin-bottom: 14px; }
.behavior-summary-card { border: 1px solid #e7ebf1; box-shadow: 0 5px 18px rgba(28,45,72,.035); }
.behavior-summary-card :deep(.ant-card-body) { padding: 16px; }
.behavior-summary-card span, .behavior-summary-card small { display: block; color: #7b8798; font-size: 10px; }
.behavior-summary-card strong { display: block; margin: 10px 0 7px; color: #253249; font-size: 20px; white-space: nowrap; }
.behavior-chart-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(280px, .6fr); gap: 14px; margin-bottom: 14px; }
.behavior-chart-grid .base-chart { height: 280px; }
.behavior-quality-card { border: 1px solid #e7ebf1; }
.quality-list { display: grid; gap: 0; }
.quality-list div { padding: 13px 0; display: grid; gap: 4px; border-bottom: 1px solid #edf0f4; }
.quality-list div:last-child { border-bottom: 0; }
.quality-list b { color: #3b4960; font-size: 12px; }
.quality-list span { color: #7f8b9c; font-size: 11px; line-height: 1.5; }
.behavior-section { margin-bottom: 14px; }
.behavior-section :deep(.ant-table-cell) { padding: 12px 10px; font-size: 11px; }
.behavior-detail-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 14px; }
.behavior-page-name { display: grid; gap: 3px; }
.behavior-page-name strong { color: #344258; font-size: 12px; }
.behavior-page-name code, .path-flow code { color: #8390a2; font-size: 10px; }
.path-flow { display: flex; align-items: center; gap: 7px; }
.path-flow strong { color: #41516a; font-size: 11px; }
.quality-risk { color: #c44f5e; font-weight: 600; }
@media (max-width: 1250px) { .behavior-summary-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (max-width: 900px) { .behavior-chart-grid, .behavior-detail-grid { grid-template-columns: 1fr; } .behavior-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .behavior-filter, .behavior-filter > div { align-items: stretch; flex-direction: column; } .behavior-filter :deep(.ant-picker) { width: 100%; } .behavior-summary-grid { grid-template-columns: 1fr; } }
</style>
