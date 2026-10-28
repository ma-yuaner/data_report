<template>
  <div class="page-wrap placement-orders-page">
    <PageHeader
      eyebrow="SMART PLACEMENT"
      title="收单情况"
      description="查看投放政策命中的订单、消息触达和业务关注进度"
    />

    <a-alert
      v-if="error"
      type="error"
      show-icon
      class="page-alert"
      :message="error"
    />

    <section class="orders-hero">
      <div><h2>收单监控与跟进</h2><p>汇总已投放政策命中的真实订单，识别需要立即关注的来单，并展示平台、航司、政策、人员和处理状态。</p></div>
      <a-button class="hero-action" :loading="loading" @click="load(1)"><ReloadOutlined /> 刷新当前结果</a-button>
    </section>

    <div class="summary-grid">
      <article v-for="card in summaryCards" :key="card.key" class="summary-card">
        <span>{{ card.label }}</span>
        <strong :class="card.tone">{{ card.format(summaryValue(card.key)) }}</strong>
        <small>{{ card.note }}</small>
      </article>
    </div>

    <a-card class="panel-card orders-panel" :bordered="false">
      <div class="filter-bar">
        <a-range-picker
          v-model:value="dateRange"
          :locale="dateLocale"
          value-format="YYYY-MM-DD"
          :allow-clear="false"
        />
        <a-input v-model:value="filters.keyword" allow-clear placeholder="订单号 / 政策ID / 航程" @press-enter="load(1)">
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <a-select v-model:value="filters.attentionStatus" :options="attentionOptions" />
        <a-input v-model:value="filters.platform" allow-clear placeholder="平台名称" />
        <a-input v-model:value="filters.airline" allow-clear placeholder="航司" />
        <a-input v-model:value="filters.owner" allow-clear placeholder="关注负责人" />
        <a-button type="primary" @click="load(1)">查询</a-button>
        <a-button @click="resetFilters">重置</a-button>
      </div>

      <a-table
        row-key="id"
        :columns="columns"
        :data-source="data?.rows || []"
        :loading="loading"
        :pagination="pagination"
        :scroll="{ x: 1500 }"
        @change="changePage"
      >
        <template #emptyText>
          <a-empty :description="error || '所选期间暂无命中订单'" />
        </template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'order'">
            <button class="order-link" type="button" @click="openDetail(record)">
              <strong>{{ record.otaOrderNo }}</strong>
              <small>{{ currentValue(record.currentTicketNo, record.ticketNo, record) || '暂无票号' }} · {{ record.passengerName || '暂无乘客' }}</small>
            </button>
          </template>
          <template v-else-if="column.key === 'scope'">
            <div class="two-line"><strong>{{ record.platformName || '—' }}</strong><span>{{ record.siteName || '全部站点' }}</span></div>
          </template>
          <template v-else-if="column.key === 'route'">
            <div class="two-line"><strong>{{ record.airlineCode || '—' }}</strong><span>{{ record.routeText || routeName(record) }}</span></div>
          </template>
          <template v-else-if="column.key === 'policy'">
            <div class="two-line"><strong>{{ record.externalPolicyId }}</strong><span>任务 #{{ record.taskId }} · {{ attributionLabel(record) }}</span></div>
          </template>
          <template v-else-if="column.key === 'volume'">
            <div class="two-line"><strong>{{ quantity(currentValue(record.currentTicketCount, record.ticketCount, record), '票') }}</strong><span>{{ quantity(currentValue(record.currentSegmentCount, record.segmentCount, record), '航段') }}</span></div>
          </template>
          <template v-else-if="column.key === 'profit'">
            <strong v-if="currentValue(record.currentEstimatedProfitCny, record.estimatedProfitCny, record) !== null" :class="profitClass(currentValue(record.currentEstimatedProfitCny, record.estimatedProfitCny, record))">{{ money(currentValue(record.currentEstimatedProfitCny, record.estimatedProfitCny, record)) }} 元</strong>
            <a-tag v-else color="orange">待同步</a-tag>
          </template>
          <template v-else-if="column.key === 'outcome'">
            <div class="two-line"><a-tag :color="outcomeMeta[record.outcomeStatus || 'WAITING_SYNC']?.color || 'default'">{{ outcomeLabel(record) }}</a-tag><span :class="{ 'stale-text': record.statusFreshnessStatus === 'STALE' }">{{ statusFreshnessLabel(record) }}</span><span :class="{ 'stale-text': record.dataFreshnessStatus === 'STALE' }">{{ freshnessLabel(record) }}</span></div>
          </template>
          <template v-else-if="column.key === 'message'">
            <a-tag :color="messageMeta[record.messageStatus]?.color || 'default'">{{ messageMeta[record.messageStatus]?.label || record.messageStatus }}</a-tag>
          </template>
          <template v-else-if="column.key === 'attention'">
            <div class="two-line"><a-tag :color="attentionMeta[record.attentionStatus]?.color || 'default'">{{ attentionMeta[record.attentionStatus]?.label || record.attentionStatus }}</a-tag><span>{{ record.attentionOwnerName || '未分配' }}</span></div>
          </template>
          <template v-else-if="column.key === 'matchedAt'">{{ displayTime(record.matchedAt) }}</template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button size="small" @click="openDetail(record)">详情</a-button>
              <a-button v-if="canManageAttention && !['COMPLETED', 'NO_ACTION'].includes(record.attentionStatus)" size="small" type="primary" @click="openAttention(record)">
                {{ record.attentionStatus === 'IN_PROGRESS' ? '处理结果' : '开始关注' }}
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-drawer v-model:open="detailOpen" title="命中订单详情" :width="'min(760px, 100vw)'" class="placement-order-drawer">
      <template v-if="activeOrder">
        <div class="order-detail-hero"><span>OTA订单号</span><h2>{{ activeOrder.otaOrderNo }}</h2><p>{{ activeOrder.platformName || '—' }} · {{ activeOrder.airlineCode || '—' }} · {{ activeOrder.routeText || routeName(activeOrder) }}</p></div>
        <section class="order-detail-section"><h3>订单与命中信息</h3><div class="order-detail-grid">
          <div><label>出票票号</label><span>{{ currentValue(activeOrder.currentTicketNo, activeOrder.ticketNo, activeOrder) || '待同步' }}</span></div><div><label>乘客姓名</label><span>{{ currentValue(activeOrder.currentPassengerName, activeOrder.passengerName, activeOrder) || '待同步' }}</span></div>
          <div><label>外部政策 ID</label><span>{{ activeOrder.externalPolicyId }}</span></div><div><label>平台 / 站点</label><span>{{ activeOrder.platformName || '—' }} / {{ activeOrder.siteName || '全部站点' }}</span></div>
          <div><label>航司 / 航程</label><span>{{ activeOrder.airlineCode || '—' }} / {{ activeOrder.routeText || routeName(activeOrder) }}</span></div><div><label>实际舱位</label><span>{{ activeOrder.cabinCodes || '—' }}</span></div>
          <div><label>产品类型</label><span>{{ activeOrder.productType || '—' }}</span></div><div><label>票数 / 航段</label><span>{{ quantity(currentValue(activeOrder.currentTicketCount, activeOrder.ticketCount, activeOrder), '票') }} / {{ quantity(currentValue(activeOrder.currentSegmentCount, activeOrder.segmentCount, activeOrder), '航段') }}</span></div>
          <div><label>预估利润</label><span>{{ nullableMoney(currentValue(activeOrder.currentEstimatedProfitCny, activeOrder.estimatedProfitCny, activeOrder)) }}</span></div><div><label>命中时间</label><span>{{ displayTime(activeOrder.matchedAt) }}</span></div>
          <div><label>当前订单结果</label><span>{{ outcomeLabel(activeOrder) }}</span></div><div><label>当前出票时间</label><span>{{ displayTime(activeOrder.currentTicketTime) }}</span></div>
          <div><label>智能参与 / 成功</label><span>{{ triState(activeOrder.smartParticipated) }} / {{ triState(activeOrder.smartSucceeded) }}</span></div><div><label>明细来源更新</label><span>{{ displayTime(activeOrder.outcomeSourceUpdatedAt) }}（{{ freshnessLabel(activeOrder) }}）</span></div><div><label>最近核对</label><span>{{ displayTime(activeOrder.outcomeLastCheckedAt) }}</span></div><div><label>明细来源</label><span>{{ activeOrder.outcomeSourceTable || '尚未取得' }}</span></div>
          <div><label>状态来源更新</label><span>{{ displayTime(activeOrder.statusSourceUpdatedAt) }}（{{ statusFreshnessLabel(activeOrder) }}）</span></div><div><label>状态来源</label><span>{{ activeOrder.statusSourceTable || '等待后台核对' }}</span></div>
          <div><label>政策归属</label><span>{{ attributionLabel(activeOrder) }}</span></div><div><label>命中政策数</label><span>{{ quantity(activeOrder.matchedPolicyCount, '个') }}</span></div>
        </div></section>
        <section class="order-detail-section"><h3>提醒与关注记录</h3><div class="order-timeline"><article><strong>订单命中投放规则</strong><p>{{ activeOrder.matchDetail || '平台、航司、航程及有效期满足匹配条件' }}</p><time>{{ displayTime(activeOrder.matchedAt) }}</time></article><article><strong>{{ messageMeta[activeOrder.messageStatus]?.label || activeOrder.messageStatus }}</strong><p>系统记录当前群提醒发送状态</p></article><article><strong>{{ attentionMeta[activeOrder.attentionStatus]?.label || activeOrder.attentionStatus }}</strong><p>{{ activeOrder.resolutionNote || '等待业务人员补充处理结果' }}</p></article></div></section>
      </template>
    </a-drawer>

    <a-modal v-model:open="attentionOpen" title="更新订单关注状态" width="min(620px, 94vw)" wrap-class-name="placement-order-action-modal" :footer="null" :mask-closable="false">
      <a-alert v-if="activeOrder" type="info" show-icon class="modal-alert" :message="`${activeOrder.otaOrderNo} · ${activeOrder.externalPolicyId}`" />
      <a-form layout="vertical">
        <a-form-item label="关注状态" required>
          <a-select v-model:value="attentionForm.status" :options="updateAttentionOptions" />
        </a-form-item>
        <a-form-item v-if="['COMPLETED', 'NO_ACTION'].includes(attentionForm.status)" label="处理结果" required>
          <a-input v-model:value="attentionForm.resolutionCode" placeholder="例如：已重点跟进、无需处理、异常订单" />
        </a-form-item>
        <a-form-item label="处理说明" :required="attentionForm.status === 'NO_ACTION'">
          <a-textarea v-model:value="attentionForm.resolutionNote" :rows="4" placeholder="记录业务关注结果，便于复盘" />
        </a-form-item>
      </a-form>
      <div class="dialog-actions"><a-button @click="attentionOpen=false">取消</a-button><a-button type="primary" :loading="saving" @click="saveAttention">保存关注状态</a-button></div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  Drawer as ADrawer,
  Empty as AEmpty,
  Form as AForm,
  FormItem as AFormItem,
  RangePicker as ARangePicker,
  message,
} from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import {
  fetchPlacementOrders,
  updatePlacementAttention,
  type PlacementOrderList,
  type PlacementOrderRow,
} from '@/api/smartPlacement'

const loading = ref(false)
const authStore = useAuthStore()
const canManageAttention = computed(() => Boolean(authStore.user?.isAdmin) || Boolean(authStore.user?.permissions?.includes('smart_placement.orders.attention')))
const saving = ref(false)
const error = ref('')
const data = ref<PlacementOrderList>()
const page = ref(1)
const pageSize = ref(30)
const today = businessToday()
const dateRange = ref<[string, string]>([`${today.slice(0, 7)}-01`, today])
const filters = ref({ keyword: '', attentionStatus: '', platform: '', airline: '', owner: '' })
const detailOpen = ref(false)
const attentionOpen = ref(false)
const activeOrder = ref<PlacementOrderRow>()
const attentionForm = ref({ status: 'IN_PROGRESS', resolutionCode: '', resolutionNote: '' })

const attentionMeta: Record<string, { label: string; color: string }> = {
  PENDING: { label: '待关注', color: 'orange' },
  IN_PROGRESS: { label: '关注中', color: 'processing' },
  COMPLETED: { label: '已完成', color: 'green' },
  NO_ACTION: { label: '无需处理', color: 'default' },
  ESCALATED: { label: '已升级', color: 'red' },
}
const messageMeta: Record<string, { label: string; color: string }> = {
  PENDING: { label: '待发送', color: 'orange' }, SENT: { label: '已发送', color: 'green' }, FAILED: { label: '发送失败', color: 'red' },
}
const outcomeMeta: Record<string, { label: string; color: string }> = {
  WAITING_SYNC: { label: '等待宽表同步', color: 'orange' }, PENDING: { label: '待出票', color: 'blue' },
  TICKETED: { label: '已出票', color: 'green' }, CANCELLED: { label: '已取消', color: 'default' },
  REFUNDED: { label: '已退票', color: 'purple' }, UNKNOWN: { label: '状态待确认', color: 'default' },
}
const attentionOptions = [{ value: '', label: '全部关注状态' }, ...Object.entries(attentionMeta).map(([value, meta]) => ({ value, label: meta.label }))]
const updateAttentionOptions = [
  { value: 'IN_PROGRESS', label: '开始关注' },
  { value: 'COMPLETED', label: '处理完成' },
  { value: 'NO_ACTION', label: '无需处理' },
]
const number = (value: unknown) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))
const moneyFormatter = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
function money(value: unknown) { return moneyFormatter.format(Number(value || 0)) }
function currentValue<T>(current: T | null | undefined, snapshot: T | null | undefined, record?: PlacementOrderRow): T | null {
  if (record?.dataFreshnessStatus === 'MISSING' && record.outcomeSourceTable) return current ?? null
  return current !== null && current !== undefined ? current : (snapshot !== null && snapshot !== undefined ? snapshot : null)
}
function quantity(value: unknown, unit: string) { return value === null || value === undefined || value === '' ? '待同步' : `${number(value)} ${unit}` }
function nullableMoney(value: unknown) { return value === null || value === undefined || value === '' ? '待同步' : `${money(value)} 元` }
function triState(value: unknown) { return value === null || value === undefined ? '待同步' : Number(value) === 1 ? '是' : '否' }
function attributionLabel(record: PlacementOrderRow) { return record.attributionType === 'SECONDARY' ? `次归属（主命中 #${record.primaryMatchId || '—'}）` : record.matchedPolicyCount && record.matchedPolicyCount > 1 ? '主归属' : '唯一归属' }
function outcomeLabel(record: PlacementOrderRow) {
  const label = outcomeMeta[record.outcomeStatus || 'WAITING_SYNC']?.label || record.outcomeStatus
  return record.outcomeStatus === 'TICKETED' && record.dataFreshnessStatus === 'MISSING' ? '已出票 · 明细待补齐' : label
}
function freshnessLabel(record: PlacementOrderRow) {
  if (record.dataFreshnessStatus === 'MISSING' && record.outcomeSourceTable) return record.outcomeSourceTable.endsWith('.rt_order_monitor_feature') ? '出票状态来自采集快照' : '沿用上次结果，本轮源表缺单'
  return record.dataFreshnessStatus === 'FRESH' ? '明细已更新' : record.dataFreshnessStatus === 'STALE' ? '明细源超过时效，待更新' : '明细等待同步'
}
function statusFreshnessLabel(record: PlacementOrderRow) {
  return record.statusFreshnessStatus === 'FRESH' ? '状态已更新' : record.statusFreshnessStatus === 'STALE' ? '状态源超过时效' : '状态时效待核对'
}
const summaryCards = [
  { key: 'primaryOrderCount', label: '归属订单', note: '按订单主归属去重', tone: 'blue', format: number },
  { key: 'ticketCount', label: '命中票数', note: '匹配订单票数合计', tone: 'blue', format: number },
  { key: 'segmentCount', label: '命中航段', note: '匹配订单航段合计', tone: 'blue', format: number },
  { key: 'estimatedProfit', label: '预估利润', note: '命中订单业务估算利润', tone: 'green', format: (value: unknown) => `${money(value)} 元` },
  { key: 'pendingCount', label: '待关注', note: '待处理及已升级订单', tone: 'orange', format: number },
  { key: 'activePolicyCount', label: '活跃政策', note: '期间内命中的政策数', tone: 'violet', format: number },
  { key: 'waitingSyncCount', label: '明细待同步', note: '结果源缺单，含已出票兜底记录', tone: 'orange', format: number },
  { key: 'staleCount', label: '明细待更新', note: '明细源超过时效，订单状态另行核对', tone: 'red', format: number },
] as const
const columns = [
  { title: '订单 / 票号', key: 'order', width: 245, fixed: 'left' as const },
  { title: '平台 / 站点', key: 'scope', width: 170 },
  { title: '航司 / 航程', key: 'route', width: 180 },
  { title: '命中政策', key: 'policy', width: 180 },
  { title: '票数 / 航段', key: 'volume', width: 120 },
  { title: '预估利润', key: 'profit', width: 135, align: 'right' as const },
  { title: '当前结果', key: 'outcome', width: 140 },
  { title: '消息', key: 'message', width: 100 },
  { title: '业务关注', key: 'attention', width: 135 },
  { title: '命中时间', key: 'matchedAt', width: 155 },
  { title: '操作', key: 'action', width: 170, fixed: 'right' as const },
]
const pagination = computed(() => ({ current: page.value, pageSize: pageSize.value, total: data.value?.total || 0, showSizeChanger: true, showTotal: (total: number) => `共 ${number(total)} 条` }))
const summaryValue = (key: typeof summaryCards[number]['key']) => data.value?.summary?.[key] ?? 0
function businessToday() { return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }) }
function displayTime(value: unknown) { return value ? String(value).replace('T', ' ').slice(0, 16) : '—' }
function routeName(record?: PlacementOrderRow) { return [record?.departureCode, record?.arrivalCode].filter(Boolean).join('-') || '不限航程' }
function profitClass(value: unknown) { return Number(value || 0) < 0 ? 'negative' : 'positive' }

let lastQuery: Record<string, string | number> | undefined
let loadVersion = 0
async function load(targetPage = page.value, automatic = false) {
  const params = automatic ? lastQuery : {
    startDate: dateRange.value[0], endDate: dateRange.value[1],
    ...filters.value, page: targetPage, pageSize: pageSize.value,
  }
  if (!params) return
  if (!automatic) lastQuery = params
  const version = ++loadVersion
  loading.value = true
  error.value = ''
  page.value = targetPage
  try {
    const result = await fetchPlacementOrders(params)
    if (version !== loadVersion) return
    data.value = result
    if (detailOpen.value && !attentionOpen.value && activeOrder.value) {
      const current = data.value.rows.find(row => row.id === activeOrder.value?.id)
      if (current) activeOrder.value = current
    }
  } catch (failure) {
    if (version !== loadVersion) return
    data.value = undefined
    error.value = failure instanceof Error ? failure.message : '收单情况查询失败'
  } finally { if (version === loadVersion) loading.value = false }
}
function resetFilters() {
  dateRange.value = [`${today.slice(0, 7)}-01`, today]
  filters.value = { keyword: '', attentionStatus: '', platform: '', airline: '', owner: '' }
  void load(1)
}
function changePage(value: { current?: number; pageSize?: number }) {
  const size = value.pageSize || pageSize.value
  page.value = size === pageSize.value ? value.current || 1 : 1
  pageSize.value = size
  void load(page.value)
}
function openDetail(record: PlacementOrderRow) { activeOrder.value = record; detailOpen.value = true }
function openAttention(record: PlacementOrderRow) {
  activeOrder.value = record
  attentionForm.value = { status: record.attentionStatus === 'IN_PROGRESS' ? 'COMPLETED' : 'IN_PROGRESS', resolutionCode: '', resolutionNote: '' }
  attentionOpen.value = true
}
async function saveAttention() {
  if (!activeOrder.value) return
  saving.value = true
  try {
    await updatePlacementAttention(activeOrder.value.id, attentionForm.value)
    message.success('关注状态已更新')
    attentionOpen.value = false
    await load()
  } catch (failure) {
    message.error(failure instanceof Error ? failure.message : '状态更新失败')
  } finally { saving.value = false }
}

let refreshTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  void load(1)
  refreshTimer = setInterval(() => {
    if (!document.hidden && !loading.value && !attentionOpen.value && !saving.value) void load(page.value, true)
  }, 300_000)
})
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })
</script>

<style scoped>
:global(.placement-order-action-modal .ant-modal-content) { overflow: hidden; border: 1px solid #dfe6ef; border-radius: 14px; box-shadow: 0 20px 55px rgba(29,44,68,.2); }
:global(.placement-order-action-modal .ant-modal-header) { margin-bottom: 0; padding: 20px 22px 16px; border-bottom: 1px solid #e8edf4; }
:global(.placement-order-action-modal .ant-modal-body) { padding: 18px 22px 22px; }
.placement-orders-page { padding-bottom: 34px; }
.page-alert { margin-bottom: 14px; border-radius: 10px; }
.orders-hero { position: relative; display: flex; min-height: 124px; align-items: center; justify-content: space-between; gap: 24px; overflow: hidden; margin-bottom: 16px; padding: 24px 28px; border-radius: 16px; color: #fff; background: linear-gradient(110deg,#2049a6 0%,#1768bd 55%,#0f8d9c 100%); box-shadow: 0 10px 30px rgba(27,41,70,.08); }.orders-hero::after { position: absolute; top: -115px; right: -70px; width: 320px; height: 320px; border: 40px solid rgba(255,255,255,.08); border-radius: 50%; content: ''; }.orders-hero h2 { position: relative; z-index: 1; margin: 0 0 6px; color: #fff; font-size: 20px; }.orders-hero p { position: relative; z-index: 1; max-width: 760px; margin: 0; color: #d8e9ff; }.hero-action { position: relative; z-index: 1; flex: none; border: 0; color: #1a55a4; font-weight: 700; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.summary-card { padding: 17px 18px; border: 1px solid #e8edf4; border-radius: 12px; background: #fff; box-shadow: 0 4px 15px rgba(30,52,89,.04); }.summary-card span,.summary-card small { display: block; color: #697386; font-size: 11px; }.summary-card span { font-size: 12px; }.summary-card strong { display: block; margin: 7px 0 3px; color: #26344b; font-size: 23px; white-space: nowrap; }.summary-card .blue { color: #2563eb; }.summary-card .green { color: #059669; }.summary-card .orange { color: #ea580c; }.summary-card .violet { color: #7c3aed; }
.panel-card { border: 1px solid #e8edf4 !important; border-radius: 13px; box-shadow: 0 5px 20px rgba(25,43,74,.045); }.orders-panel :deep(.ant-card-body) { padding: 18px; }
.filter-bar { display: grid; grid-template-columns: 240px minmax(210px,1fr) 150px 120px 90px 120px auto auto; gap: 10px; margin-bottom: 16px; }
.order-link { padding: 0; border: 0; text-align: left; background: transparent; cursor: pointer; }.order-link strong,.order-link small,.two-line strong,.two-line span { display: block; }.order-link strong { color: #275fae; }.order-link small,.two-line span { margin-top: 3px; color: #8290a4; font-size: 11px; }.positive { color: #059669; }.negative { color: #dc2626; }.modal-alert { margin-bottom: 16px; }.stale-text { color: #dc2626 !important; font-weight: 600; }
.order-detail-hero { margin: -8px 0 18px; padding: 18px 20px; border: 1px solid #d7e3f4; border-radius: 13px; background: linear-gradient(135deg,#f3f7fe,#fff); }.order-detail-hero span,.order-detail-hero p { color: #76859a; font-size: 11px; }.order-detail-hero h2 { margin: 4px 0; color: #253a58; font-size: 20px; }.order-detail-hero p { margin: 0; }.order-detail-section { margin-bottom: 16px; padding: 16px; border: 1px solid #e4e9f0; border-radius: 11px; background: #fff; }.order-detail-section h3 { margin: 0 0 12px; color: #31445f; font-size: 14px; }.order-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }.order-detail-grid > div { padding: 10px 12px; border-radius: 8px; background: #f7f9fc; }.order-detail-grid label,.order-detail-grid span { display: block; }.order-detail-grid label { color: #8a95a8; font-size: 11px; }.order-detail-grid span { margin-top: 3px; color: #344054; }.order-timeline { margin-left: 7px; padding-left: 18px; border-left: 2px solid #dfe7f2; }.order-timeline article { position: relative; padding: 0 0 18px; }.order-timeline article::before { position: absolute; top: 5px; left: -24px; width: 9px; height: 9px; border: 2px solid #fff; border-radius: 50%; background: #2563eb; box-shadow: 0 0 0 2px #a9c4ff; content: ''; }.order-timeline p { margin: 3px 0; color: #667085; }.order-timeline time { color: #8a95a8; font-size: 11px; }.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin: 18px -22px -22px; padding: 14px 22px; border-top: 1px solid #e5eaf1; background: #fff; }
@media (max-width: 1280px) { .summary-grid { grid-template-columns: repeat(3, 1fr); }.filter-bar { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 760px) { .summary-grid,.filter-bar,.order-detail-grid { grid-template-columns: 1fr 1fr; }.orders-hero { align-items: flex-start; flex-direction: column; } }
@media (max-width: 520px) { .summary-grid,.filter-bar,.order-detail-grid { grid-template-columns: 1fr; } }
</style>
