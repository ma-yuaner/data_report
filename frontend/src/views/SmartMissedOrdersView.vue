<template>
  <div class="page-wrap missed-orders-page">
    <PageHeader eyebrow="SMART PLACEMENT" title="漏处理订单" description="查询清洗脚本生成的降舱漏处理结果，核对出票证据与投放关联">
      <a-button :loading="loading" @click="refresh"><ReloadOutlined />刷新当前查询</a-button>
    </PageHeader>
    <a-alert v-if="error" type="error" show-icon :message="error" class="page-message" />
    <FilterPanel stacked :instant="false" :loading="loading" @reset="reset">
      <template #period>
        <DateRangeField v-model:start="draft.startDate" v-model:end="draft.endDate" label="出票日期" :disabled="Boolean(draft.otaOrderNo.trim())" />
        <span class="muted">{{ draft.otaOrderNo.trim() ? '订单号精确查询不限制出票日期' : '默认本月＋月初前7天，单次最多366天' }}</span>
      </template>
      <label><span>OTA订单号</span><a-input v-model:value="draft.otaOrderNo" allow-clear :maxlength="50" placeholder="输入完整订单号" @press-enter="query" /></label>
      <label><span>平台</span><a-select v-model:value="draft.platform" allow-clear show-search :options="optionsFor('platform')" option-filter-prop="label" :loading="optionsLoading" placeholder="全部平台" /></label>
      <label><span>航司</span><a-select v-model:value="draft.airline" allow-clear show-search :options="optionsFor('airline')" option-filter-prop="label" placeholder="全部航司" /></label>
      <label><span>政策员</span><a-select v-model:value="draft.operator" allow-clear show-search :options="optionsFor('operator')" option-filter-prop="label" placeholder="全部政策员" /></label>
      <label><span>组别</span><a-select v-model:value="draft.group" allow-clear show-search :options="optionsFor('group')" option-filter-prop="label" placeholder="全部组别" /></label>
      <template #actions>
        <a-button type="primary" :loading="loading" @click="query"><SearchOutlined />查询</a-button>
        <a-button @click="advanced = !advanced">{{ advanced ? '收起更多筛选' : '更多筛选' }}</a-button>
      </template>
      <template #footer>
        <div v-if="advanced" class="advanced-fields">
          <label><span>出发城市</span><a-input v-model:value="draft.depCity" allow-clear :maxlength="3" placeholder="城市三字码" /></label>
          <label><span>到达城市</span><a-input v-model:value="draft.arrCity" allow-clear :maxlength="3" placeholder="城市三字码" /></label>
          <label><span>比价差下限</span><a-input v-model:value="draft.minPrice" allow-clear placeholder="原值，支持负数" /></label>
          <label><span>比价差上限</span><a-input v-model:value="draft.maxPrice" allow-clear placeholder="原值，最多两位小数" /></label>
          <label><span>任务类型</span><a-select v-model:value="draft.jobType" allow-clear :options="optionsFor('jobType')" placeholder="全部任务类型" /></label>
          <label><span>业务类型</span><a-select v-model:value="draft.businessType" allow-clear :options="optionsFor('businessType')" placeholder="全部业务类型" /></label>
        </div>
        <p v-if="optionsError" class="option-error">{{ optionsError }} <a-button size="small" type="link" @click="loadOptions">重试选项</a-button></p>
        <p v-if="optionsTruncated" class="muted">部分下拉选项超过250项，请缩小出票日期；查询及导出不受选项数量限制。</p>
      </template>
    </FilterPanel>
    <a-alert v-if="data?.scopeEmpty" type="warning" show-icon message="当前账号没有可匹配的人员范围" description="请管理员核对ERP员工绑定和收单情况的数据范围；不会按登录昵称推定政策员身份。" class="page-message" />
    <section class="results-panel">
      <div class="results-heading">
        <div><h2>漏处理明细</h2><p>{{ dirty ? '筛选已修改，点击查询后更新结果。' : appliedLabel }}</p></div>
        <a-space wrap>
          <a-select v-model:value="selectedFields" mode="multiple" :options="fieldOptions" :max-tag-count="1" class="column-picker" placeholder="选择显示字段" aria-label="显示字段" />
          <a-button v-if="canExport" :disabled="!data || loading || dirty" :loading="exporting" @click="exportRows"><DownloadOutlined />导出全部明细</a-button>
        </a-space>
      </div>
      <dl class="result-summary">
        <div v-for="item in summaries" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ data ? number(data.summary[item.key]) : '—' }}</dd></div>
      </dl>
      <p class="scope-note">完整保留源记录；同一订单可能存在多条历史记录。比价差展示源值，不作为损失或利润。人员范围沿用“收单情况”配置。</p>
      <a-table row-key="id" :columns="columns" :data-source="data?.rows || []" :loading="loading" :pagination="false" :scroll="{ x: tableWidth, y: 'max(220px, calc(100vh - 510px))' }" @change="changeSort">
        <template #emptyText><a-empty :description="error ? '查询失败，请重试' : data ? '当前条件下没有可见记录' : '正在加载查询结果'" /></template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'otaOrderNo'"><a-button type="link" class="order-link" @click="openDetail(record)">{{ record.otaOrderNo }}</a-button></template>
          <template v-else-if="column.key === 'saleDiffPrice'"><span class="amount">{{ money(record.saleDiffPrice) }}</span></template>
          <template v-else-if="column.key === 'remark'"><button class="remark-link" type="button" @click="openDetail(record)">{{ record.remark || '无备注' }}</button></template>
          <template v-else-if="column.key === 'policyOperatorGroupName'">{{ record.policyOperatorGroupName || '未填写' }}</template>
          <template v-else>{{ record[column.key] ?? '—' }}</template>
        </template>
      </a-table>
      <div class="pagination-row">
        <span>数据行最近更新时间：{{ data?.summary.latestRowUpdatedAt || '暂无' }}；不代表调度成功时间</span>
        <a-pagination :current="data?.page || 1" :page-size="data?.pageSize || 30" :total="data?.total || 0" show-size-changer :page-size-options="['30', '50', '100']" :show-total="paginationTotal" @change="changePage" />
      </div>
    </section>
    <a-drawer v-model:open="detailOpen" title="漏处理订单详情" :width="'min(820px, 100vw)'">
      <a-spin :spinning="detailLoading">
        <a-alert v-if="detailError" type="error" show-icon :message="detailError" />
        <template v-if="detail">
          <div class="detail-actions"><strong>{{ detail.row.otaOrderNo }}</strong><a-button v-if="canSee('smart.details')" @click="openTicket">查看出票明细</a-button><a-button v-if="canSee('smart.placement.orders')" @click="openReceipts">查看收单情况</a-button></div>
          <dl class="detail-grid"><div v-for="field in detailFields" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ field.key === 'saleDiffPrice' ? money(detail.row.saleDiffPrice) : detail.row[field.key] ?? '—' }}</dd></div></dl>
          <section class="detail-section"><h3>完整备注</h3><p class="full-remark">{{ detail.row.remark || '无备注' }}</p></section>
          <section class="detail-section"><h3>同订单历史记录</h3><p class="muted">按平台和订单号精确查询，未自动合并或删除。</p>
            <div v-for="row in detail.history" :key="row.id" class="history-row"><span>记录 {{ row.id }} · 原业务日期 {{ row.businessDate }}</span><span>{{ row.cabin || '—' }} → {{ row.hprCabin || '—' }} · 比价差 {{ money(row.saleDiffPrice) }}</span><span>源更新时间 {{ row.updateTime }}</span></div>
            <p v-if="detail.historyTruncated" class="muted">仅展示最近20条，请按此订单号查询完整列表。</p>
          </section>
          <section class="detail-section"><h3>实际投放关联</h3><p class="muted">{{ detail.matches?.message || '未读取关联信息' }}</p>
            <article v-for="match in detail.matches?.rows || []" :key="match.id" class="history-row"><span>{{ match.taskNo }} · {{ match.opportunityName }}</span><span>政策 {{ match.externalPolicyId }} · 命中 {{ match.matchedAt }}</span><a-button v-if="canSee('smart.placement.policies')" size="small" @click="openPolicy(match.taskId)">查看投放任务</a-button></article>
            <p v-if="detail.matches?.truncated" class="muted">仅显示最近100条关联，请进入收单情况查看。</p>
          </section>
        </template>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import DateRangeField from '@/components/DateRangeField.vue'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import { decimalDisplay } from '@/utils/decimalDisplay'
import { defaultMissedFilters, fetchMissedDetail, fetchMissedOptions, fetchMissedOrders, type MissedDetail, type MissedFilters, type MissedList, type MissedOptions, type MissedOrder } from '@/api/missedOrders'

const router = useRouter(); const auth = useAuthStore()
const canSee = (code: string) => Boolean(auth.user?.isAdmin || auth.user?.menuCodes?.includes(code))
const canExport = computed(() => Boolean(auth.user?.isAdmin || auth.user?.permissions?.includes('smart_placement.missed.export')))
const draft = ref(defaultMissedFilters()); const applied = ref(defaultMissedFilters())
const data = ref<MissedList>(); const loading = ref(false); const exporting = ref(false); const error = ref(''); const advanced = ref(false)
const options = ref<MissedOptions>({}); const optionsLoading = ref(false); const optionsError = ref('')
const detail = ref<MissedDetail>(); const detailOpen = ref(false); const detailLoading = ref(false); const detailError = ref('')
let loadNo = 0; let optionsNo = 0; let detailNo = 0
const dirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(applied.value))
const optionsTruncated = computed(() => Object.values(options.value).some(value => value.truncated))
const summaries = [{ key: 'recordCount', label: '记录数' }, { key: 'orderCount', label: '订单数（按平台去重）' }, { key: 'operatorCount', label: '涉及政策员' }, { key: 'routeCount', label: '涉及城市航线' }] as const
const allFields = [
  { key: 'otaOrderNo', label: 'OTA订单号', width: 220 }, { key: 'platformName', label: '平台', width: 130 }, { key: 'airline', label: '航司', width: 80 },
  { key: 'saleDiffPrice', label: '比价差（原值）', width: 140 }, { key: 'depCity', label: '出发城市', width: 100 }, { key: 'arrCity', label: '到达城市', width: 100 },
  { key: 'cabin', label: '降前舱位', width: 150 }, { key: 'hprCabin', label: '降后舱位', width: 150 }, { key: 'policyOperator', label: '政策员', width: 110 },
  { key: 'policyOperatorGroupName', label: '组别', width: 130 }, { key: 'remark', label: '备注', width: 260 }, { key: 'issueTicketTime', label: '出票时间', width: 180 },
  { key: 'jobTypeName', label: '任务类型', width: 120 }, { key: 'businessTypeName', label: '业务类型', width: 140 }, { key: 'id', label: '原记录ID', width: 110 },
  { key: 'businessDate', label: '原业务日期', width: 120 }, { key: 'createTime', label: '创建时间', width: 180 }, { key: 'updateTime', label: '更新时间', width: 180 },
  { key: 'otaCode', label: '平台代码', width: 120 }, { key: 'companyCode', label: '业务公司代码', width: 130 }, { key: 'analysisCode', label: '分析代码', width: 180 },
  { key: 'jobType', label: '任务类型代码', width: 130 }, { key: 'hprJobBusinessType', label: '业务类型代码', width: 130 }, { key: 'orderSmartConfirmFlag', label: '原智能确认标记', width: 140 },
]
const fieldOptions = allFields.map(field => ({ value: field.key, label: field.label }))
const detailFields = allFields.filter(field => field.key !== 'remark')
const selectedFields = ref(allFields.slice(0, 14).map(field => field.key))
watch(selectedFields, fields => { if (!fields.includes('otaOrderNo')) selectedFields.value = ['otaOrderNo', ...fields] })
const columns = computed(() => allFields.filter(field => selectedFields.value.includes(field.key)).map(field => ({
  title: field.label, key: field.key, dataIndex: field.key, width: field.width,
  align: field.key === 'saleDiffPrice' ? 'right' as const : 'left' as const,
  fixed: field.key === 'otaOrderNo' ? 'left' as const : undefined,
  sorter: ['issueTicketTime', 'saleDiffPrice', 'id'].includes(field.key),
  sortOrder: applied.value.sortBy === field.key ? applied.value.direction === 'asc' ? 'ascend' as const : 'descend' as const : null,
})))
const tableWidth = computed(() => columns.value.reduce((sum, field) => sum + field.width, 0))
const appliedLabel = computed(() => data.value ? applied.value.otaOrderNo ? `订单号 ${applied.value.otaOrderNo} · 不限制出票日期` : `${applied.value.startDate} 至 ${applied.value.endDate} · ${data.value.source}` : '默认本月＋月初前7天')
const number = (value: unknown) => value == null ? '—' : new Intl.NumberFormat('zh-CN').format(Number(value))
const paginationTotal = (total: number) => `共 ${number(total)} 条记录`
const money = decimalDisplay
function optionsFor(key: keyof MissedFilters) {
  const rows = [...(options.value[key]?.rows || [])]; const selected = draft.value[key]
  if (selected && !rows.some(row => row.value === selected)) rows.unshift({ value: selected, label: selected })
  return rows
}
function cleanDraft(): MissedFilters {
  return Object.fromEntries(Object.entries(draft.value).map(([key, value]) => [key, String(value ?? '').trim()])) as unknown as MissedFilters
}
async function loadOptions() {
  const version = ++optionsNo; optionsLoading.value = true; optionsError.value = ''
  try {
    const result = await fetchMissedOptions({ startDate: applied.value.startDate, endDate: applied.value.endDate, otaOrderNo: applied.value.otaOrderNo })
    if (version === optionsNo) options.value = result
  } catch (failure) { if (version === optionsNo) { options.value = {}; optionsError.value = failure instanceof Error ? failure.message : '筛选选项读取失败' } }
  finally { if (version === optionsNo) optionsLoading.value = false }
}
async function load(filters: MissedFilters, page = 1, pageSize = data.value?.pageSize || 30) {
  const version = ++loadNo; loading.value = true; error.value = ''
  const draftAtStart = JSON.stringify(draft.value)
  try {
    const result = await fetchMissedOrders({ ...filters, page, pageSize })
    if (version !== loadNo) return
    data.value = result; applied.value = { ...result.filters }
    if (JSON.stringify(draft.value) === draftAtStart) draft.value = { ...result.filters }
    void loadOptions()
  } catch (failure) { if (version === loadNo) error.value = `${failure instanceof Error ? failure.message : '查询失败'}${data.value ? '；当前保留上次查询结果' : ''}` }
  finally { if (version === loadNo) loading.value = false }
}
function query() { void load(cleanDraft()) }
function refresh() { void load({ ...applied.value }, data.value?.page || 1) }
function reset() { draft.value = defaultMissedFilters(); void load({ ...draft.value }) }
function changePage(page: number, size: number) { void load({ ...applied.value }, size === data.value?.pageSize ? page : 1, size) }
function changeSort(_pagination: unknown, _filters: unknown, sorter: { field?: string; order?: string }) {
  void load({ ...applied.value, sortBy: sorter.order && sorter.field ? sorter.field : 'issueTicketTime', direction: sorter.order === 'ascend' ? 'asc' : 'desc' })
}
async function openDetail(row: MissedOrder) {
  const version = ++detailNo; detailOpen.value = true; detailLoading.value = true; detailError.value = ''; detail.value = undefined
  try { const result = await fetchMissedDetail(row.id); if (version === detailNo) detail.value = result }
  catch (failure) { if (version === detailNo) detailError.value = failure instanceof Error ? failure.message : '详情读取失败' }
  finally { if (version === detailNo) detailLoading.value = false }
}
async function exportRows() {
  if (!data.value || dirty.value || loading.value) return
  exporting.value = true
  try { await useComprehensiveExportStore().createBackground('smart_missed_orders', { ...applied.value }); message.success('已加入页头导出任务，导出全部匹配记录及字段') }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '导出任务创建失败') }
  finally { exporting.value = false }
}
function openTicket() { if (detail.value) void router.push({ path: '/smart-analysis/details', query: { otaOrderNo: detail.value.row.otaOrderNo, platform: detail.value.row.platformName, smartType: 'down', stage: 'all', fromMissed: '1' } }) }
function openReceipts() { if (detail.value) void router.push({ path: '/smart-analysis/placement/orders', query: { otaOrderNo: detail.value.row.otaOrderNo, platform: detail.value.row.platformName } }) }
function openPolicy(taskId: number) { void router.push({ path: '/smart-analysis/placement/policies', query: { taskId: String(taskId) } }) }
onMounted(() => { void load({ ...draft.value }) })
onBeforeUnmount(() => { ++loadNo; ++optionsNo; ++detailNo })
</script>

<style scoped>
.page-message { margin-bottom: 16px; }.muted, .scope-note { color: #69768a; font-size: 12px; line-height: 1.7; }
.advanced-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }.advanced-fields label { display: grid; gap: 6px; min-width: 0; }.advanced-fields label > span { color: #69768a; font-size: 13px; }.advanced-fields :deep(.ant-select) { width: 100%; }
.option-error { color: #c43f4f; margin: 8px 0 0; }.results-panel { min-width: 0; padding: 20px; border: 1px solid #e4e9ef; border-radius: 12px; background: white; }
.results-heading { display: flex; justify-content: space-between; gap: 16px; align-items: center; flex-wrap: wrap; }.results-heading h2 { margin: 0 0 5px; font-size: 16px; }.results-heading p { margin: 0; color: #69768a; font-size: 12px; }.column-picker { width: 240px; }
.result-summary { display: flex; gap: 36px; flex-wrap: wrap; margin: 20px 0 12px; }.result-summary dt { color: #69768a; font-size: 13px; }.result-summary dd { margin: 5px 0 0; font-size: 23px; font-variant-numeric: tabular-nums; }
.scope-note { margin: 0 0 14px; }.amount { font-variant-numeric: tabular-nums; }.order-link { padding: 0; height: auto; white-space: normal; text-align: left; overflow-wrap: anywhere; }.remark-link { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-align: left; border: 0; background: none; padding: 0; color: #52647b; cursor: pointer; overflow-wrap: anywhere; }.remark-link:focus-visible { outline: 2px solid #1677ff; }
.pagination-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; padding-top: 16px; }.pagination-row > span { color: #69768a; font-size: 12px; }
.detail-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; }.detail-actions strong { flex: 1; overflow-wrap: anywhere; }.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; }.detail-grid dt { color: #69768a; font-size: 12px; }.detail-grid dd { margin: 4px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }.detail-section { margin-top: 24px; border-top: 1px solid #edf0f5; padding-top: 16px; }.detail-section h3 { font-size: 15px; }.full-remark { white-space: pre-wrap; overflow-wrap: anywhere; }.history-row { display: grid; gap: 5px; padding: 10px 0; border-bottom: 1px solid #edf0f5; font-size: 13px; overflow-wrap: anywhere; }
@media (max-width: 760px) { .results-panel { padding: 14px; }.result-summary { gap: 18px; }.detail-grid { grid-template-columns: 1fr; }.column-picker { width: 200px; } }
</style>
