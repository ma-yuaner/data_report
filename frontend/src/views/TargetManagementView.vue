<template>
  <div class="page-wrap target-management-page">
    <PageHeader eyebrow="BUSINESS CONFIGURATION" title="目标管理" description="统一配置平台、GDS、部门与政策员的航段目标，完成进度只读取ETL产出。">
      <a-space>
        <a-button @click="metricDrawerOpen = true"><DatabaseOutlined />指标口径</a-button>
        <a-button type="primary" @click="openCreate"><PlusOutlined />新建目标</a-button>
      </a-space>
    </PageHeader>

    <a-alert v-if="loadError" class="state-alert" type="error" show-icon :message="loadError" description="页面未使用备用演示数据，请修复接口或数据库后重试。" />

    <section class="target-hero">
      <div class="hero-copy">
        <span>当前计划</span><h2>{{ periodLabel }}航段目标</h2>
        <p>{{ dataThroughDate ? `数据统计截止 ${dataThroughDate}` : '完成进度待ETL产出' }} · 完成量不允许页面手工填写</p>
      </div>
      <div class="hero-metrics">
        <article><span>目标航段</span><strong>{{ formatNumber(summary.target) }}</strong><small>{{ summary.configuredCount }} 项已配置</small></article>
        <article><span>累计完成</span><strong>{{ formatNullable(summary.actual) }}</strong><small>{{ summary.completionRate == null ? '待ETL产出' : `完成率 ${percent(summary.completionRate)}` }}</small></article>
        <article :class="{ risk: summary.behind > 0 }"><span>进度落后</span><strong>{{ summary.progressReadyCount ? summary.behind : '--' }}</strong><small>{{ summary.progressReadyCount }} 项已产出进度</small></article>
      </div>
    </section>

    <a-card class="panel-card target-workspace" :bordered="false">
      <div class="target-toolbar">
        <div class="toolbar-fields">
          <a-select v-model:value="selectedPeriod" class="period-select" :options="periodOptions" />
          <a-select v-model:value="selectedStatus" class="status-select" :options="statusOptions" />
          <a-input v-model:value="keyword" allow-clear class="keyword-input" placeholder="搜索平台、GDS、部门或政策员" />
        </div>
        <div class="toolbar-actions"><span>{{ dataThroughDate ? `数据截止：${dataThroughDate}` : '进度数据未产出' }}</span><a-button :loading="loading" @click="loadTargets"><ReloadOutlined />刷新</a-button></div>
      </div>

      <a-tabs v-model:activeKey="activeScene" class="target-tabs">
        <a-tab-pane key="platform"><template #tab><span class="tab-label"><ApartmentOutlined />平台目标</span></template></a-tab-pane>
        <a-tab-pane key="gds"><template #tab><span class="tab-label"><BranchesOutlined />GDS目标</span></template></a-tab-pane>
        <a-tab-pane key="policy"><template #tab><span class="tab-label"><TeamOutlined />部门 / 政策员目标</span></template></a-tab-pane>
      </a-tabs>
      <div class="tab-guidance"><div><strong>{{ sceneMeta.title }}</strong><span>{{ sceneMeta.description }}</span></div><a-tag color="blue">{{ sceneMeta.metric }}</a-tag></div>

      <a-table class="target-table" :columns="columns" :data-source="rows" :loading="loading" row-key="id" size="middle" :pagination="{ pageSize: 8, showSizeChanger: false }" :scroll="{ x: tableWidth }">
        <template #emptyText><a-empty description="当前条件下尚未配置目标" /></template>
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'object'">
            <div class="object-cell"><span class="object-mark" :class="`mark-${record.scene}`">{{ objectMark(record) }}</span><div><strong>{{ objectName(record) }}</strong><small>{{ objectSubline(record) }}</small></div></div>
          </template>
          <template v-else-if="column.key === 'owner'"><div class="stack-cell"><strong>{{ record.owner }}</strong><small>{{ record.department }}</small></div></template>
          <template v-else-if="column.key === 'metric'"><div class="metric-cell"><span>{{ record.metric }}</span><small>{{ record.metricCode }} / {{ record.metricVersion }}</small></div></template>
          <template v-else-if="column.key === 'target'">{{ formatNumber(record.target) }}</template>
          <template v-else-if="column.key === 'actual'"><strong class="actual-value">{{ formatNullable(record.actual) }}</strong></template>
          <template v-else-if="column.key === 'yesterday'">{{ formatNullable(record.yesterday) }}</template>
          <template v-else-if="column.key === 'profit'">{{ money(record.profit) }}</template>
          <template v-else-if="column.key === 'progress'">
            <div v-if="record.completionRate != null" class="progress-cell">
              <a-progress :percent="progressPercent(record)" :status="record.expectedRate == null || record.completionRate >= record.expectedRate ? 'normal' : 'exception'" size="small" />
              <small>{{ record.expectedRate == null ? '正常进度待产出' : `正常进度 ${percent(record.expectedRate)}` }}</small>
            </div>
            <a-tag v-else>待ETL产出</a-tag>
          </template>
          <template v-else-if="column.key === 'pace'"><a-tag :color="pace(record).color">{{ pace(record).text }}</a-tag></template>
          <template v-else-if="column.key === 'status'"><a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag></template>
          <template v-else-if="String(column.key).startsWith('gds-')">
            <div v-if="gdsMeasure(record, String(column.key))" class="gds-pair"><strong>{{ formatNullable(gdsMeasure(record, String(column.key))?.actual) }}</strong><small>/ {{ formatNumber(gdsMeasure(record, String(column.key))?.target ?? 0) }}</small></div>
            <span v-else>--</span>
          </template>
          <template v-else-if="column.key === 'actions'"><a-space size="small"><a-button type="link" size="small" @click="openDetail(record)"><EyeOutlined />详情</a-button><a-button type="link" size="small" @click="openEdit(record)"><EditOutlined />编辑</a-button></a-space></template>
        </template>
      </a-table>
    </a-card>

    <a-drawer v-model:open="editorOpen" :title="editingId ? '编辑目标' : '新建目标'" width="560" :destroy-on-close="false">
      <a-alert type="info" show-icon message="目标值保存后立即写入数据库；完成进度由后续ETL独立产出。" class="drawer-alert" />
      <a-form layout="vertical">
        <div class="form-grid two"><a-form-item label="目标场景"><a-input :value="sceneMeta.title" disabled /></a-form-item><a-form-item label="目标月份"><a-input v-model:value="form.period" type="month" /></a-form-item></div>
        <div class="form-grid two">
          <a-form-item label="归属部门"><a-auto-complete v-model:value="form.departmentName" :options="departmentSelectOptions" placeholder="选择或输入真实部门" @select="selectDepartment" /></a-form-item>
          <a-form-item label="责任人"><a-select v-model:value="form.ownerUserId" show-search option-filter-prop="label" :options="userSelectOptions" placeholder="请选择系统用户" @change="selectOwner" /></a-form-item>
        </div>
        <a-form-item v-if="activeScene === 'platform'" label="平台"><a-select v-model:value="form.platformCode" show-search option-filter-prop="label" :options="platformSelectOptions" placeholder="请选择真实平台" @change="selectPlatform" /></a-form-item>
        <a-form-item v-if="activeScene === 'gds'" label="GDS"><a-select v-model:value="form.gdsCode" show-search option-filter-prop="label" :options="gdsSelectOptions" placeholder="请选择GDS" /></a-form-item>
        <template v-if="activeScene === 'policy'">
          <a-form-item label="政策员 / 政策组"><a-auto-complete v-model:value="form.policyName" :options="policySelectOptions" placeholder="选择或输入真实政策员/政策组" @select="selectPolicy" /></a-form-item>
          <div class="gds-target-editor"><label v-for="code in policyGdsCodes" :key="code"><span>{{ code }}目标</span><a-input-number v-model:value="form.gdsTargets[code]" :min="0" :step="1000" /></label></div>
        </template>
        <template v-else>
          <a-form-item label="指标口径"><a-select v-model:value="form.metricCode" :options="metricSelectOptions" /></a-form-item>
          <a-form-item label="目标航段数"><a-input-number v-model:value="form.target" :min="0" :step="1000" class="full-width" /></a-form-item>
        </template>
        <div class="form-grid two"><a-form-item label="状态"><a-select v-model:value="form.status" :options="editStatusOptions" /></a-form-item><a-form-item label="配置来源"><a-input value="手工配置" disabled /></a-form-item></div>
        <a-form-item label="说明"><a-textarea v-model:value="form.remark" :rows="3" placeholder="填写调整原因或业务说明" /></a-form-item>
      </a-form>
      <div class="drawer-actions"><a-button @click="editorOpen = false">取消</a-button><a-button type="primary" :loading="saving" @click="submitTarget">保存目标</a-button></div>
    </a-drawer>

    <a-drawer v-model:open="detailOpen" title="目标进度详情" width="520">
      <template v-if="detailRow">
        <div class="detail-hero"><span>{{ sceneName(detailRow.scene) }}</span><h2>{{ objectName(detailRow) }}</h2><p>{{ detailRow.period }} · {{ detailRow.metric }}</p></div>
        <a-descriptions bordered size="small" :column="1">
          <a-descriptions-item label="归属部门">{{ detailRow.department }}</a-descriptions-item><a-descriptions-item label="责任人">{{ detailRow.owner }}</a-descriptions-item>
          <a-descriptions-item label="目标航段">{{ formatNumber(detailRow.target) }}</a-descriptions-item><a-descriptions-item label="累计完成">{{ formatNullable(detailRow.actual) }}</a-descriptions-item>
          <a-descriptions-item label="昨日完成">{{ formatNullable(detailRow.yesterday) }}</a-descriptions-item><a-descriptions-item label="实际 / 正常进度">{{ detailRow.completionRate == null ? '--' : percent(detailRow.completionRate) }} / {{ detailRow.expectedRate == null ? '--' : percent(detailRow.expectedRate) }}</a-descriptions-item>
          <a-descriptions-item label="累计利润">{{ money(detailRow.profit) }}</a-descriptions-item><a-descriptions-item label="数据状态">{{ dataStatusLabel(detailRow.dataStatus) }}{{ detailRow.dataThroughDate ? ` · ${detailRow.dataThroughDate}` : '' }}</a-descriptions-item>
        </a-descriptions>
      </template>
    </a-drawer>

    <a-drawer v-model:open="metricDrawerOpen" title="指标口径" width="600">
      <a-empty v-if="!metrics.length" description="未查询到已启用指标" />
      <div v-else class="metric-guide"><article v-for="item in metrics" :key="`${item.code}-${item.version}`"><div><strong>{{ item.name }}</strong><code>{{ item.code }} / {{ item.version }}</code></div><p>{{ item.definition }}</p><p v-if="item.filterDescription" class="filter-description">{{ item.filterDescription }}</p><a-tag>{{ item.supportedScenes.join('、') }}</a-tag></article></div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ApartmentOutlined, BranchesOutlined, DatabaseOutlined, EditOutlined, EyeOutlined, PlusOutlined, ReloadOutlined, TeamOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { fetchTargetMetrics, fetchTargetOptions, fetchTargets, saveTarget, type TargetMetric, type TargetOptions, type TargetRow, type TargetStatus } from '@/api/targetManagement'

type SceneKey = 'platform' | 'gds' | 'policy'
type EditableStatus = 'ACTIVE' | 'DRAFT' | 'PAUSED'
const sceneApi: Record<SceneKey, 'PLATFORM' | 'GDS' | 'POLICY'> = { platform: 'PLATFORM', gds: 'GDS', policy: 'POLICY' }
const policyGdsCodes = ['1A', '1G', '1E', '1S']
const today = new Date()
const currentPeriod = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
const activeScene = ref<SceneKey>('platform')
const selectedPeriod = ref(currentPeriod)
const selectedStatus = ref('ALL')
const keyword = ref('')
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const rows = ref<TargetRow[]>([])
const metrics = ref<TargetMetric[]>([])
const options = ref<TargetOptions>({ available: true, platforms: [], gds: [], users: [], departments: [], policyGroups: [] })
const summary = ref({ target: 0, actual: null as number | null, completionRate: null as number | null, behind: 0, configuredCount: 0, progressReadyCount: 0 })
const dataThroughDate = ref<string | null>(null)
const editorOpen = ref(false)
const detailOpen = ref(false)
const metricDrawerOpen = ref(false)
const editingId = ref<string | null>(null)
const detailRow = ref<TargetRow | null>(null)
const form = reactive({
  period: currentPeriod, departmentCode: '', departmentName: '', platformCode: '', platformName: '', gdsCode: '', policyCode: '', policyName: '',
  ownerUserId: undefined as number | undefined, ownerName: '', metricCode: '', metricVersion: 'V1', target: 0, status: 'ACTIVE' as EditableStatus, remark: '',
  itemId: undefined as number | undefined, itemIds: {} as Record<string, number>, gdsTargets: Object.fromEntries(policyGdsCodes.map(code => [code, 0])) as Record<string, number>,
})

const sceneMetas: Record<SceneKey, { title: string; description: string; metric: string }> = {
  platform: { title: '平台目标', description: '按真实OTA平台配置月度航段目标，后续由ETL回写利润和进度。', metric: '指标来自已启用口径表' },
  gds: { title: 'GDS目标', description: '按GDS、部门及责任人配置目标，可选择当前场景支持的指标口径。', metric: '支持口径由指标定义表决定' },
  policy: { title: '部门 / 政策员目标', description: '按部门与政策员/政策组配置1A、1G、1E、1S月度目标。', metric: '默认选择POLICY场景的已启用口径' },
}
const sceneMeta = computed(() => sceneMetas[activeScene.value])
const periodLabel = computed(() => `${selectedPeriod.value.slice(0, 4)}年${Number(selectedPeriod.value.slice(5))}月`)
const periodOptions = computed(() => Array.from({ length: 13 }, (_, index) => {
  const date = new Date(today.getFullYear(), today.getMonth() + 3 - index, 1)
  const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
  return { value, label: `${date.getFullYear()}年${date.getMonth() + 1}月` }
}))
const statusOptions = [{ value: 'ALL', label: '全部状态' }, { value: 'ACTIVE', label: '执行中' }, { value: 'DRAFT', label: '草稿' }, { value: 'PAUSED', label: '已暂停' }, { value: 'CLOSED', label: '已结束' }, { value: 'VOID', label: '已作废' }]
const editStatusOptions = statusOptions.filter(item => ['ACTIVE', 'DRAFT', 'PAUSED'].includes(item.value))
const platformSelectOptions = computed(() => options.value.platforms.map(item => ({ value: item.code, label: `${item.name} (${item.code})` })))
const gdsSelectOptions = computed(() => options.value.gds.map(item => ({ value: item.code, label: item.name })))
const userSelectOptions = computed(() => options.value.users.map(item => ({ value: item.id, label: `${item.name} (${item.username})` })))
const departmentSelectOptions = computed(() => options.value.departments.map(item => ({ value: item.name, label: item.name })))
const policySelectOptions = computed(() => options.value.policyGroups.map(item => ({ value: item.name, label: item.name })))
const supportedMetrics = computed(() => metrics.value.filter(item => item.supportedScenes.includes(sceneApi[activeScene.value])))
const metricSelectOptions = computed(() => supportedMetrics.value.map(item => ({ value: item.code, label: `${item.name} (${item.code}/${item.version})` })))

const baseColumns = {
  owner: { title: '责任人 / 部门', key: 'owner', width: 140 }, metric: { title: '统计口径', key: 'metric', width: 190 }, target: { title: '目标航段', key: 'target', width: 110, align: 'right' as const }, actual: { title: '累计完成', key: 'actual', width: 110, align: 'right' as const },
  progress: { title: '完成进度', key: 'progress', width: 190 }, pace: { title: '进度判断', key: 'pace', width: 105 }, status: { title: '状态', key: 'status', width: 90 }, actions: { title: '操作', key: 'actions', width: 140, fixed: 'right' as const },
}
const columns = computed(() => activeScene.value === 'policy' ? [
  { title: '政策员 / 政策组', key: 'object', width: 180, fixed: 'left' as const }, baseColumns.owner,
  ...policyGdsCodes.map(code => ({ title: `${code}完成 / 目标`, key: `gds-${code}`, width: 132, align: 'right' as const })), baseColumns.target, baseColumns.actual, baseColumns.progress, baseColumns.pace,
  { title: '累计利润', key: 'profit', width: 110, align: 'right' as const }, baseColumns.status, baseColumns.actions,
] : [
  { title: activeScene.value === 'platform' ? '平台' : 'GDS', key: 'object', width: 180, fixed: 'left' as const }, baseColumns.owner, baseColumns.metric, baseColumns.target, baseColumns.actual,
  { title: '昨日完成', key: 'yesterday', width: 105, align: 'right' as const }, baseColumns.progress, baseColumns.pace,
  ...(activeScene.value === 'platform' ? [{ title: '累计利润', key: 'profit', width: 110, align: 'right' as const }] : []), baseColumns.status, baseColumns.actions,
])
const tableWidth = computed(() => activeScene.value === 'policy' ? 1550 : 1390)

let keywordTimer: ReturnType<typeof setTimeout> | undefined
async function loadTargets() {
  loading.value = true; loadError.value = ''
  try {
    const result = await fetchTargets({ scene: sceneApi[activeScene.value], period: selectedPeriod.value, status: selectedStatus.value, keyword: keyword.value.trim() })
    rows.value = result.rows; summary.value = result.summary; dataThroughDate.value = result.dataThroughDate ?? null
  } catch (error) {
    rows.value = []; summary.value = { target: 0, actual: null, completionRate: null, behind: 0, configuredCount: 0, progressReadyCount: 0 }; dataThroughDate.value = null
    loadError.value = error instanceof Error ? error.message : '目标数据加载失败'
  } finally { loading.value = false }
}
async function loadMeta() {
  try { const [metricRows, optionRows] = await Promise.all([fetchTargetMetrics(), fetchTargetOptions()]); metrics.value = metricRows; options.value = optionRows }
  catch (error) { void message.error(error instanceof Error ? error.message : '目标基础数据加载失败') }
}
function resetForm() {
  Object.assign(form, { period: selectedPeriod.value, departmentCode: '', departmentName: '', platformCode: '', platformName: '', gdsCode: options.value.gds[0]?.code ?? '', policyCode: '', policyName: '', ownerUserId: undefined, ownerName: '', metricCode: supportedMetrics.value[0]?.code ?? '', metricVersion: supportedMetrics.value[0]?.version ?? 'V1', target: 0, status: 'ACTIVE', remark: '', itemId: undefined, itemIds: {} })
  policyGdsCodes.forEach(code => { form.gdsTargets[code] = 0 })
}
function openCreate() { editingId.value = null; resetForm(); editorOpen.value = true }
function openEdit(row: TargetRow) {
  editingId.value = row.id
  Object.assign(form, { period: row.period, departmentCode: row.departmentCode, departmentName: row.department, platformCode: row.platformCode, platformName: row.platform ?? '', gdsCode: row.gds ?? '', policyCode: row.policyCode, policyName: row.policy ?? '', ownerUserId: row.ownerUserId ?? undefined, ownerName: row.owner, metricCode: row.metricCode, metricVersion: row.metricVersion, target: row.target, status: ['ACTIVE', 'DRAFT', 'PAUSED'].includes(row.status) ? row.status : 'ACTIVE', remark: row.remark, itemId: row.itemId, itemIds: { ...row.itemIds } })
  policyGdsCodes.forEach(code => { form.gdsTargets[code] = row.gdsBreakdown?.[code]?.target ?? 0 }); editorOpen.value = true
}
function openDetail(row: TargetRow) { detailRow.value = row; detailOpen.value = true }
function selectDepartment(name: string) { form.departmentCode = options.value.departments.find(item => item.name === name)?.code ?? '' }
function selectPolicy(name: string) { form.policyCode = options.value.policyGroups.find(item => item.name === name)?.code ?? '' }
function selectOwner(id: number) { form.ownerName = options.value.users.find(item => item.id === id)?.name ?? '' }
function selectPlatform(code: string) { form.platformName = options.value.platforms.find(item => item.code === code)?.name ?? '' }
async function submitTarget() {
  if (!form.departmentName.trim() || !form.ownerUserId || !form.ownerName) { void message.warning('请填写归属部门并选择责任人'); return }
  if (activeScene.value === 'platform' && (!form.platformCode || !form.platformName)) { void message.warning('请选择平台'); return }
  if (activeScene.value === 'gds' && !form.gdsCode) { void message.warning('请选择GDS'); return }
  if (activeScene.value === 'policy' && !form.policyName.trim()) { void message.warning('请填写政策员或政策组'); return }
  const total = activeScene.value === 'policy' ? policyGdsCodes.reduce((sum, code) => sum + Number(form.gdsTargets[code] || 0), 0) : Number(form.target || 0)
  if (total <= 0) { void message.warning('目标航段数合计必须大于0'); return }
  const selectedMetric = metrics.value.find(item => item.code === form.metricCode && item.version === form.metricVersion) ?? supportedMetrics.value[0]
  if (!selectedMetric) { void message.warning('当前场景没有可用指标口径'); return }
  saving.value = true
  try {
    await saveTarget({ scene: sceneApi[activeScene.value], period: form.period, departmentCode: form.departmentCode || undefined, departmentName: form.departmentName.trim(), platformCode: form.platformCode || undefined, platformName: form.platformName || undefined, gdsCode: form.gdsCode || undefined, policyGroupCode: form.policyCode || undefined, policyGroupName: form.policyName.trim() || undefined, ownerUserId: form.ownerUserId, ownerName: form.ownerName, metricCode: selectedMetric.code, metricVersion: selectedMetric.version, targetValue: activeScene.value === 'policy' ? undefined : Number(form.target), itemId: editingId.value && activeScene.value !== 'policy' ? form.itemId : undefined, itemIds: activeScene.value === 'policy' ? form.itemIds : undefined, gdsTargets: activeScene.value === 'policy' ? policyGdsCodes.map(code => ({ gdsCode: code, targetValue: Number(form.gdsTargets[code] || 0) })) : undefined, status: form.status, remark: form.remark.trim() })
    editorOpen.value = false; selectedPeriod.value = form.period; await Promise.all([loadTargets(), loadMeta()]); void message.success('目标已写入数据库')
  } catch (error) { void message.error(error instanceof Error ? error.message : '目标保存失败') }
  finally { saving.value = false }
}

function formatNumber(value: number) { return Math.round(Number(value)).toLocaleString('zh-CN') }
function formatNullable(value: number | null | undefined) { return value == null ? '--' : formatNumber(value) }
function percent(value: number) { return `${(Number(value) * 100).toFixed(1)}%` }
function money(value: number | null | undefined) { return value == null ? '--' : `¥${Math.round(value).toLocaleString('zh-CN')}` }
function progressPercent(row: TargetRow) { return Math.max(0, Math.round(Number(row.completionRate ?? 0) * 1000) / 10) }
function pace(row: TargetRow) { if (row.completionRate == null || row.expectedRate == null) return { color: 'default', text: '待产出' }; const gap = (row.completionRate - row.expectedRate) * 100; if (gap >= 3) return { color: 'green', text: `领先 ${gap.toFixed(1)}%` }; if (gap >= 0) return { color: 'blue', text: '进度正常' }; return { color: 'red', text: `落后 ${Math.abs(gap).toFixed(1)}%` } }
function statusLabel(status: TargetStatus) { return ({ ACTIVE: '执行中', DRAFT: '草稿', PAUSED: '已暂停', CLOSED: '已结束', VOID: '已作废' } as const)[status] ?? status }
function statusColor(status: TargetStatus) { return status === 'ACTIVE' ? 'green' : status === 'PAUSED' ? 'orange' : status === 'VOID' ? 'red' : 'default' }
function dataStatusLabel(status: string) { return ({ PENDING_ETL: '待ETL产出', READY: '已产出', PARTIAL: '部分产出', MISSING: '数据缺失' } as Record<string, string>)[status] ?? status }
function sceneName(scene: SceneKey) { return sceneMetas[scene].title }
function objectName(row: TargetRow) { return row.scene === 'platform' ? row.platform || '未命名平台' : row.scene === 'gds' ? row.gds || '未命名GDS' : row.policy || '未命名政策组' }
function objectSubline(row: TargetRow) { return row.scene === 'policy' ? `${row.department} · ${row.owner}` : `${row.department} · ${row.metric}` }
function objectMark(row: TargetRow) { return row.scene === 'platform' ? (row.platform || '平').slice(0, 1) : row.scene === 'gds' ? row.gds || 'G' : '策' }
function gdsMeasure(row: TargetRow, columnKey: string) { return row.gdsBreakdown?.[columnKey.replace('gds-', '')] }

watch([activeScene, selectedPeriod, selectedStatus], () => { void loadTargets() })
watch(keyword, () => { if (keywordTimer) clearTimeout(keywordTimer); keywordTimer = setTimeout(() => void loadTargets(), 350) })
watch(() => form.metricCode, code => { const item = metrics.value.find(metric => metric.code === code); if (item) form.metricVersion = item.version })
onMounted(async () => { await loadMeta(); await loadTargets() })
</script>

<style scoped>
.state-alert { margin-bottom: 14px; }
.target-hero { min-height: 168px; margin-bottom: 16px; padding: 26px 28px; display: grid; grid-template-columns: minmax(300px,.85fr) minmax(560px,1.15fr); align-items: center; gap: 28px; overflow: hidden; position: relative; border-radius: 16px; color: #fff; background: linear-gradient(125deg,#142a49,#1d4c84 60%,#347bd2); box-shadow: 0 14px 34px rgba(31,79,141,.16); }
.target-hero::after { width: 260px; height: 260px; position: absolute; right: -90px; top: -150px; border: 44px solid rgba(255,255,255,.055); border-radius: 50%; content: ''; }
.hero-copy,.hero-metrics { position: relative; z-index: 1; }.hero-copy>span { color: #91bcf5; font-size: 10px; font-weight: 700; letter-spacing: .14em; }.hero-copy h2 { margin: 7px 0 9px; color: #fff; font-size: 25px; }.hero-copy p { margin: 0; color: #c6d8ef; font-size: 12px; line-height: 1.7; }
.hero-metrics { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }.hero-metrics article { min-height: 98px; padding: 17px; display: flex; flex-direction: column; border: 1px solid rgba(255,255,255,.13); border-radius: 11px; background: rgba(255,255,255,.075); backdrop-filter: blur(8px); }.hero-metrics span,.hero-metrics small { color: #bfd1e8; font-size: 10px; }.hero-metrics strong { margin: 8px 0 5px; color: #fff; font-size: 24px; }.hero-metrics article.risk strong { color: #ffd4d4; }
.target-workspace { border-radius: 14px; }.target-workspace :deep(.ant-card-body) { padding: 0 18px 18px; }.target-toolbar { min-height: 68px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid #edf0f4; }.toolbar-fields,.toolbar-actions,.tab-label { display: flex; align-items: center; gap: 9px; }.period-select { width: 145px; }.status-select { width: 120px; }.keyword-input { width: 270px; }.toolbar-actions>span { color: #8a96a8; font-size: 11px; }
.target-tabs { margin-top: 8px; }.target-tabs :deep(.ant-tabs-nav) { margin-bottom: 10px; }.tab-guidance { min-height: 58px; margin-bottom: 12px; padding: 11px 14px; display: flex; align-items: center; justify-content: space-between; gap: 15px; border: 1px solid #dbe7f8; border-radius: 10px; background: #f5f8fd; }.tab-guidance>div { display: grid; gap: 3px; }.tab-guidance strong { color: #304158; font-size: 13px; }.tab-guidance span { color: #758297; font-size: 11px; }
.target-table :deep(.ant-table-thead>tr>th) { color: #667085; background: #f8fafc; font-size: 11px; }.target-table :deep(.ant-table-tbody>tr>td) { padding-top: 12px; padding-bottom: 12px; font-size: 11px; }.object-cell { display: flex; align-items: center; gap: 10px; }.object-mark { width: 36px; height: 36px; flex: none; display: grid; place-items: center; border-radius: 10px; color: #2766c2; background: #edf4ff; font-weight: 700; }.mark-gds { color: #087a72; background: #e8f8f5; }.mark-policy { color: #7a55bb; background: #f3effc; }.object-cell>div,.stack-cell,.metric-cell { min-width: 0; display: grid; gap: 3px; }.object-cell strong,.stack-cell strong { overflow: hidden; color: #334155; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.object-cell small,.stack-cell small,.metric-cell small,.gds-pair small,.progress-cell small { color: #929dad; font-size: 9px; }.metric-cell span { color: #526176; }.metric-cell small { font-family: ui-monospace,SFMono-Regular,Consolas,monospace; }.actual-value { color: #215fab; }.progress-cell { min-width: 160px; }.progress-cell small { display: block; }.gds-pair { display: flex; align-items: baseline; justify-content: flex-end; gap: 3px; }
.drawer-alert { margin-bottom: 18px; }.form-grid { display: grid; gap: 14px; }.form-grid.two { grid-template-columns: 1fr 1fr; }.full-width { width: 100%; }.gds-target-editor { margin-bottom: 18px; padding: 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; border: 1px solid #e4e9f1; border-radius: 10px; background: #f8fafc; }.gds-target-editor label { display: grid; gap: 6px; color: #667085; font-size: 12px; }.gds-target-editor :deep(.ant-input-number) { width: 100%; }.drawer-actions { margin-top: 20px; padding-top: 16px; display: flex; justify-content: flex-end; gap: 9px; border-top: 1px solid #edf0f4; }
.detail-hero { margin-bottom: 18px; padding: 19px; border: 1px solid #d8e4f3; border-radius: 12px; background: linear-gradient(135deg,#f1f6fd,#fff); }.detail-hero span { color: #3178f6; font-size: 10px; letter-spacing: .1em; }.detail-hero h2 { margin: 5px 0; color: #26364c; }.detail-hero p { margin: 0; color: #7d899a; font-size: 11px; }.metric-guide { display: grid; gap: 12px; }.metric-guide article { padding: 16px; border: 1px solid #e2e8f0; border-radius: 11px; }.metric-guide article>div { display: flex; align-items: center; justify-content: space-between; gap: 10px; }.metric-guide code { color: #3972c6; font-size: 10px; }.metric-guide p { margin: 9px 0 12px; color: #6f7d91; font-size: 12px; line-height: 1.65; }.metric-guide .filter-description { color: #8a6a36; }
@media (max-width:1000px) { .target-hero { grid-template-columns: 1fr; }.target-toolbar { align-items: flex-start; padding: 14px 0; flex-direction: column; }.toolbar-fields { width: 100%; flex-wrap: wrap; }.keyword-input { flex: 1; min-width: 210px; }.toolbar-actions { width: 100%; justify-content: space-between; } }
@media (max-width:620px) { .target-management-page { padding-inline: 12px; }.target-hero { padding: 22px 18px; }.hero-metrics { grid-template-columns: 1fr; }.form-grid.two,.gds-target-editor { grid-template-columns: 1fr; }.tab-guidance { align-items: flex-start; flex-direction: column; }.period-select,.status-select,.keyword-input { width: 100%; } }
</style>
