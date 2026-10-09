<template>
  <div class="page-wrap smart-page">
    <PageHeader eyebrow="SMART TICKET EVIDENCE" title="出票明细" description="按当前日期、业务维度和智能环节查看一票一行的Hive真实出票记录" />
    <SmartAnalysisFilters :loading="loading" @query="queryFromStart" @reset="resetPage" />
    <DataStateBar :label="stateLabel" :message="stateMessage" :freshness="data?.updatedAt || '尚未读取'" metric-state="一行一个 issue_id" />
    <a-alert v-if="data?.error" class="smart-alert" type="error" show-icon :message="data.error" />

    <a-card :bordered="false" class="panel-card smart-detail-panel">
      <div class="detail-toolbar">
        <label><span>票单范围</span><a-select v-model:value="stage" :options="stageOptions" @change="queryFromStart" /></label>
        <div class="detail-scope"><a-tag color="blue">{{ typeLabel }}</a-tag><span>已显示 {{ selectedFields.length }} 个字段</span></div>
        <a-button @click="openFieldModal"><SettingOutlined />显示字段</a-button>
        <a-button type="primary" :loading="loading" @click="queryFromStart"><SearchOutlined />刷新明细</a-button>
      </div>

      <div v-if="data?.available && data.hasData" class="detail-summary-grid">
        <div><span>出票量</span><strong>{{ count(data.summary.ticketCount) }} 张</strong></div>
        <div><span>订单量</span><strong>{{ count(data.summary.orderCount) }} 单</strong></div>
        <div><span>票单预估利润</span><strong>{{ money(data.summary.profit) }} 元</strong></div>
      </div>

      <a-table :columns="tableColumns" :data-source="data?.rows || []" :loading="loading" row-key="recordKey" :pagination="false" :scroll="{ x: tableWidth }" :locale="{ emptyText: '当前范围没有符合条件的出票记录' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'issueId'"><a-button type="link" size="small" @click="openEvidence(record)">{{ record.issueId ?? '—' }}</a-button></template>
          <template v-else-if="column.valueType === 'money'"><span :class="{ negative: Number(record[column.key]) < 0 }">{{ money(record[column.key]) }}</span></template>
          <template v-else-if="column.valueType === 'boolean'">{{ record[column.key] == null ? '—' : record[column.key] ? '是' : '否' }}</template>
          <template v-else-if="column.key === 'smartConfirm'"><a-tag v-if="record.smartConfirm" color="blue">{{ record.smartConfirm }}</a-tag><span v-else>未使用</span></template>
          <template v-else>{{ record[column.key] ?? '—' }}</template>
        </template>
      </a-table>
      <div class="detail-pagination">
        <span>共 {{ count(data?.total) }} 张票；分页只影响页面展示</span>
        <a-pagination v-model:current="page" v-model:pageSize="pageSize" :total="data?.total || 0" :page-size-options="['10','20','50','100']" show-size-changer @change="load" />
      </div>
    </a-card>

    <a-modal v-model:open="fieldModalOpen" title="显示字段" width="760px" ok-text="应用字段" cancel-text="取消" @ok="applyFields">
      <a-input v-model:value="fieldSearch" placeholder="搜索字段名称" allow-clear />
      <div class="field-modal-actions"><span>出票ID固定显示；当前选择 {{ draftFields.length }} 项</span><div><a-button size="small" @click="selectDefaults">恢复默认</a-button><a-button size="small" @click="selectAll">全选</a-button></div></div>
      <div class="field-groups">
        <section v-for="group in filteredFieldGroups" :key="group.name">
          <h3>{{ group.name }}</h3>
          <div><label v-for="field in group.fields" :key="field.key"><input v-model="draftFields" type="checkbox" :value="field.key" :disabled="field.key === 'issueId'">{{ field.title }}</label></div>
        </section>
      </div>
    </a-modal>

    <a-drawer v-model:open="evidenceOpen" title="出票记录与智能任务证据" width="520">
      <template v-if="evidence">
        <div class="evidence-title"><strong>出票ID {{ evidence.issueId }}</strong><span>订单ID {{ evidence.orderId ?? '—' }}</span></div>
        <div class="evidence-facts">
          <div><span>航司 / 平台</span><b>{{ evidence.airline ?? '—' }} / {{ evidence.platform ?? '—' }}</b></div>
          <div><span>出票时间</span><b>{{ evidence.issueTicketTime ?? '—' }}</b></div>
          <div><span>政策员</span><b>{{ evidence.policy ?? '—' }}</b></div>
          <div><span>最终使用智能</span><b>{{ evidence.smartConfirm || '未使用' }}</b></div>
          <div><span>预估利润</span><b>{{ money(evidence.issueProfit) }} 元</b></div>
        </div>
        <h3>参与与成功标记</h3>
        <div class="evidence-events">
          <div><b>智能降舱</b><span>参与：{{ yesNo(evidence.downParticipated) }}　成功：{{ yesNo(evidence.downSucceeded) }}</span></div>
          <div><b>智能废票</b><span>参与：{{ yesNo(evidence.voidParticipated) }}　成功：{{ yesNo(evidence.voidSucceeded) }}</span></div>
          <p>成功标记证明历史任务曾成功；最终是否使用以去重后的 smart_confirm 为准。</p>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Drawer as ADrawer, message, Pagination as APagination } from 'ant-design-vue'
import { SearchOutlined, SettingOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import SmartAnalysisFilters from '@/components/SmartAnalysisFilters.vue'
import { smartAnalysisApi, type SmartDetailColumn, type SmartDetailData, type SmartStage, type SmartType } from '@/api/smartAnalysis'
import { useSmartAnalysisStore } from '@/stores/smartAnalysis'

const DEFAULT_FIELDS = ['issueId', 'otaOrderNo', 'airline', 'platform', 'issueTicketTime', 'smartConfirm', 'issueProfit']
const EVIDENCE_FIELDS = ['downParticipated', 'downSucceeded', 'voidParticipated', 'voidSucceeded', 'orderId', 'policy']
const store = useSmartAnalysisStore()
const route = useRoute()
const data = ref<SmartDetailData>()
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const stage = ref<SmartStage>('all')
const fieldModalOpen = ref(false)
const fieldSearch = ref('')
const selectedFields = ref<string[]>(loadSavedFields())
const draftFields = ref<string[]>([...selectedFields.value])
const evidenceOpen = ref(false)
const evidence = ref<SmartDetailData['rows'][number]>()
const integer = new Intl.NumberFormat('zh-CN')
const currency = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const stageOptions = [
  { label: '全部出票', value: 'all' }, { label: '参与智能', value: 'participation' },
  { label: '智能成功', value: 'success' }, { label: '使用智能', value: 'use' },
  { label: '参与但未成功', value: 'unsuccessful' }, { label: '成功但未使用', value: 'unused' },
  { label: '退票出票', value: 'refund' },
]
const typeLabel = computed(() => ({ all: '智能整体', down: '智能降舱', void: '智能废票' }[store.smartType]))
const count = (value: number | null | undefined) => value == null ? '—' : integer.format(value)
const money = (value: unknown) => value == null || value === '' ? '—' : currency.format(Number(value))
const yesNo = (value: unknown) => value == null ? '—' : value ? '是' : '否'
const stateLabel = computed(() => data.value?.available && data.value.hasData ? '真实Hive明细' : data.value?.available ? '当前范围暂无数据' : '数据不可用')
const stateMessage = computed(() => data.value?.available && data.value.hasData ? `${data.value.source} · ${typeLabel.value} · ${stageOptions.find(item => item.value === stage.value)?.label}` : data.value?.error || '查询无记录不认定为真实零')
const tableColumns = computed(() => selectedFields.value.map(key => data.value?.availableColumns.find(column => column.key === key)).filter((column): column is SmartDetailColumn => Boolean(column)).map(column => ({ ...column, dataIndex: column.key, fixed: column.key === 'issueId' ? 'left' as const : undefined })))
const tableWidth = computed(() => tableColumns.value.reduce((sum, column) => sum + column.width, 0))
const filteredFieldGroups = computed(() => {
  const query = fieldSearch.value.trim().toLowerCase()
  const grouped = new Map<string, SmartDetailColumn[]>()
  for (const field of data.value?.availableColumns || []) {
    if (EVIDENCE_FIELDS.includes(field.key)) continue
    if (query && !field.title.toLowerCase().includes(query)) continue
    const rows = grouped.get(field.category) || []
    rows.push(field)
    grouped.set(field.category, rows)
  }
  return [...grouped].map(([name, fields]) => ({ name, fields }))
})

function loadSavedFields() {
  try {
    const value = JSON.parse(localStorage.getItem('smart-detail-fields-v1') || '[]')
    if (Array.isArray(value) && value.length) return ['issueId', ...value.filter((key, index) => key !== 'issueId' && typeof key === 'string' && value.indexOf(key) === index)]
  } catch { /* use defaults */ }
  return [...DEFAULT_FIELDS]
}

async function load() {
  loading.value = true
  try {
    data.value = await smartAnalysisApi.details({ ...store.applied }, {
      smartType: store.smartType, stage: stage.value,
      fields: [...new Set([...selectedFields.value, ...EVIDENCE_FIELDS])],
      page: page.value, pageSize: pageSize.value,
    })
  } catch (error) { data.value = undefined; message.error(error instanceof Error ? error.message : '出票明细加载失败') }
  finally { loading.value = false }
}
function queryFromStart() { page.value = 1; void load() }
function resetPage() { stage.value = 'all'; page.value = 1; selectedFields.value = [...DEFAULT_FIELDS]; void load() }
function selectDefaults() { draftFields.value = [...DEFAULT_FIELDS] }
function selectAll() { draftFields.value = (data.value?.availableColumns || []).filter(field => !EVIDENCE_FIELDS.includes(field.key)).map(field => field.key) }
function applyFields() {
  selectedFields.value = ['issueId', ...draftFields.value.filter(key => key !== 'issueId')]
  localStorage.setItem('smart-detail-fields-v1', JSON.stringify(selectedFields.value))
  fieldModalOpen.value = false
  queryFromStart()
}
function openFieldModal() {
  draftFields.value = [...selectedFields.value]
  fieldSearch.value = ''
  fieldModalOpen.value = true
}
function openEvidence(record: SmartDetailData['rows'][number]) { evidence.value = record; evidenceOpen.value = true }

onMounted(() => {
  const queryType = String(route.query.smartType || '') as SmartType
  const queryStage = String(route.query.stage || '') as SmartStage
  if (['all', 'down', 'void'].includes(queryType)) store.smartType = queryType
  if (stageOptions.some(item => item.value === queryStage)) stage.value = queryStage
  draftFields.value = [...selectedFields.value]
  void load()
})
</script>

<style scoped>
.smart-alert { margin: 14px 0; }
.smart-detail-panel { margin-top: 16px; }
.detail-toolbar { display: flex; align-items: end; gap: 12px; margin-bottom: 16px; }
.detail-toolbar > label { width: 210px; display: grid; gap: 6px; color: #718096; font-size: 11px; }
.detail-scope { flex: 1; display: flex; align-items: center; gap: 9px; color: #7c899b; font-size: 11px; }
.detail-summary-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 10px; margin-bottom: 16px; }
.detail-summary-grid div { padding: 13px 15px; display: grid; gap: 5px; border-radius: 8px; background: #f5f8fc; }
.detail-summary-grid span { color: #7a8798; font-size: 10px; }
.detail-summary-grid strong { color: #324159; font-size: 16px; }
.negative { color: #c14f5e; }
.detail-pagination { padding-top: 16px; display: flex; align-items: center; justify-content: space-between; color: #7d8999; font-size: 11px; }
.field-modal-actions { margin: 13px 0; display: flex; justify-content: space-between; align-items: center; color: #788598; font-size: 11px; }
.field-modal-actions > div { display: flex; gap: 8px; }
.field-groups { max-height: 520px; overflow: auto; }
.field-groups section { padding: 13px 0; border-top: 1px solid #edf0f4; }
.field-groups h3 { margin: 0 0 10px; color: #41516a; font-size: 12px; }
.field-groups section > div { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 9px; }
.field-groups label { display: flex; align-items: center; gap: 7px; color: #5f6d82; font-size: 11px; }
.evidence-title { display: grid; gap: 5px; margin-bottom: 18px; }
.evidence-title strong { color: #2d3d55; font-size: 18px; }
.evidence-title span { color: #7d8999; font-size: 11px; }
.evidence-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 24px; }
.evidence-facts div { padding: 12px; display: grid; gap: 5px; border-radius: 8px; background: #f5f8fc; }
.evidence-facts span { color: #8390a2; font-size: 10px; }
.evidence-facts b { color: #405069; font-size: 12px; }
.evidence-events div { margin: 10px 0; padding: 13px; display: grid; gap: 5px; border-left: 3px solid #75a5ed; background: #f5f9ff; }
.evidence-events b { color: #33527e; font-size: 12px; }
.evidence-events span, .evidence-events p { color: #75839a; font-size: 11px; }
@media (max-width: 750px) { .detail-toolbar { align-items: stretch; flex-direction: column; } .detail-toolbar > label { width: 100%; } .detail-summary-grid, .field-groups section > div, .evidence-facts { grid-template-columns: 1fr; } .detail-pagination { align-items: flex-start; flex-direction: column; gap: 12px; } }
</style>
