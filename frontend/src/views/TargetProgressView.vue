<template>
  <div class="page-wrap target-progress-page">
    <PageHeader eyebrow="TARGET PERFORMANCE" title="目标进度" description="按月份集中查看全部平台、GDS与政策员目标的实时完成、利润和趋势；本页只读。">
      <a-space>
        <a-button @click="definitionDrawerOpen = true"><QuestionCircleOutlined />指标口径</a-button>
        <a-button @click="router.push('/business-configuration/targets')"><SettingOutlined />目标配置</a-button>
        <a-tooltip v-if="canManageTargets" :title="refreshButtonTip">
          <a-button :loading="refreshRunning" :disabled="!refreshStatus.canTrigger && !refreshRunning" @click="triggerImmediateRefresh">
            <ReloadOutlined />{{ refreshRunning ? '正在更新' : '立即更新' }}
          </a-button>
        </a-tooltip>
        <a-button type="primary" :loading="loading" @click="load"><ReloadOutlined />刷新数据</a-button>
      </a-space>
    </PageHeader>

    <a-alert v-if="loadError" class="state-alert" type="error" show-icon :message="loadError" description="页面不会用演示数据兜底，请检查接口与数据库。" />
    <a-alert
      v-else-if="!availability.hasEtlData"
      class="state-alert"
      type="warning"
      show-icon
      message="部分经营指标待ETL产出"
      :description="availability.message"
    />
    <a-alert
      v-if="refreshStatus.status === 'FAILED'"
      class="state-alert"
      type="error"
      show-icon
      message="最近一次立即更新失败"
      :description="refreshStatus.errorMessage || '请稍后重试或检查目标ETL日志。'"
    />

    <section class="progress-hero">
      <div class="hero-title">
        <span>{{ periodLabel }}</span>
        <h2>{{ sceneMeta.title }}月度进度</h2>
        <p>{{ dataCoverageText }} · 空值表示尚未产出，不代表0</p>
      </div>
      <div class="hero-cards">
        <article><span>{{ sceneMeta.scopeLabel }}</span><strong>{{ summary.scopeCount }}</strong><small>已配置 {{ summary.configuredCount }} · 当前显示 {{ summary.visibleCount }}</small></article>
        <article><span>目标 / 截至当前</span><strong>{{ number(summary.target) }} / {{ nullable(summary.actual) }}</strong><small>当前完成率 {{ percentNullable(summary.completionRate) }}</small></article>
        <article><span>累计出票利润</span><strong>{{ money(summary.profit) }}</strong><small>业务估算口径</small></article>
        <article :class="summary.progressGapRate != null && summary.progressGapRate < 0 ? 'behind' : ''"><span>当前进度差</span><strong>{{ percentSigned(summary.progressGapRate) }}</strong><small>正常进度 {{ percentNullable(summary.expectedRate) }}</small></article>
      </div>
    </section>

    <a-card class="progress-workspace" :bordered="false">
      <div class="toolbar">
        <div class="toolbar-left">
          <a-select v-model:value="selectedPeriod" class="period-select" :options="periodOptions" />
          <a-input-search v-model:value="keyword" class="keyword-input" allow-clear placeholder="搜索平台、GDS、政策员、部门或责任人" />
          <a-checkbox v-if="activeScene === 'platform'" v-model:checked="includeUnconfigured">显示未配置平台</a-checkbox>
        </div>
        <span>共 {{ summary.visibleCount }} 行 · {{ summary.progressReadyCount }} 行已有进度</span>
      </div>

      <a-tabs v-model:activeKey="activeScene" class="scene-tabs">
        <a-tab-pane v-for="(meta, key) in sceneMetas" :key="key">
          <template #tab><span class="tab-label"><component :is="meta.icon" />{{ meta.title }}</span></template>
        </a-tab-pane>
      </a-tabs>

      <div class="scene-note">
        <div><strong>当前考核口径：{{ sceneMeta.criterion }}</strong><span>{{ sceneMeta.description }}</span></div>
        <a-space>
          <a-tag v-if="refreshStatus.status !== 'IDLE'" :color="refreshStatusColor">{{ refreshStatusLabel }}</a-tag>
          <a-tag v-if="activeScene === 'platform'" color="blue">当前显示 {{ summary.visibleCount }} / {{ summary.scopeCount }} 个有效平台</a-tag>
          <a-tag v-else>当前展示已配置目标</a-tag>
        </a-space>
      </div>

      <a-table
        class="progress-table"
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        :pagination="{ pageSize: 20, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'], showTotal: (total: number) => `共 ${total} 条` }"
        :row-key="(row: TargetProgressRow) => row.id"
        :scroll="{ x: tableWidth, y: 560 }"
        size="small"
      >
        <template #emptyText><a-empty description="当前筛选条件下没有真实数据" /></template>
        <template #headerCell="{ column }">
          <a-tooltip v-if="column.definition" :title="column.definition">
            <span class="column-title">{{ column.title }}<QuestionCircleOutlined /></span>
          </a-tooltip>
          <span v-else>{{ column.title }}</span>
        </template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'scope'">
            <div class="scope-cell">
              <span class="scope-mark" :class="`scope-${activeScene}`">{{ scopeMark(record) }}</span>
              <div><strong>{{ scopeName(record) }}</strong><small>{{ scopeSubline(record) }}</small></div>
            </div>
          </template>
          <template v-else-if="column.key === 'owner'">
            <div class="owner-cell">
              <strong>{{ record.owner || '未配置责任人' }}</strong>
              <small>{{ record.department || '未配置归属部门' }}</small>
              <a-tag v-if="record.owner" :color="record.wechatConfigured ? 'green' : 'orange'">{{ record.wechatConfigured ? '企微可通知' : '未配置企微' }}</a-tag>
            </div>
          </template>
          <template v-else-if="column.key === 'target'">
            <strong v-if="record.configured">{{ number(record.target) }}</strong><a-tag v-else color="default">未配置</a-tag>
          </template>
          <template v-else-if="column.key === 'actualThroughYesterday'"><MetricValue :value="record.actualThroughYesterday" /></template>
          <template v-else-if="column.key === 'todayActual'"><MetricValue :value="record.todayActual" /></template>
          <template v-else-if="column.key === 'actual'"><MetricValue :value="record.actual" /></template>
          <template v-else-if="column.key === 'completion'">
            <template v-if="record.completionRate != null">
              <a-progress :percent="progressPercent(record.completionRate)" size="small" :status="record.progressGapRate != null && record.progressGapRate < 0 ? 'exception' : 'normal'" />
              <small>{{ percentNullable(record.completionRate) }}</small>
            </template><span v-else class="pending">待ETL</span>
          </template>
          <template v-else-if="column.key === 'expected'"><RateValue :value="record.expectedRate" /></template>
          <template v-else-if="column.key === 'gap'"><RateValue :value="record.progressGapRate" signed /></template>
          <template v-else-if="column.key === 'todayRequired'"><MetricValue :value="record.todayRequired" :decimals="1" /></template>
          <template v-else-if="column.key === 'todayRemaining'"><MetricValue :value="record.todayRemaining" :decimals="1" /></template>
          <template v-else-if="String(column.key).startsWith('policyGds')">
            <div v-if="policyGdsMeasure(record, String(column.key).replace('policyGds', ''))" class="gds-measure-cell">
              <strong>{{ nullable(policyGdsMeasure(record, String(column.key).replace('policyGds', ''))?.actual) }}</strong>
              <small>目标 {{ number(policyGdsMeasure(record, String(column.key).replace('policyGds', ''))?.target || 0) }}</small>
            </div>
            <span v-else class="pending">未配置</span>
          </template>
          <template v-else-if="column.key === 'remaining'"><MetricValue :value="record.remaining" /></template>
          <template v-else-if="column.key === 'requiredDaily'"><MetricValue :value="record.requiredDaily" :decimals="1" /></template>
          <template v-else-if="column.key === 'profit'"><MoneyValue :value="record.profit" /></template>
          <template v-else-if="column.key === 'profitPerSegment'"><MoneyValue :value="record.profitPerSegment" :decimals="2" /></template>
          <template v-else-if="column.key === 'yesterdayProfit'"><MoneyValue :value="record.yesterdayProfit" /></template>
          <template v-else-if="column.key === 'yesterdayProfitPerSegment'"><MoneyValue :value="record.yesterdayProfitPerSegment" :decimals="2" /></template>
          <template v-else-if="column.key === 'yesterday'"><MetricValue :value="record.yesterday" /></template>
          <template v-else-if="column.key === 'dayBefore'"><MetricValue :value="record.dayBefore" /></template>
          <template v-else-if="column.key === 'dayOverDayRate'"><RateValue :value="record.dayOverDayRate" signed /></template>
          <template v-else-if="column.key === 'dataStatus'">
            <a-tag :color="record.dataStatus === 'READY' ? 'green' : record.dataStatus === 'PARTIAL' ? 'orange' : 'default'">{{ dataStatus(record.dataStatus) }}</a-tag>
            <small class="through-date">{{ record.dataThroughDate || '--' }}</small>
          </template>
        </template>
      </a-table>
      <p class="realtime-note">截至昨日为稳定数据；今日数据为实时统计，可能因退票或数据同步继续变化。</p>
    </a-card>

    <a-drawer v-model:open="definitionDrawerOpen" title="目标进度指标口径" width="620">
      <a-alert type="info" show-icon message="数据时点说明" description="截至昨日为稳定数据；今日实时数据可能继续变化。空值表示ETL尚未产出，不代表0。" />
      <div class="definition-list">
        <article v-for="item in metricDefinitions" :key="item.name">
          <strong>{{ item.name }}</strong>
          <p>{{ item.description }}</p>
          <code v-if="item.formula">{{ item.formula }}</code>
        </article>
      </div>
      <a-divider />
      <div class="scene-definition">
        <strong>场景完成量口径</strong>
        <p><b>平台完成量：</b>有效出票对应的总承运航段数，不区分是否有奖。</p>
        <p><b>GDS完成量：</b><code>reward_flag=1</code>、非婴儿，并且属于有效承运航段，即有奖航段数；按平台归属到责任人。</p>
        <p><b>政策员完成量：</b>完全沿用 <code>erp_daily_data.py</code>，按政策组组长的 <code>order_info.policy_operator</code> 归属，分别汇总1A、1G、1E、1S的 <code>reward_trip_count</code>，四项相加作为政策组考核完成量。</p>
        <p><b>政策员利润：</b>沿用同一脚本，汇总组长名下全部有效出票的预估利润；单段利润以全部有效出票的 <code>trip_count</code> 总航段为分母，不以有奖航段为分母。</p>
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref, watch, type PropType } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { BranchesOutlined, QuestionCircleOutlined, ReloadOutlined, SettingOutlined, ShopOutlined, TeamOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import {
  fetchTargetProgress,
  fetchTargetProgressRefreshStatus,
  triggerTargetProgressRefresh,
  type TargetEtlRefreshStatus,
  type TargetProgressResult,
  type TargetProgressRow,
  type TargetScene,
} from '@/api/targetManagement'
import { useAuthStore } from '@/stores/auth'

const MetricValue = defineComponent({
  props: { value: { type: Number as PropType<number | null>, default: null }, decimals: { type: Number, default: 0 } },
  setup: props => () => props.value == null ? h('span', { class: 'pending' }, '待ETL') : h('strong', Number(props.value).toLocaleString('zh-CN', { minimumFractionDigits: props.decimals, maximumFractionDigits: props.decimals })),
})
const MoneyValue = defineComponent({
  props: { value: { type: Number as PropType<number | null>, default: null }, decimals: { type: Number, default: 0 } },
  setup: props => () => props.value == null ? h('span', { class: 'pending' }, '待ETL') : h('strong', `¥${Number(props.value).toLocaleString('zh-CN', { minimumFractionDigits: props.decimals, maximumFractionDigits: props.decimals })}`),
})
const RateValue = defineComponent({
  props: { value: { type: Number as PropType<number | null>, default: null }, signed: Boolean },
  setup: props => () => props.value == null ? h('span', { class: 'pending' }, '待ETL') : h('strong', { class: props.signed ? (props.value < 0 ? 'negative' : 'positive') : '' }, `${props.signed && props.value > 0 ? '+' : ''}${(props.value * 100).toFixed(1)}%`),
})

type SceneKey = 'platform' | 'gds' | 'policy'
const router = useRouter()
const authStore = useAuthStore()
const today = new Date()
const currentPeriod = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
const sceneApi: Record<SceneKey, TargetScene> = { platform: 'PLATFORM', gds: 'GDS', policy: 'POLICY' }
const sceneMetas = {
  platform: { title: '平台目标', scopeLabel: '有效平台总数', criterion: '有效出票承运总航段', description: '已出票、非作废且 airlift_flag=1 的全部承运航段，不限是否有奖。', icon: ShopOutlined },
  gds: { title: 'GDS目标', scopeLabel: 'GDS目标数', criterion: '有奖有效承运航段', description: 'reward_flag=1、包含非婴儿乘客且 airlift_flag=1，并按平台归属到责任人。', icon: BranchesOutlined },
  policy: { title: '政策员目标', scopeLabel: '政策目标数', criterion: '政策员有奖航段', description: '完全沿用 erp_daily_data.py：按组长 policy_operator 汇总 reward_trip_count，并分1A、1G、1E、1S展示。', icon: TeamOutlined },
} as const
const activeScene = ref<SceneKey>('platform')
const selectedPeriod = ref(currentPeriod)
const keyword = ref('')
const includeUnconfigured = ref(false)
const definitionDrawerOpen = ref(false)
const loading = ref(false)
const loadError = ref('')
const rows = ref<TargetProgressRow[]>([])
const emptySummary: TargetProgressResult['summary'] = {
  scopeCount: 0, visibleCount: 0, configuredCount: 0, progressReadyCount: 0,
  target: 0, actual: null, completionRate: null, actualThroughYesterday: null,
  todayActual: null, todayRequired: null, todayRemaining: null, expectedRate: null,
  progressGapRate: null, remaining: null, requiredDaily: null, profit: null, lossAmount: null,
}
const summary = ref<TargetProgressResult['summary']>({ ...emptySummary })
const availability = ref<TargetProgressResult['metricAvailability']>({ hasEtlData: false, lossMetricsReady: false, message: '完成量和利润指标尚未由ETL写入，当前显示为待ETL。' })
const dataThroughDate = ref<string | null>(null)
const dataUpdatedAt = ref<string | null>(null)
const refreshStatus = ref<TargetEtlRefreshStatus>({
  id: null, status: 'IDLE', triggerType: null, requestedBy: '', requestedAt: null,
  startedAt: null, finishedAt: null, dataThroughDate: null, processedDates: 0,
  dwsRows: 0, adsRows: 0, errorMessage: '', canTrigger: true, retryAfterSeconds: 0,
})
const triggeredRunId = ref<number | null>(null)
const sceneMeta = computed(() => sceneMetas[activeScene.value])
const canManageTargets = computed(() => Boolean(
  authStore.user?.isAdmin || authStore.user?.permissions?.includes('business_config.targets.manage'),
))
const refreshRunning = computed(() => ['QUEUED', 'RUNNING'].includes(refreshStatus.value.status))
const refreshStatusColor = computed(() => ({ IDLE: 'default', QUEUED: 'blue', RUNNING: 'processing', SUCCEEDED: 'green', FAILED: 'red' }[refreshStatus.value.status]))
const refreshStatusLabel = computed(() => ({
  IDLE: '',
  QUEUED: '立即更新：排队中', RUNNING: '立即更新：计算中',
  SUCCEEDED: `最近更新成功 · ${refreshStatus.value.processedDates} 个业务日`,
  FAILED: '最近更新失败',
}[refreshStatus.value.status] || ''))
const refreshButtonTip = computed(() => {
  if (refreshRunning.value) return '目标ETL正在后台计算，完成后页面会自动刷新'
  if (refreshStatus.value.retryAfterSeconds > 0) return `为保护数据库，请 ${refreshStatus.value.retryAfterSeconds} 秒后再试`
  return '后台补算新增或修改目标，并刷新截至今天的真实进度'
})
const periodLabel = computed(() => `${selectedPeriod.value.slice(0, 4)}年${Number(selectedPeriod.value.slice(5))}月`)
const dataCoverageText = computed(() => {
  if (!dataUpdatedAt.value) return '当前尚无ETL进度快照'
  const todayText = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  const coverage = dataThroughDate.value === todayText ? '已纳入今日实时数据' : dataThroughDate.value ? `数据截至 ${dataThroughDate.value}` : '数据日期待确认'
  return `更新于 ${formatTime(dataUpdatedAt.value)} · ${coverage}`
})
const periodOptions = computed(() => Array.from({ length: 25 }, (_, index) => {
  const date = new Date(today.getFullYear(), today.getMonth() + 3 - index, 1)
  const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
  return { value, label: `${date.getFullYear()}年${date.getMonth() + 1}月` }
}))
const completionBasis = computed(() => sceneMeta.value.criterion)
const metricDefinitions = computed(() => {
  const policyProfit = activeScene.value === 'policy'
  return [
    { name: '月度目标', description: `当前行本月配置的目标考核航段数；当前口径为“${completionBasis.value}”。` },
    { name: '截至昨日', description: `从当月1日至昨天23:59:59累计完成的考核航段数，不包含今天；当前口径为“${completionBasis.value}”。` },
    { name: '今日实时', description: '今天00:00至页面数据更新时间累计完成的考核航段数，可能因出票、退票、状态变化或同步延迟继续变化。' },
    { name: '截至当前', description: '当月1日至页面数据更新时间累计完成的考核航段数。', formula: '截至昨日 + 今日实时' },
    { name: '当前完成率', description: '截至当前完成量占月度目标的比例。', formula: '截至当前 ÷ 月度目标' },
    { name: '正常进度', description: '按本月自然日均匀分配目标，截至今天理论上应该达到的月度目标比例。', formula: '本月已过天数（含今天）÷ 本月总天数' },
    { name: '进度差', description: '实际完成进度与正常进度的差值，正数表示超前，负数表示落后。', formula: '当前完成率 − 正常进度' },
    { name: '今日需完成', description: '为了在今天结束时达到正常进度，今天理论上需要完成的考核航段数。', formula: 'max(月度目标 × 正常进度 − 截至昨日, 0)' },
    { name: '今日尚需', description: '扣除今日已经实时完成的考核航段后，今天还需要完成的数量。', formula: 'max(今日需完成 − 今日实时, 0)' },
    { name: '月度剩余', description: '距离完成整个月度目标还差的考核航段数，超额完成后显示0。', formula: 'max(月度目标 − 截至当前, 0)' },
    { name: '后续日均需完成', description: '从明天开始到本月最后一天，为完成月度目标，平均每天还需要完成的考核航段数。', formula: '月度剩余 ÷ 本月剩余自然日数（不含今天）' },
    { name: '累计利润', description: policyProfit ? '沿用 erp_daily_data.py：当月截至当前，组长名下全部有效出票的预估利润合计，不限定 reward_trip_count>0；属于业务估算，不是财务结算利润。' : '当月截至当前，符合当前考核口径的出票预估利润合计；属于业务估算，不是财务结算利润。' },
    { name: '单段利润', description: policyProfit ? '沿用 erp_daily_data.py：累计预估利润除以组长名下全部有效出票的 trip_count 总航段，不以有奖航段为分母。' : '平均每个考核航段产生的出票预估利润。', formula: policyProfit ? '累计利润 ÷ 有效出票 trip_count 总航段' : '累计利润 ÷ 截至当前' },
    { name: '昨日利润', description: policyProfit ? '昨天00:00至23:59:59，组长名下全部有效出票的预估利润。' : '昨天00:00至23:59:59，符合当前考核口径的出票预估利润。' },
    { name: '昨日单段', description: policyProfit ? '沿用 erp_daily_data.py：昨日预估利润除以昨日有效出票的 trip_count 总航段。' : '昨天平均每个考核航段产生的出票预估利润。', formula: policyProfit ? '昨日利润 ÷ 昨日有效出票 trip_count 总航段' : '昨日利润 ÷ 昨日航段' },
    { name: '昨日航段', description: `昨天00:00至23:59:59完成的考核航段数；当前口径为“${completionBasis.value}”。` },
    { name: '前日航段', description: '前天00:00至23:59:59完成的考核航段数。' },
    { name: '环比', description: '昨日航段相对于前日航段的增减比例。', formula: '(昨日航段 − 前日航段) ÷ 前日航段' },
    { name: '数据状态', description: '已就绪表示对应日期和指标已有完整ETL数据；部分就绪表示数据不完整；待ETL表示尚未产出，不能理解为0。日期为当前行最新成功产出的业务日期。' },
  ]
})
function definition(index: number) {
  const item = metricDefinitions.value[index]
  return `${item.description}${item.formula ? ` 公式：${item.formula}` : ''}`
}
const coreColumns = computed(() => [
  { title: '月度目标', key: 'target', width: 95, align: 'right' as const, definition: definition(0) },
  { title: '截至昨日', key: 'actualThroughYesterday', width: 105, align: 'right' as const, definition: definition(1) },
  { title: '今日实时', key: 'todayActual', width: 95, align: 'right' as const, definition: definition(2) },
  { title: '截至当前', key: 'actual', width: 105, align: 'right' as const, definition: definition(3) },
  { title: '当前完成率', key: 'completion', width: 155, definition: definition(4) },
  { title: '正常进度', key: 'expected', width: 95, align: 'right' as const, definition: definition(5) },
  { title: '进度差', key: 'gap', width: 90, align: 'right' as const, definition: definition(6) },
  { title: '今日需完成', key: 'todayRequired', width: 105, align: 'right' as const, definition: definition(7) },
  { title: '今日尚需', key: 'todayRemaining', width: 100, align: 'right' as const, definition: definition(8) },
  { title: '月度剩余', key: 'remaining', width: 95, align: 'right' as const, definition: definition(9) },
  { title: '后续日均需完成', key: 'requiredDaily', width: 125, align: 'right' as const, definition: definition(10) },
])
const columns = computed(() => [
  { title: activeScene.value === 'platform' ? '平台' : activeScene.value === 'gds' ? 'GDS' : '政策员 / 政策组', key: 'scope', width: 205, fixed: 'left' as const },
  { title: '责任归属', key: 'owner', width: 175 },
  { title: '目标进度', children: coreColumns.value },
  ...(activeScene.value === 'policy' ? [{ title: '截至当前各GDS完成量（reward_trip_count）', children: ['1G', '1A', '1E', '1S'].map(code => ({
    title: code, key: `policyGds${code}`, width: 105, align: 'right' as const,
    definition: `${code}有奖航段完成量；单元格下方显示该GDS月度目标。`,
  })) }] : []),
  { title: '利润表现', children: [
    { title: '累计利润', key: 'profit', width: 110, align: 'right' as const, definition: definition(11) },
    { title: '单段利润', key: 'profitPerSegment', width: 100, align: 'right' as const, definition: definition(12) },
    { title: '昨日利润', key: 'yesterdayProfit', width: 105, align: 'right' as const, definition: definition(13) },
    { title: '昨日单段', key: 'yesterdayProfitPerSegment', width: 100, align: 'right' as const, definition: definition(14) },
  ] },
  { title: '近期趋势', children: [
    { title: '昨日航段', key: 'yesterday', width: 90, align: 'right' as const, definition: definition(15) }, { title: '前日航段', key: 'dayBefore', width: 90, align: 'right' as const, definition: definition(16) },
    { title: '环比', key: 'dayOverDayRate', width: 85, align: 'right' as const, definition: definition(17) },
  ] },
  { title: '数据状态', key: 'dataStatus', width: 115, fixed: 'right' as const, definition: definition(18) },
])
const tableWidth = computed(() => activeScene.value === 'platform' ? 2670 : activeScene.value === 'policy' ? 3040 : 2620)

let keywordTimer: ReturnType<typeof setTimeout> | undefined
async function load() {
  loading.value = true; loadError.value = ''
  try {
    const result = await fetchTargetProgress({
      scene: sceneApi[activeScene.value],
      period: selectedPeriod.value,
      keyword: keyword.value.trim(),
      includeUnconfigured: activeScene.value === 'platform' ? includeUnconfigured.value : undefined,
    })
    rows.value = result.rows; summary.value = result.summary; availability.value = result.metricAvailability; dataThroughDate.value = result.dataThroughDate ?? null; dataUpdatedAt.value = result.dataUpdatedAt ?? null
  } catch (error) {
    rows.value = []; summary.value = { ...emptySummary }
    availability.value = { hasEtlData: false, lossMetricsReady: false, message: '未读取到真实ETL数据。' }; dataThroughDate.value = null; dataUpdatedAt.value = null
    loadError.value = error instanceof Error ? error.message : '目标进度加载失败'
  } finally { loading.value = false }
}
function scopeName(row: TargetProgressRow) { return row.scene === 'platform' ? row.platform || row.platformCode : row.scene === 'gds' ? row.gds || '未命名GDS' : row.policy || '未命名政策组' }
function scopeSubline(row: TargetProgressRow) { return row.scene === 'platform' ? `${row.platformCode}${row.platformFullName && row.platformFullName !== row.platform ? ` · ${row.platformFullName}` : ''}` : `${row.metric} · ${row.metricCode}` }
function scopeMark(row: TargetProgressRow) { return row.scene === 'platform' ? (row.platform || row.platformCode || '平').slice(0, 1) : row.scene === 'gds' ? row.gds || 'G' : '策' }
function policyGdsMeasure(row: TargetProgressRow, code: string) { return row.gdsBreakdown?.[code] }
function number(value: number) { return Math.round(Number(value)).toLocaleString('zh-CN') }
function nullable(value: number | null | undefined) { return value == null ? '待ETL' : number(value) }
function money(value: number | null | undefined) { return value == null ? '待ETL' : `¥${Math.round(Number(value)).toLocaleString('zh-CN')}` }
function percentNullable(value: number | null | undefined) { return value == null ? '待ETL' : `${(Number(value) * 100).toFixed(1)}%` }
function percentSigned(value: number | null | undefined) { return value == null ? '待ETL' : `${value > 0 ? '+' : ''}${(Number(value) * 100).toFixed(1)}%` }
function progressPercent(value: number) { return Math.max(0, Math.min(100, Number((value * 100).toFixed(1)))) }
function dataStatus(value: string) { return ({ READY: '已产出', PARTIAL: '部分产出', MISSING: '数据缺失', PENDING_ETL: '待ETL' } as Record<string, string>)[value] ?? value }
function formatTime(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false }) }

let refreshStatusTimer: ReturnType<typeof setTimeout> | undefined
function scheduleRefreshStatus() {
  if (refreshStatusTimer) clearTimeout(refreshStatusTimer)
  const delay = refreshRunning.value ? 3_000 : refreshStatus.value.retryAfterSeconds > 0 ? Math.min(5_000, refreshStatus.value.retryAfterSeconds * 1_000) : 0
  if (delay) refreshStatusTimer = setTimeout(() => void loadRefreshStatus(), delay)
}
async function loadRefreshStatus() {
  try {
    const result = await fetchTargetProgressRefreshStatus()
    refreshStatus.value = result
    if (triggeredRunId.value === result.id && ['SUCCEEDED', 'FAILED'].includes(result.status)) {
      if (result.status === 'SUCCEEDED') {
        message.success(`目标进度已更新：处理 ${result.processedDates} 个业务日`)
        await load()
      } else {
        message.error(result.errorMessage || '目标进度立即更新失败')
      }
      triggeredRunId.value = null
    }
    scheduleRefreshStatus()
  } catch (error) {
    if (triggeredRunId.value != null) message.error(error instanceof Error ? error.message : '立即更新状态读取失败')
    if (refreshStatusTimer) clearTimeout(refreshStatusTimer)
  }
}
async function triggerImmediateRefresh() {
  try {
    const result = await triggerTargetProgressRefresh()
    refreshStatus.value = result
    triggeredRunId.value = result.id
    message.success('立即更新任务已提交，完成后页面会自动刷新')
    scheduleRefreshStatus()
  } catch (error) {
    message.error(error instanceof Error ? error.message : '立即更新提交失败')
    await loadRefreshStatus()
  }
}

watch([activeScene, selectedPeriod], () => { void load() })
watch(includeUnconfigured, () => { if (activeScene.value === 'platform') void load() })
watch(keyword, () => { if (keywordTimer) clearTimeout(keywordTimer); keywordTimer = setTimeout(() => void load(), 350) })
let refreshTimer: ReturnType<typeof setInterval> | undefined
function refreshWhenVisible() { if (document.visibilityState === 'visible') void load() }
onMounted(() => {
  void load()
  void loadRefreshStatus()
  refreshTimer = setInterval(refreshWhenVisible, 60_000)
  document.addEventListener('visibilitychange', refreshWhenVisible)
})
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (keywordTimer) clearTimeout(keywordTimer)
  if (refreshStatusTimer) clearTimeout(refreshStatusTimer)
  document.removeEventListener('visibilitychange', refreshWhenVisible)
})
</script>

<style scoped>
.state-alert{margin-bottom:14px}.progress-hero{min-height:176px;margin-bottom:16px;padding:25px 27px;display:grid;grid-template-columns:minmax(260px,.65fr) minmax(680px,1.35fr);align-items:center;gap:24px;border-radius:16px;color:#fff;background:linear-gradient(128deg,#122a48,#1d518c 58%,#3b83d7);box-shadow:0 14px 34px rgba(31,79,141,.17)}.hero-title>span{color:#9dc8f7;font-size:11px;font-weight:700;letter-spacing:.08em}.hero-title h2{margin:7px 0 8px;color:#fff;font-size:25px}.hero-title p{margin:0;color:#c9daef;font-size:11px;line-height:1.65}.hero-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.hero-cards article{min-height:104px;padding:15px;display:flex;flex-direction:column;border:1px solid rgba(255,255,255,.14);border-radius:11px;background:rgba(255,255,255,.08)}.hero-cards span,.hero-cards small{color:#c5d6ec;font-size:10px}.hero-cards strong{margin:9px 0 6px;color:#fff;font-size:20px;white-space:nowrap}.hero-cards .behind strong{color:#ffd6d6}.progress-workspace{border-radius:14px}.progress-workspace :deep(.ant-card-body){padding:0 18px 18px}.toolbar{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid #edf0f4}.toolbar-left,.tab-label{display:flex;align-items:center;gap:9px}.toolbar>span{color:#8793a4;font-size:11px}.period-select{width:150px}.keyword-input{width:320px}.scene-tabs{margin-top:8px}.scene-tabs :deep(.ant-tabs-nav){margin-bottom:10px}.scene-note{min-height:58px;margin-bottom:12px;padding:11px 14px;display:flex;align-items:center;justify-content:space-between;gap:14px;border:1px solid #dbe7f8;border-radius:10px;background:#f5f8fd}.scene-note>div{display:grid;gap:3px}.scene-note strong{color:#33445b;font-size:12px}.scene-note span{color:#768398;font-size:11px}.progress-table :deep(.ant-table-thead>tr>th){color:#5f6e82;background:#f7f9fc;font-size:10px;text-align:center}.progress-table :deep(.ant-table-tbody>tr>td){padding-top:11px;padding-bottom:11px;font-size:11px}.column-title{display:inline-flex;align-items:center;justify-content:center;gap:4px;cursor:help}.column-title :deep(svg){color:#8da0b8}.scope-cell{display:flex;align-items:center;gap:9px}.scope-mark{width:35px;height:35px;flex:none;display:grid;place-items:center;border-radius:9px;color:#2766c2;background:#edf4ff;font-weight:700}.scope-gds{color:#087a72;background:#e7f8f4}.scope-policy{color:#7753b9;background:#f2eefb}.scope-cell>div,.owner-cell{min-width:0;display:grid;gap:3px}.scope-cell strong,.owner-cell strong{overflow:hidden;color:#344258;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.scope-cell small,.owner-cell small,.through-date{color:#8b97a8;font-size:9px}.owner-cell :deep(.ant-tag){width:max-content;margin:2px 0 0;font-size:9px}.gds-measure-cell{display:grid;gap:2px;text-align:right}.gds-measure-cell small{color:#8b97a8;font-size:9px}.pending{color:#a0a8b5;font-size:10px}.positive{color:#16845b}.negative{color:#cf4a4a}.through-date{display:block;margin-top:3px;text-align:center}.realtime-note{margin:12px 2px 0;color:#7a8798;font-size:11px}.definition-list{display:grid;gap:10px;margin-top:16px}.definition-list article{padding:13px 15px;border:1px solid #e5eaf1;border-radius:9px;background:#fafbfd}.definition-list strong{color:#344258;font-size:13px}.definition-list p,.scene-definition p{margin:5px 0 0;color:#657287;font-size:12px;line-height:1.65}.definition-list code,.scene-definition code{display:inline-block;margin-top:6px;padding:2px 6px;border-radius:4px;color:#365f94;background:#edf4ff;font-size:11px}.scene-definition>strong{color:#344258}.scene-definition b{color:#485971}@media(max-width:1200px){.progress-hero{grid-template-columns:1fr}.hero-cards{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.target-progress-page{padding-inline:12px}.progress-hero{padding:21px 17px}.hero-cards{grid-template-columns:1fr}.toolbar{align-items:flex-start;padding:14px 0;flex-direction:column}.toolbar-left{width:100%;flex-wrap:wrap}.period-select,.keyword-input{width:100%}.scene-note{align-items:flex-start;flex-direction:column}}
</style>
