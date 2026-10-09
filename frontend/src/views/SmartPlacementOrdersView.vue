<template>
  <div class="page-wrap placement-orders-page">
    <PageHeader
      eyebrow="SMART PLACEMENT"
      title="收单情况"
      description="查看投放政策命中的订单、消息触达和业务关注进度"
    >
      <a-button :loading="loading" @click="load(1)"><ReloadOutlined />刷新</a-button>
    </PageHeader>

    <a-alert
      v-if="error"
      type="error"
      show-icon
      class="page-alert"
      :message="error"
    />

    <div class="summary-grid">
      <article v-for="card in summaryCards" :key="card.key" class="summary-card">
        <span>{{ card.label }}</span>
        <strong :class="card.tone">{{ card.format(summaryValue(card.key)) }}</strong>
        <small>{{ card.note }}</small>
      </article>
    </div>

    <a-card class="panel-card" :bordered="false">
      <div class="filter-bar">
        <a-range-picker
          v-model:value="dateRange"
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
              <small>{{ record.ticketNo || '暂无票号' }} · {{ record.passengerName || '暂无乘客' }}</small>
            </button>
          </template>
          <template v-else-if="column.key === 'scope'">
            <div class="two-line"><strong>{{ record.platformName || '—' }}</strong><span>{{ record.siteName || '全部站点' }}</span></div>
          </template>
          <template v-else-if="column.key === 'route'">
            <div class="two-line"><strong>{{ record.airlineCode || '—' }}</strong><span>{{ record.routeText || routeName(record) }}</span></div>
          </template>
          <template v-else-if="column.key === 'policy'">
            <div class="two-line"><strong>{{ record.externalPolicyId }}</strong><span>任务 #{{ record.taskId }}</span></div>
          </template>
          <template v-else-if="column.key === 'volume'">
            <div class="two-line"><strong>{{ number(record.ticketCount) }} 票</strong><span>{{ number(record.segmentCount) }} 航段</span></div>
          </template>
          <template v-else-if="column.key === 'profit'">
            <strong :class="profitClass(record.estimatedProfitCny)">{{ money(record.estimatedProfitCny) }} 元</strong>
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
              <a-button v-if="!['COMPLETED', 'NO_ACTION'].includes(record.attentionStatus)" size="small" type="primary" @click="openAttention(record)">
                {{ record.attentionStatus === 'IN_PROGRESS' ? '处理结果' : '开始关注' }}
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-drawer v-model:open="detailOpen" title="命中订单详情" :width="'min(760px, 100vw)'">
      <a-descriptions v-if="activeOrder" bordered size="small" :column="2">
        <a-descriptions-item label="OTA订单号">{{ activeOrder.otaOrderNo }}</a-descriptions-item>
        <a-descriptions-item label="出票票号">{{ activeOrder.ticketNo || '—' }}</a-descriptions-item>
        <a-descriptions-item label="乘客姓名">{{ activeOrder.passengerName || '—' }}</a-descriptions-item>
        <a-descriptions-item label="外部政策ID">{{ activeOrder.externalPolicyId }}</a-descriptions-item>
        <a-descriptions-item label="平台">{{ activeOrder.platformName || '—' }}</a-descriptions-item>
        <a-descriptions-item label="站点">{{ activeOrder.siteName || '全部站点' }}</a-descriptions-item>
        <a-descriptions-item label="航司">{{ activeOrder.airlineCode || '—' }}</a-descriptions-item>
        <a-descriptions-item label="航程">{{ activeOrder.routeText || routeName(activeOrder) }}</a-descriptions-item>
        <a-descriptions-item label="实际舱位">{{ activeOrder.cabinCodes || '—' }}</a-descriptions-item>
        <a-descriptions-item label="产品类型">{{ activeOrder.productType || '—' }}</a-descriptions-item>
        <a-descriptions-item label="票数 / 航段">{{ number(activeOrder.ticketCount) }} 票 / {{ number(activeOrder.segmentCount) }} 航段</a-descriptions-item>
        <a-descriptions-item label="预估利润">{{ money(activeOrder.estimatedProfitCny) }} 元</a-descriptions-item>
        <a-descriptions-item label="命中时间">{{ displayTime(activeOrder.matchedAt) }}</a-descriptions-item>
        <a-descriptions-item label="关注状态">{{ attentionMeta[activeOrder.attentionStatus]?.label || activeOrder.attentionStatus }}</a-descriptions-item>
        <a-descriptions-item label="命中说明" :span="2">{{ activeOrder.matchDetail || '—' }}</a-descriptions-item>
        <a-descriptions-item label="处理说明" :span="2">{{ activeOrder.resolutionNote || '—' }}</a-descriptions-item>
      </a-descriptions>
    </a-drawer>

    <a-modal v-model:open="attentionOpen" title="更新订单关注状态" :confirm-loading="saving" @ok="saveAttention">
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
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import {
  fetchPlacementOrders,
  updatePlacementAttention,
  type PlacementOrderList,
  type PlacementOrderRow,
} from '@/api/smartPlacement'

const loading = ref(false)
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
const attentionOptions = [{ value: '', label: '全部关注状态' }, ...Object.entries(attentionMeta).map(([value, meta]) => ({ value, label: meta.label }))]
const updateAttentionOptions = [
  { value: 'IN_PROGRESS', label: '开始关注' },
  { value: 'COMPLETED', label: '处理完成' },
  { value: 'NO_ACTION', label: '无需处理' },
]
const number = (value: unknown) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))
const moneyFormatter = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
function money(value: unknown) { return moneyFormatter.format(Number(value || 0)) }
const summaryCards = [
  { key: 'orderCount', label: '命中订单', note: '期间内政策命中记录', tone: 'blue', format: number },
  { key: 'ticketCount', label: '命中票数', note: '匹配订单票数合计', tone: 'blue', format: number },
  { key: 'segmentCount', label: '命中航段', note: '匹配订单航段合计', tone: 'blue', format: number },
  { key: 'estimatedProfit', label: '预估利润', note: '命中订单业务估算利润', tone: 'green', format: (value: unknown) => `${money(value)} 元` },
  { key: 'pendingCount', label: '待关注', note: '待处理及已升级订单', tone: 'orange', format: number },
  { key: 'activePolicyCount', label: '活跃政策', note: '期间内命中的政策数', tone: 'violet', format: number },
] as const
const columns = [
  { title: '订单 / 票号', key: 'order', width: 245, fixed: 'left' as const },
  { title: '平台 / 站点', key: 'scope', width: 170 },
  { title: '航司 / 航程', key: 'route', width: 180 },
  { title: '命中政策', key: 'policy', width: 180 },
  { title: '票数 / 航段', key: 'volume', width: 120 },
  { title: '预估利润', key: 'profit', width: 135, align: 'right' as const },
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

async function load(targetPage = page.value) {
  loading.value = true
  error.value = ''
  page.value = targetPage
  try {
    data.value = await fetchPlacementOrders({
      startDate: dateRange.value[0], endDate: dateRange.value[1],
      ...filters.value, page: page.value, pageSize: pageSize.value,
    })
  } catch (failure) {
    data.value = undefined
    error.value = failure instanceof Error ? failure.message : '收单情况查询失败'
  } finally { loading.value = false }
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

onMounted(() => { void load(1) })
</script>

<style scoped>
.placement-orders-page { padding-bottom: 34px; }
.page-alert { margin-bottom: 14px; border-radius: 10px; }
.summary-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.summary-card { padding: 16px 17px; border: 1px solid #e6ebf2; border-radius: 11px; background: #fff; box-shadow: 0 5px 18px rgba(28,45,72,.035); }
.summary-card span,.summary-card small { display: block; color: #7b8798; font-size: 11px; }.summary-card strong { display: block; margin: 5px 0 2px; color: #26344b; font-size: 22px; white-space: nowrap; }.summary-card .blue { color: #2563eb; }.summary-card .green { color: #059669; }.summary-card .orange { color: #d97706; }.summary-card .violet { color: #7c3aed; }
.panel-card { border: 1px solid #e6ebf2 !important; border-radius: 12px; }
.filter-bar { display: grid; grid-template-columns: 240px minmax(210px,1fr) 150px 120px 90px 120px auto auto; gap: 10px; margin-bottom: 16px; }
.order-link { padding: 0; border: 0; text-align: left; background: transparent; cursor: pointer; }.order-link strong,.order-link small,.two-line strong,.two-line span { display: block; }.order-link strong { color: #275fae; }.order-link small,.two-line span { margin-top: 3px; color: #8290a4; font-size: 11px; }.positive { color: #059669; }.negative { color: #dc2626; }.modal-alert { margin-bottom: 16px; }
@media (max-width: 1280px) { .summary-grid { grid-template-columns: repeat(3, 1fr); }.filter-bar { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 760px) { .summary-grid,.filter-bar { grid-template-columns: 1fr 1fr; } }
</style>
