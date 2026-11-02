<template>
  <section>
    <a-alert type="info" show-icon class="diagnosis-alert" message="按航司、出发/到达范围、航程及航段类型横向比较当前可见平台" description="基于成功投放政策识别零单，异常订单仍算实际来单。无单表示本轮监控下的待核查信号；国家/城市范围按配置范围展示，不展开为所有机场组合。" />
    <a-alert v-if="error" type="error" show-icon class="diagnosis-alert" :message="error" />
    <div class="diagnosis-summary">
      <button v-for="item in cards" :key="item.key" type="button" @click="selectProblem(item.key)"><span>{{ item.title }}</span><strong>{{ data?.summary[item.key] ?? 0 }}</strong></button>
    </div>
    <a-card :bordered="false">
      <FilterPanel stacked :instant="false" :loading="loading" @reset="reset">
        <label><span>观察窗口</span><a-select v-model:value="filters.days" :options="[3,7,14,30].map(value => ({ value, label: `${value} 天` }))" /></label>
        <label><span>航司</span><a-input v-model:value="filters.airline" allow-clear placeholder="航司编码" @press-enter="query(1)" /></label>
        <label><span>航线／机会</span><a-input v-model:value="filters.keyword" allow-clear placeholder="出发/到达代码、机会名称" @press-enter="query(1)" /></label>
        <label><span>问题类型</span><a-select v-model:value="filters.problem" :options="problemOptions" /></label>
        <template #actions><a-button type="primary" :loading="loading" @click="query(1)">查询</a-button></template>
      </FilterPanel>
      <a-alert v-if="data && !data.dataHealthy" type="warning" show-icon class="diagnosis-alert" message="采集或匹配最近运行未确认正常，无单政策暂标记“数据待核对”" :description="healthText" />
      <a-alert v-else-if="updating" type="info" show-icon class="diagnosis-alert" message="采集或匹配正在刷新，当前沿用最近成功数据" :description="healthText" />
      <div v-if="data" class="diagnosis-caption">{{ data.scopeNote }} · 本次 {{ data.days }} 天窗口 {{ data.windowStart }} 至 {{ data.asOf }} · 条件有差异时需展开核对；范围可能重叠，订单不可跨行相加。</div>
      <a-table :loading="loading" :columns="columns" :data-source="data?.rows || []" row-key="key" :pagination="false" :scroll="{ x: tableWidth, y: 470 }" size="middle">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'route'">
            <div class="route-name"><strong>{{ record.airlineCode || '不限航司' }} · {{ routeName(record) }}</strong><span>{{ tripName(record.journeyType) }} · {{ record.segmentType || '不限航段' }}</span><a-tag v-if="record.mixedConditions" color="orange">平台条件有差异</a-tag></div>
          </template>
          <template v-else-if="column.key === 'diagnosis'">
            <div class="route-name"><a-tag :color="meta(record.diagnosis).color">{{ meta(record.diagnosis).label }}</a-tag><a-tag v-if="record.hasInterruption" color="orange">曾有单后中断</a-tag><a-tag v-if="record.due" color="red">到期需复查</a-tag></div>
          </template>
          <template v-else>
            <button v-if="record.cells[column.platform]" class="platform-cell" type="button" @click="openCell(record, record.cells[column.platform])">
              <a-tag :color="meta(record.cells[column.platform].state).color">{{ meta(record.cells[column.platform].state).label }}</a-tag>
              <strong>{{ inactive(record.cells[column.platform].state) ? '未纳入当前比较' : record.cells[column.platform].periodOrderCount === null ? '范围受限' : `${record.cells[column.platform].periodOrderCount} 单` }}</strong>
              <span v-if="!inactive(record.cells[column.platform].state)">正常分类 {{ record.cells[column.platform].assessmentOrderCount ?? '—' }} 单</span>
              <span>最后来单 {{ time(record.cells[column.platform].lastOrderAt) }}</span>
              <span>{{ record.cells[column.platform].policies.length }} 条政策 · 点击跟进</span>
            </button>
            <span v-else class="not-placed">当前可见范围未配置</span>
          </template>
        </template>
        <template #emptyText><a-empty :description="error || '当前条件没有可见投放范围'" /></template>
      </a-table>
      <a-pagination class="diagnosis-pagination" :current="page" :page-size="pageSize" :total="data?.total || 0" :show-total="totalLabel" :show-size-changer="true" :page-size-options="['20','50']" @change="changePage" />
    </a-card>

    <a-drawer v-model:open="drawerOpen" title="平台收单诊断与跟进" width="min(900px, 96vw)">
      <template v-if="selectedCell && selectedRoute">
        <a-alert type="info" show-icon :message="`${routeName(selectedRoute)} · ${selectedCell.platform} · ${meta(selectedCell.state).label}`" description="观察起点取实际投放、生效、当前规则版本及最近恢复时间中的较晚者。暂停/过期不参与当前零单比较；不能据此认定市场没有需求。" />
        <article v-for="policy in selectedCell.policies" :key="policy.taskId" class="diagnostic-policy">
          <header><div><strong>{{ policy.name }}</strong><span>{{ policy.taskNo }} · {{ policy.externalPolicyId || '尚未投放' }}</span></div><a-tag :color="meta(policy.state).color">{{ meta(policy.state).label }}</a-tag></header>
          <a-descriptions size="small" :column="2">
            <a-descriptions-item label="负责人 / 站点">{{ policy.ownerName || '未分配' }} / {{ policy.siteName || '全部站点' }}</a-descriptions-item>
            <a-descriptions-item label="观察起点">{{ time(policy.observedFrom) }}（{{ policy.observedDays ?? '—' }}天）</a-descriptions-item>
            <a-descriptions-item label="窗口实际订单">{{ policy.periodOrderCount ?? '收单权限受限' }}</a-descriptions-item>
            <a-descriptions-item label="本轮最后来单">{{ time(policy.lastOrderAt) }}</a-descriptions-item>
            <a-descriptions-item label="距来单/观察起点">{{ policy.noOrderDays ?? '—' }}天</a-descriptions-item>
            <a-descriptions-item label="规则最近运行">{{ time(policy.lastRunAt) }}</a-descriptions-item>
            <a-descriptions-item v-for="(value, key) in policy.conditions" :key="key" :label="conditionLabels[key] || key">{{ value || '不限／未填写' }}</a-descriptions-item>
          </a-descriptions>
          <div v-if="policy.followupId" class="followup-note"><a-tag :color="policy.due ? 'red' : 'blue'">{{ followupLabel(policy.followup.status) }}</a-tag><strong>{{ reasonLabel(policy.followup.reason) }}</strong><p>{{ policy.followup.note }}</p><small>复查：{{ time(policy.followup.nextReviewAt) }} · {{ policy.followupRecordedBy }} · {{ time(policy.followupRecordedAt) }}</small></div>
          <a-space wrap><a-button @click="emit('open-task', policy.taskId)">查看政策与处理</a-button><a-button v-if="canFollowup" type="primary" @click="openFollowup(policy)">登记跟进</a-button><a-button v-if="canOrders" :disabled="!policy.executionId || !policy.orderScopeComplete || !policy.observedFrom || policy.observedFrom > policy.observedUntil" @click="openOrders(policy)">查看窗口收单</a-button></a-space>
        </article>
      </template>
    </a-drawer>
    <FormDialog :open="!!editing" title="登记航线/平台跟进" :width="620" :busy="saving" :dirty="dirty" :error="saveError" @update:open="closeForm" @submit="save">
      <a-alert type="info" show-icon message="“已调整”和“建议挂起”仅记录跟进结论；调整或暂停仍需在原政策流程登记，系统不会自动更改外部政策。" />
      <a-form layout="vertical" class="followup-form">
        <a-form-item label="核查方向" required><a-select v-model:value="form.reason" :options="reasonOptions" :disabled="saving" /></a-form-item>
        <a-form-item label="跟进状态" required><a-select v-model:value="form.status" :options="followupOptions" :disabled="saving" /></a-form-item>
        <a-form-item label="核查事实、证据及下一步" required><a-textarea v-model:value="form.note" :rows="4" :maxlength="1000" show-count :disabled="saving" /></a-form-item>
        <a-form-item label="下次复查时间" :required="form.status !== 'RESOLVED'"><DateField v-model="form.nextReviewAt" with-time :disabled="saving || form.status === 'RESOLVED'" /></a-form-item>
      </a-form>
    </FormDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import FilterPanel from '@/components/FilterPanel.vue'
import FormDialog from '@/components/FormDialog.vue'
import DateField from '@/components/DateField.vue'
import { useAuthStore } from '@/stores/auth'
import { fetchRouteDiagnosis, saveRouteFollowup, type DiagnosticCell, type DiagnosticPolicy, type DiagnosticRoute, type RouteDiagnosisResult } from '@/api/placementDiagnosis'

const emit = defineEmits<{ 'open-task': [id: number] }>()
const auth = useAuthStore(); const router = useRouter()
const canFollowup = computed(() => auth.user?.isAdmin || auth.user?.permissions?.includes('smart_placement.orders.attention'))
const canOrders = computed(() => auth.user?.isAdmin || auth.user?.menuCodes?.includes('smart.placement.orders'))
const filters = ref({ days: 7, airline: '', keyword: '', problem: 'ALL' })
const data = ref<RouteDiagnosisResult>(); const error = ref(''); const loading = ref(false)
const page = ref(1); const pageSize = ref(20)
const drawerOpen = ref(false); const selectedCell = ref<DiagnosticCell>(); const selectedRoute = ref<DiagnosticRoute>()
const editing = ref<DiagnosticPolicy>(); const saving = ref(false); const saveError = ref('')
const form = ref({ reason: 'PENDING_CHECK', status: 'OPEN', note: '', nextReviewAt: '' })
const initialForm = ref('')
const dirty = computed(() => Boolean(editing.value && JSON.stringify(form.value) !== initialForm.value))
const totalLabel = (total: number) => `共 ${total} 个投放范围`
const states: Record<string, { label: string; color: string }> = {
  PLATFORM_GAP: { label: '部分平台无单', color: 'orange' }, ALL_NO_ORDERS: { label: '已投放平台均无单', color: 'red' },
  INTERRUPTED: { label: '本轮收单中断', color: 'orange' }, NO_ORDERS: { label: '本轮持续无单', color: 'red' },
  DATA_CHECK: { label: '数据待核对', color: 'gold' }, RESTRICTED: { label: '收单权限受限', color: 'default' },
  OBSERVING: { label: '观察中/未到阈值', color: 'blue' }, RECEIVING: { label: '窗口内有单', color: 'green' },
  SCHEDULED: { label: '尚未生效', color: 'blue' }, PAUSED: { label: '已暂停/停止', color: 'default' },
  EXPIRED: { label: '已过期', color: 'default' }, NOT_PLACED: { label: '尚未投放', color: 'default' },
  PARTIAL_NO_ORDERS: { label: '无单政策待复核', color: 'orange' },
}
const meta = (key: string) => states[key] || { label: key, color: 'default' }
const inactive = (state: string) => ['NOT_PLACED', 'PAUSED', 'EXPIRED', 'SCHEDULED'].includes(state)
const cards = [{ key: 'PLATFORM_GAP', title: '其他平台有单' }, { key: 'ALL_NO_ORDERS', title: '已投放平台均无单' }, { key: 'INTERRUPTED', title: '收单中断' }, { key: 'due', title: '到期复查' }]
const problemOptions = [{ value: 'ALL', label: '全部诊断' }, ...cards.map(item => ({ value: item.key === 'due' ? 'DUE' : item.key, label: item.title })), { value: 'DATA_CHECK', label: '数据待核对' }, { value: 'OBSERVING', label: '观察中' }]
const reasonOptions = [{ value: 'PENDING_CHECK', label: '待核实' }, { value: 'NOT_VISIBLE', label: '未展示' }, { value: 'RANKING', label: '排位偏后' }, { value: 'PRICE', label: '价格无优势' }, { value: 'CONDITIONS', label: '投放条件限制' }, { value: 'INVENTORY', label: '库存问题' }, { value: 'OTHER', label: '其他原因' }]
const followupOptions = [{ value: 'OPEN', label: '待跟进' }, { value: 'OBSERVING', label: '继续观察' }, { value: 'ADJUSTED', label: '已调整待复查' }, { value: 'SUSPEND_SUGGESTED', label: '建议挂起' }, { value: 'RESOLVED', label: '本次跟进完成' }]
const reasonLabel = (value: unknown) => reasonOptions.find(item => item.value === value)?.label || '待核实'
const followupLabel = (value: unknown) => followupOptions.find(item => item.value === value)?.label || '待跟进'
const conditionLabels: Record<string, string> = { include_cabins: '包含舱位', exclude_cabins: '排除舱位', product_type: '产品类型', order_source: '订单来源', travel_start_date: '旅行开始', travel_end_date: '旅行结束', order_start_date: '销售开始', order_end_date: '销售结束', advance_sale_days: '提前销售天数', flight_nos: '航班号', loss_threshold_min: '亏损阈值下限', loss_threshold_max: '亏损阈值上限' }
const time = (value: unknown) => value ? String(value).replace('T', ' ').slice(0, 16) : '未取得'
function location(type: string | null, code: string | null) { return code ? `${({ COUNTRY: '国家', CITY: '城市', AIRPORT: '机场', LEGACY: '历史' } as Record<string,string>)[type || 'LEGACY'] || type} ${code}` : '不限' }
const routeName = (row: DiagnosticRoute) => row.routeText || `${location(row.departureType, row.departureCode)} → ${location(row.arrivalType, row.arrivalCode)}`
const tripName = (type: string | null) => ({ ONE_WAY: '单程', ROUND_TRIP: '往返', MULTI_CITY: '多程' } as Record<string,string>)[type || ''] || type || '不限航程'
const columns = computed(() => [{ title: '航司 / 投放范围', key: 'route', width: 290, fixed: 'left' as const }, { title: '诊断', key: 'diagnosis', width: 180 }, ...(data.value?.platforms || []).map(platform => ({ title: platform, key: `platform:${platform}`, platform, width: 190 }))])
const tableWidth = computed(() => Math.max(1000, 470 + (data.value?.platforms.length || 0) * 190))
const updating = computed(() => Object.values(data.value?.health || {}).some(item => item.code === 'UPDATING'))
const healthText = computed(() => ['FEATURE_ETL', 'RULE_MATCH'].map(kind => {
  const item = data.value?.health[kind]
  return `${kind === 'FEATURE_ETL' ? '采集' : '匹配'}：${item?.message || '未找到运行记录'}${item?.status === 'RUNNING' ? `（开始于 ${item.startedAt || '未知'}）` : ''}；上次成功 ${item?.lastSuccessAt || '尚无记录'}`
}).join('；'))
let sequence = 0
let applied = { ...filters.value }
async function query(target = page.value, useApplied = false) {
  const id = ++sequence; loading.value = true; error.value = ''; page.value = target
  const requested = useApplied ? { ...applied } : { ...filters.value }
  try {
    const result = await fetchRouteDiagnosis({ ...requested, page: target, pageSize: pageSize.value })
    if (id !== sequence) return
    data.value = result; applied = requested
    if (selectedRoute.value && selectedCell.value) {
      const current = result.rows.find(row => row.key === selectedRoute.value?.key)
      const cell = current?.cells[selectedCell.value.platform]
      if (current && cell) { selectedRoute.value = current; selectedCell.value = cell }
      else { drawerOpen.value = false; selectedRoute.value = undefined; selectedCell.value = undefined }
    }
  } catch (reason) { if (id === sequence) { data.value = undefined; error.value = reason instanceof Error ? reason.message : '诊断查询失败' } }
  finally { if (id === sequence) loading.value = false }
}
function reset() { filters.value = { days: 7, airline: '', keyword: '', problem: 'ALL' }; void query(1) }
function selectProblem(value: string) { filters.value.problem = value === 'due' ? 'DUE' : value; void query(1) }
function changePage(current: number, size: number) { const target = size === pageSize.value ? current : 1; pageSize.value = size; void query(target, true) }
function openCell(route: DiagnosticRoute, cell: DiagnosticCell) { selectedRoute.value = route; selectedCell.value = cell; drawerOpen.value = true }
function openOrders(policy: DiagnosticPolicy) {
  const start = [data.value?.windowStart || '', policy.observedFrom || ''].reduce((latest, value) => value > latest ? value : latest, '')
  void router.push({ path: '/smart-analysis/placement/orders', query: { executionId: String(policy.executionId), startDate: start.slice(0, 10), endDate: policy.observedUntil.slice(0, 10), diagnosticFrom: start, diagnosticTo: policy.observedUntil } })
}
function openFollowup(policy: DiagnosticPolicy) {
  editing.value = policy; saveError.value = ''
  form.value = { reason: policy.followup.reason || 'PENDING_CHECK', status: policy.followup.status || 'OPEN', note: policy.followup.note || '', nextReviewAt: (policy.followup.nextReviewAt || '').replace(' ', 'T').slice(0, 16) }
  initialForm.value = JSON.stringify(form.value)
}
function closeForm(open: boolean) { if (!open) editing.value = undefined }
async function save() {
  if (!editing.value || saving.value) return
  if (!form.value.note.trim() || (form.value.status !== 'RESOLVED' && !form.value.nextReviewAt)) { saveError.value = '请填写跟进说明和下次复查时间'; return }
  saving.value = true; saveError.value = ''
  try {
    const result = await saveRouteFollowup(editing.value.taskId, { ...form.value, followupId: editing.value.followupId })
    editing.value.followupId = result.id; editing.value.followup = result
    editing.value = undefined; message.success('跟进记录已保存'); await query(page.value, true)
  } catch (reason) { saveError.value = reason instanceof Error ? reason.message : '保存结果未确认，请刷新记录核对后重试' }
  finally { saving.value = false }
}
onMounted(() => { void query(1) })
</script>

<style scoped>
.diagnosis-alert { margin-bottom: 14px; }.diagnosis-summary { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-bottom: 16px; }
.diagnosis-summary button { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 18px; text-align: left; border: 1px solid #e2e8f0; border-radius: 10px; background: #fff; cursor: pointer; }.diagnosis-summary strong { color: #2456a6; font-size: 24px; }
.diagnosis-caption { margin-bottom: 12px; color: #667085; font-size: 12px; }
.route-name,.platform-cell { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; }.route-name span,.platform-cell span { font-size: 12px; }.platform-cell { width: 100%; padding: 6px; border: 0; background: transparent; text-align: left; cursor: pointer; }.platform-cell:hover { background: #f2f6fc; }.platform-cell:focus-visible,.diagnosis-summary button:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }.not-placed { color: #98a2b3; }.diagnosis-pagination { margin-top: 18px; text-align: right; }
.diagnostic-policy { margin-top: 16px; padding: 16px; border: 1px solid #e2e8f0; border-radius: 10px; }.diagnostic-policy header { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 14px; }.diagnostic-policy header span { display: block; color: #667085; margin-top: 4px; }.followup-note { margin: 10px 0 16px; padding: 12px; background: #f5f8fc; }.followup-note p { white-space: pre-wrap; overflow-wrap: anywhere; }.followup-form { margin-top: 16px; }
@media (max-width: 600px) { .diagnosis-summary { grid-template-columns: repeat(2,minmax(0,1fr)); } }
</style>
