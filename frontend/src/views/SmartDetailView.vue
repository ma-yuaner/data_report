<template>
  <div class="page-wrap smart-page">
    <PageHeader eyebrow="SMART TICKET EVIDENCE" title="出票明细" description="按当前日期、业务维度和智能环节查看一票一行的MySQL真实出票记录">
      <a-button v-if="drillContext" @click="backToSource"><ArrowLeftOutlined />返回{{ drillContext.sourceTitle }}</a-button>
    </PageHeader>

    <section v-if="drillContext" class="drill-context">
      <div><strong>当前明细来源：{{ drillContext.sourceTitle }}</strong><span>已带入来源页的日期、业务筛选和智能口径</span></div>
      <div><a-tag v-for="tag in drillContext.tags" :key="`${tag.label}-${tag.value}`" color="blue">{{ tag.label }}：{{ tag.value }}</a-tag></div>
    </section>

    <SmartAnalysisFilters page="detail" :loading="loading" @query="queryFromStart" @reset="resetPage" />
    <DataStateBar :label="stateLabel" :message="stateMessage" :freshness="data?.updatedAt || '尚未读取'" metric-state="一行一个 issue_id" />
    <a-alert v-if="data?.error" class="smart-alert" type="error" show-icon :message="data.error" />

    <a-card :bordered="false" class="panel-card smart-detail-panel">
      <div class="view-template-bar">
        <strong>私人模板 / 公共模板</strong>
        <a-select v-model:value="selectedTemplateId" allow-clear placeholder="选择私人或公共模板" :options="templateOptions" @change="applyFieldTemplate" />
        <a-button @click="openTemplateModal"><SaveOutlined />保存当前字段</a-button>
        <a-button danger :disabled="!selectedTemplate?.isOwner" @click="deleteFieldTemplate"><DeleteOutlined />删除模板</a-button>
        <span>私人模板仅本人可见；可在保存时公开供其他账号使用</span>
      </div>
      <div class="detail-toolbar">
        <label class="ticket-scope"><span>票单范围</span><a-select v-model:value="stage" :options="stageOptions" :dropdown-match-select-width="false" popup-class-name="ticket-scope-popup" @change="queryFromStart" /></label>
        <div class="detail-scope"><a-tag color="blue">{{ typeLabel }}</a-tag><span>已显示 {{ selectedFields.length }} 个字段</span></div>
        <label class="export-scope"><span>导出字段</span><a-select v-model:value="exportScope" :options="exportScopeOptions" /></label>
        <a-button @click="openFieldModal"><SettingOutlined />显示字段</a-button>
        <a-button :loading="exporting" @click="exportRows"><DownloadOutlined />导出</a-button>
        <a-button type="primary" :loading="loading" @click="queryFromStart"><SearchOutlined />刷新明细</a-button>
      </div>

      <div v-if="data?.available && data.hasData" class="detail-summary-grid">
        <div><span>出票量</span><strong>{{ count(data.summary.ticketCount) }} 张</strong></div>
        <div><span>订单量</span><strong>{{ count(data.summary.orderCount) }} 单</strong></div>
        <div><span>票单预估利润</span><strong>{{ money(data.summary.profit) }} 元</strong></div>
      </div>

      <a-table :columns="tableColumns" :data-source="data?.rows || []" :loading="loading" row-key="recordKey" :pagination="false" :scroll="{ x: tableWidth }" :locale="{ emptyText: '当前范围没有符合条件的出票记录' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'issueId'"><a-button type="link" size="small" @click="openTicket(record.issueId)">{{ record.issueId ?? '—' }}</a-button></template>
          <template v-else-if="column.valueType === 'money'"><span :class="{ negative: Number(record[column.key]) < 0 }">{{ money(record[column.key]) }}</span></template>
          <template v-else-if="column.valueType === 'boolean'">{{ yesNo(record[column.key]) }}</template>
          <template v-else-if="column.key === 'smartConfirm'"><a-tag v-if="record.smartConfirm" color="blue">{{ record.smartConfirm }}</a-tag><span v-else>未使用</span></template>
          <template v-else>{{ record[column.key] ?? '—' }}</template>
        </template>
      </a-table>
      <div class="detail-pagination">
        <span>共 {{ count(data?.total) }} 张票；页面分页不影响导出，单次上限 900,000 条。超过 300,000 条时会提醒，建议缩小日期或筛选范围</span>
        <a-pagination v-model:current="page" v-model:pageSize="pageSize" :total="data?.total || 0" :page-size-options="['10','20','50','100']" show-size-changer @change="load" />
      </div>
    </a-card>

    <a-modal v-model:open="fieldModalOpen" title="显示字段" width="760px" ok-text="应用字段" cancel-text="取消" @ok="applyFields">
      <a-input v-model:value="fieldSearch" placeholder="搜索字段名称" allow-clear />
      <div class="field-modal-actions"><span>出票ID固定显示；当前选择 {{ draftFields.length }} 项</span><div><a-button size="small" @click="selectDefaults">恢复默认</a-button><a-button size="small" @click="selectAll">全选</a-button></div></div>
      <div class="field-groups">
        <section v-for="group in filteredFieldGroups" :key="group.name"><h3>{{ group.name }}</h3><div><label v-for="field in group.fields" :key="field.key"><input v-model="draftFields" type="checkbox" :value="field.key" :disabled="field.key === 'issueId'">{{ field.title }}</label></div></section>
      </div>
    </a-modal>

    <a-modal v-model:open="templateModalOpen" title="保存字段模板" ok-text="保存" cancel-text="取消" @ok="saveFieldTemplate">
      <p class="template-modal-note">当前已选 {{ selectedFields.length }} 个字段；使用相同名称会覆盖原模板。</p>
      <a-input v-model:value="templateName" :maxlength="30" show-count placeholder="例如：运营日常明细" @press-enter="saveFieldTemplate" />
      <a-checkbox v-model:checked="templatePublic" class="template-public-check">公开模板（其他账号可使用，但不能修改）</a-checkbox>
    </a-modal>

    <a-drawer v-model:open="ticketOpen" title="出票记录完整信息" width="720">
      <a-spin :spinning="ticketLoading" tip="正在读取MySQL明细">
        <template v-if="ticket?.record">
          <div class="ticket-heading"><div><strong>出票ID {{ ticket.record.issueId }}</strong><span>订单ID {{ ticket.record.orderId ?? '—' }}</span></div><a-switch v-model:checked="showEmptyFields" size="small" /><span>显示空字段</span></div>
          <div class="ticket-core">
            <div><span>航司 / 平台</span><b>{{ ticket.record.airline ?? '—' }} / {{ ticket.record.platform ?? '—' }}</b></div>
            <div><span>出票时间</span><b>{{ ticket.record.issueTicketTime ?? '—' }}</b></div>
            <div><span>最终使用智能</span><b>{{ ticket.record.smartConfirm || '未使用' }}</b></div>
            <div><span>预估利润</span><b>{{ money(ticket.record.issueProfit) }} 元</b></div>
          </div>
          <div class="ticket-groups">
            <details v-for="group in ticketGroups" :key="group.name" :open="group.name === '智能状态' || group.name === '智能及PNR信息'">
              <summary>{{ group.name }}<small>{{ group.fields.length }} 个字段</small></summary>
              <dl><template v-for="field in group.fields" :key="field.key"><dt>{{ field.title }}</dt><dd>{{ formatDetail(ticket.record[field.key], field.valueType) }}</dd></template></dl>
            </details>
          </div>
          <p class="ticket-note">参与、成功与最终使用均直接展示明细表字段，未构造源表中不存在的任务事件。</p>
        </template>
        <a-empty v-else-if="!ticketLoading" :description="ticket?.error || '未找到该出票记录'" />
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Drawer as ADrawer, Empty as AEmpty, message, Modal, Pagination as APagination } from 'ant-design-vue'
import { ArrowLeftOutlined, DeleteOutlined, DownloadOutlined, SaveOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import SmartAnalysisFilters from '@/components/SmartAnalysisFilters.vue'
import { smartAnalysisApi, type SmartDetailColumn, type SmartDetailData, type SmartDetailValueType, type SmartStage, type SmartTicketData, type SmartType, type SmartViewTemplate } from '@/api/smartAnalysis'
import { useSmartAnalysisStore } from '@/stores/smartAnalysis'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import { useAuthStore } from '@/stores/auth'
import { guardSmartExport } from '@/utils/smartExportGuard'
import { loadViewTemplates } from '@/utils/smartViewTemplates'

const DEFAULT_FIELDS = ['issueId', 'otaOrderNo', 'issueTicketNo', 'airline', 'platform', 'issueTicketTime', 'smartConfirm', 'issueProfit']
const FIELD_CATEGORY_ORDER = ['订单与出票', '航程信息', '人员信息', '智能及PNR信息', '智能状态', '金额与派生字段']
type DetailTemplateValue = { fields: string[] } & Record<string, unknown>
const isDetailTemplateValue = (value: unknown): value is DetailTemplateValue => Boolean(
  value && typeof value === 'object' && Array.isArray((value as DetailTemplateValue).fields)
  && (value as DetailTemplateValue).fields.every(item => typeof item === 'string'),
)
const store = useSmartAnalysisStore()
const authStore = useAuthStore()
const pageState = store.pages.detail
const route = useRoute()
const router = useRouter()
const data = ref<SmartDetailData>()
const loading = ref(false)
const exporting = ref(false)
const exportScope = ref<'visible' | 'all'>('visible')
const page = ref(1)
const pageSize = ref(20)
const stage = ref<SmartStage>('all')
const fieldModalOpen = ref(false)
const fieldSearch = ref('')
const selectedFields = ref<string[]>(loadSavedFields())
const draftFields = ref<string[]>([...selectedFields.value])
const fieldTemplates = ref<SmartViewTemplate<DetailTemplateValue>[]>([])
const selectedTemplateId = ref<number>()
const templateModalOpen = ref(false)
const templateName = ref('')
const templatePublic = ref(false)
const ticketOpen = ref(false)
const ticketLoading = ref(false)
const ticket = ref<SmartTicketData>()
const showEmptyFields = ref(false)
const integer = new Intl.NumberFormat('zh-CN')
const currency = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const exportScopeOptions = [{ label: '当前显示字段', value: 'visible' }, { label: '全部字段', value: 'all' }]
const drillContext = computed(() => String(route.query.drill || '') === '1' ? store.drillContext : null)
const typeLabel = computed(() => ({ all: '智能整体', down: '智能降舱', void: '智能废票' }[pageState.smartType]))
const stageOptions = computed(() => [
  { label: '全部出票（不区分智能类型）', value: 'all' },
  { label: `${typeLabel.value}参与`, value: 'participation' },
  { label: `${typeLabel.value}未参与`, value: 'unparticipated' },
  { label: `${typeLabel.value}成功`, value: 'success' },
  { label: `${typeLabel.value}使用`, value: 'use' },
  { label: `${typeLabel.value}参与但未成功`, value: 'unsuccessful' },
  { label: `${typeLabel.value}成功但未使用`, value: 'unused' },
  { label: '退票中/已退票（不区分智能类型）', value: 'refund' },
])
const selectedTemplate = computed(() => fieldTemplates.value.find(item => item.id === selectedTemplateId.value))
const templateOptions = computed(() => [
  { label: '私人模板', options: fieldTemplates.value.filter(item => item.isOwner && !item.isPublic).map(item => ({ value: item.id, label: item.name })) },
  { label: '我的公共模板', options: fieldTemplates.value.filter(item => item.isOwner && item.isPublic).map(item => ({ value: item.id, label: item.name })) },
  { label: '公共模板', options: fieldTemplates.value.filter(item => !item.isOwner && item.isPublic).map(item => ({ value: item.id, label: `${item.name} · ${item.ownerName}` })) },
].filter(group => group.options.length))
const count = (value: number | null | undefined) => value == null ? '—' : integer.format(value)
const money = (value: unknown) => value == null || value === '' ? '—' : currency.format(Number(value))
const yesNo = (value: unknown) => value == null ? '—' : value ? '是' : '否'
const stateLabel = computed(() => data.value?.available && data.value.hasData ? '真实MySQL明细' : data.value?.available ? '当前范围暂无数据' : '数据不可用')
const stateMessage = computed(() => data.value?.available && data.value.hasData ? `${data.value.source} · ${typeLabel.value} · ${stageOptions.value.find(item => item.value === stage.value)?.label}` : data.value?.error || '查询无记录不认定为真实零')
const tableColumns = computed(() => {
  const selected = new Set(selectedFields.value)
  const columns = data.value?.columns?.length ? data.value.columns : data.value?.availableColumns || []
  return columns.filter(column => selected.has(column.key)).map(column => ({ ...column, dataIndex: column.key, fixed: column.key === 'issueId' ? 'left' as const : undefined }))
})
const tableWidth = computed(() => tableColumns.value.reduce((sum, column) => sum + column.width, 0))
const filteredFieldGroups = computed(() => {
  const query = fieldSearch.value.trim().toLowerCase(); const grouped = new Map<string, SmartDetailColumn[]>()
  for (const field of data.value?.availableColumns || []) { if (query && !field.title.toLowerCase().includes(query)) continue; const rows = grouped.get(field.category) || []; rows.push(field); grouped.set(field.category, rows) }
  return [...grouped].map(([name, fields]) => ({ name, fields })).sort((a, b) => FIELD_CATEGORY_ORDER.indexOf(a.name) - FIELD_CATEGORY_ORDER.indexOf(b.name))
})
const ticketGroups = computed(() => {
  const grouped = new Map<string, SmartDetailColumn[]>()
  for (const field of ticket.value?.columns || []) {
    const value = ticket.value?.record?.[field.key]
    if (!showEmptyFields.value && (value == null || value === '')) continue
    const rows = grouped.get(field.category) || []; rows.push(field); grouped.set(field.category, rows)
  }
  return [...grouped].map(([name, fields]) => ({ name, fields })).sort((a, b) => FIELD_CATEGORY_ORDER.indexOf(a.name) - FIELD_CATEGORY_ORDER.indexOf(b.name))
})

function fieldStorageKey() { return `smart-detail-fields-v4:user-${authStore.user?.id ?? 'anonymous'}` }
function normalizeFields(fields: string[]) { return ['issueId', ...fields.filter((key, index) => key !== 'issueId' && typeof key === 'string' && fields.indexOf(key) === index)] }
function persistFields() { localStorage.setItem(fieldStorageKey(), JSON.stringify(selectedFields.value)) }
function loadSavedFields() {
  try {
    const scoped = JSON.parse(localStorage.getItem(fieldStorageKey()) || '[]')
    if (Array.isArray(scoped) && scoped.length) return normalizeFields(scoped)
    const legacy = JSON.parse(localStorage.getItem('smart-detail-fields-v3') || '[]')
    if (Array.isArray(legacy) && legacy.length) return normalizeFields(legacy)
  } catch { /* use defaults */ }
  return [...DEFAULT_FIELDS]
}
function formatDetail(value: unknown, valueType: SmartDetailValueType) { if (value == null || value === '') return '—'; if (valueType === 'boolean') return yesNo(value); if (valueType === 'money') return money(value); return String(value) }
async function load() {
  loading.value = true
  try { data.value = await smartAnalysisApi.details({ ...pageState.applied }, { smartType: pageState.smartType, stage: stage.value, fields: selectedFields.value, page: page.value, pageSize: pageSize.value }) }
  catch (error) { data.value = undefined; message.error(error instanceof Error ? error.message : '出票明细加载失败') }
  finally { loading.value = false }
}
function queryFromStart() { page.value = 1; void load() }
function resetPage() { stage.value = 'all'; page.value = 1; selectedTemplateId.value = undefined; selectedFields.value = [...DEFAULT_FIELDS]; persistFields(); void load() }
function selectDefaults() { draftFields.value = [...DEFAULT_FIELDS] }
function selectAll() { draftFields.value = (data.value?.availableColumns || []).map(field => field.key) }
function applyFields() { selectedFields.value = normalizeFields(draftFields.value); selectedTemplateId.value = undefined; persistFields(); fieldModalOpen.value = false; queryFromStart() }
function openFieldModal() { draftFields.value = [...selectedFields.value]; fieldSearch.value = ''; fieldModalOpen.value = true }
function applyFieldTemplate(templateId?: number) {
  if (!templateId) return
  const template = fieldTemplates.value.find(item => item.id === templateId)
  if (!template) return
  const available = new Set((data.value?.availableColumns || []).map(item => item.key))
  const fields = available.size ? template.value.fields.filter(key => available.has(key)) : template.value.fields
  selectedFields.value = normalizeFields(fields)
  draftFields.value = [...selectedFields.value]
  persistFields()
  queryFromStart()
}
function openTemplateModal() {
  const template = selectedTemplate.value
  templateName.value = template?.isOwner ? template.name : (template ? `${template.name}副本` : '')
  templatePublic.value = template?.isOwner ? template.isPublic : false
  templateModalOpen.value = true
}
async function loadFieldTemplates() {
  try {
    let rows = await smartAnalysisApi.templates<DetailTemplateValue>('detail-fields')
    const ownNames = new Set(rows.filter(item => item.isOwner).map(item => item.name))
    const legacy = loadViewTemplates('detail-fields', authStore.user?.id, isDetailTemplateValue)
    const missing = legacy.filter(item => !ownNames.has(item.name))
    for (const item of missing) {
      await smartAnalysisApi.saveTemplate<DetailTemplateValue>({ scope: 'detail-fields', name: item.name, value: item.value, isPublic: false })
    }
    if (missing.length) rows = await smartAnalysisApi.templates<DetailTemplateValue>('detail-fields')
    fieldTemplates.value = rows
  }
  catch (error) { message.error(error instanceof Error ? error.message : '字段模板加载失败') }
}
async function saveFieldTemplate() {
  try {
    const current = selectedTemplate.value
    const saved = await smartAnalysisApi.saveTemplate<DetailTemplateValue>({
      id: current?.isOwner ? current.id : undefined,
      scope: 'detail-fields', name: templateName.value,
      value: { fields: [...selectedFields.value] }, isPublic: templatePublic.value,
    })
    await loadFieldTemplates()
    selectedTemplateId.value = saved.id
    templateModalOpen.value = false
    message.success(`已保存${saved.isPublic ? '公共' : '私人'}模板“${saved.name}”`)
  } catch (error) { message.warning(error instanceof Error ? error.message : '字段模板保存失败') }
}
function deleteFieldTemplate() {
  const template = selectedTemplate.value
  if (!template?.isOwner) return
  Modal.confirm({ title: '删除字段模板', content: `确定删除“${template.name}”吗？`, okType: 'danger', onOk: () => {
    void smartAnalysisApi.deleteTemplate(template.id).then(async () => {
      selectedTemplateId.value = undefined
      await loadFieldTemplates()
      message.success('字段模板已删除')
    }).catch(error => message.error(error instanceof Error ? error.message : '字段模板删除失败'))
  } })
}
async function openTicket(issueId: unknown) {
  if (issueId == null) return
  ticketOpen.value = true; ticketLoading.value = true; ticket.value = undefined; showEmptyFields.value = false
  try { ticket.value = await smartAnalysisApi.ticket(String(issueId)) }
  catch (error) { message.error(error instanceof Error ? error.message : '出票记录加载失败') }
  finally { ticketLoading.value = false }
}
async function runExport() {
  exporting.value = true
  try {
    const task = await useComprehensiveExportStore().createBackground('smart_details', { ...pageState.applied, smartType: pageState.smartType, stage: stage.value, fields: selectedFields.value, scope: exportScope.value })
    message.success(task.reused ? '相同条件的任务正在进行，已打开导出任务' : '已加入导出任务，可在页头查看进度')
  } catch (error) {
    message.error(error instanceof Error ? error.message : '出票明细导出失败')
  } finally {
    exporting.value = false
  }
}
function exportRows() { guardSmartExport(data.value?.total ?? 0, runExport) }
async function backToSource() { const context = store.restoreDrillSource(); if (!context) return; await router.push(context.sourcePath); requestAnimationFrame(() => window.scrollTo({ top: context.scrollY })) }

onMounted(() => {
  const queryType = String(route.query.smartType || '') as SmartType; const queryStage = String(route.query.stage || '') as SmartStage
  if (['all', 'down', 'void'].includes(queryType)) pageState.smartType = queryType
  if (stageOptions.value.some(item => item.value === queryStage)) stage.value = queryStage
  if (String(route.query.drill || '') !== '1') store.clearDrill()
  draftFields.value = [...selectedFields.value]; void load(); void loadFieldTemplates()
})
</script>

<style scoped>
.smart-alert { margin: 14px 0; }
.drill-context { margin-bottom: 14px; padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border: 1px solid #bad2f6; border-radius: 10px; background: #f3f8ff; }
.drill-context > div:first-child { display: grid; gap: 3px; }
.drill-context strong { color: #34547f; font-size: 12px; }
.drill-context span { color: #71839a; font-size: 10px; }
.smart-detail-panel { margin-top: 16px; }
.view-template-bar { margin-bottom: 14px; padding: 11px 12px; display: flex; align-items: center; gap: 9px; border: 1px solid #dbe7f7; border-radius: 8px; background: #f6f9fe; }
.view-template-bar strong { color: #3e526f; font-size: 12px; }
.view-template-bar :deep(.ant-select) { width: 220px; }
.view-template-bar > span { flex: 1; color: #7b899c; font-size: 10px; text-align: right; }
.template-modal-note { color: #718096; font-size: 12px; }
.template-public-check { display: block; margin-top: 14px; color: #5f6d82; }
.detail-toolbar { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin-bottom: 16px; }
.detail-toolbar > label { width: 190px; display: grid; gap: 6px; color: #718096; font-size: 11px; }
.detail-toolbar > .ticket-scope { width: 330px; flex: 0 0 330px; }
.ticket-scope :deep(.ant-select) { width: 100%; }
.ticket-scope :deep(.ant-select-selection-item) { padding-inline-end: 28px; }
.detail-toolbar > .export-scope { width: 170px; }
.detail-scope { min-width: 150px; flex: 1; display: flex; align-items: center; gap: 9px; color: #7c899b; font-size: 11px; }
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
.ticket-heading { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.ticket-heading > div { flex: 1; display: grid; gap: 4px; }
.ticket-heading strong { color: #2d3d55; font-size: 18px; }
.ticket-heading span { color: #7d8999; font-size: 11px; }
.ticket-core { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 18px; }
.ticket-core div { padding: 12px; display: grid; gap: 5px; border-radius: 8px; background: #f5f8fc; }
.ticket-core span, .ticket-groups small { color: #8390a2; font-size: 10px; }
.ticket-core b { color: #405069; font-size: 12px; }
.ticket-groups details { border-top: 1px solid #e8edf4; }
.ticket-groups summary { padding: 14px 2px; display: flex; justify-content: space-between; color: #40516a; font-size: 13px; font-weight: 600; cursor: pointer; }
.ticket-groups dl { margin: 0 0 14px; display: grid; grid-template-columns: 180px 1fr; font-size: 11px; }
.ticket-groups dt, .ticket-groups dd { margin: 0; padding: 8px 10px; border-bottom: 1px solid #eef1f5; }
.ticket-groups dt { color: #768398; background: #f8fafc; }
.ticket-groups dd { color: #394a63; word-break: break-all; }
.ticket-note { padding: 11px 12px; color: #708198; font-size: 10px; border-left: 3px solid #6da2ef; background: #f5f9ff; }
@media (max-width: 850px) { .detail-toolbar, .drill-context, .view-template-bar { align-items: stretch; flex-direction: column; } .view-template-bar :deep(.ant-select) { width: 100%; } .view-template-bar > span { text-align: left; } .detail-toolbar > label, .detail-toolbar > .ticket-scope, .detail-toolbar > .export-scope { width: 100%; flex-basis: auto; } .detail-summary-grid, .field-groups section > div, .ticket-core { grid-template-columns: 1fr; } .detail-pagination { align-items: flex-start; flex-direction: column; gap: 12px; } }
</style>

<style>
.ticket-scope-popup { min-width: 330px !important; }
</style>
