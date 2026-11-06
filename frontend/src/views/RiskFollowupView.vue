<template>
  <div class="page-wrap followup-page">
    <PageHeader eyebrow="风控分析" :title="pageTitle" description="核实结论、差错认定与后续跟进分别记录；团队共享案例，保留每次变化。">
      <template #default><a-button @click="load">刷新</a-button><a-button @click="router.push('/risk-verification')">去风控核对</a-button></template>
    </PageHeader>
    <template v-if="mode !== 'policies'">
      <div v-if="mode === 'workbench'" class="follow-metrics">
        <button v-for="m in metrics" :key="m.key" @click="jumpMetric(m.key)"><span>{{ m.label }}</span><strong>{{ result ? result.metrics[m.key] ?? 0 : '—' }}</strong><small>{{ m.note }}</small></button>
      </div>
      <section class="follow-panel">
        <a-tabs :active-key="tab" @change="switchTab">
          <a-tab-pane v-for="t in tabs" :key="t.value" :tab="t.label" />
        </a-tabs>
        <div class="follow-filters">
          <a-input v-model:value="query" placeholder="案例标题或完整编号" allow-clear @press-enter="search" />
          <a-button @click="assignee = auth.user?.displayName || ''; search()">我的跟进</a-button><a-input v-model:value="assignee" placeholder="负责人姓名" allow-clear @press-enter="search" />
          <a-select v-model:value="state" :options="stateOptions" placeholder="全部跟进状态" allow-clear />
          <a-checkbox v-model:checked="overdue">仅逾期未完成</a-checkbox>
          <a-button type="primary" :loading="loading" @click="search">查询</a-button>
        </div>
        <a-alert v-if="error" type="error" show-icon :message="error" />
        <a-table :columns="columns" :data-source="result?.items || []" row-key="id" :loading="loading" :scroll="{ x: 1250, y: 'min(60vh, 600px)' }" :pagination="{ current: page, pageSize, total: result?.total || 0, showSizeChanger: true, showTotal: (n: number) => `共 ${n} 个案例` }" @change="changePage">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'title'"><a-button type="link" @click="openCase(record.id)">{{ record.title }}</a-button><small class="block">{{ record.id }}</small><a-tag v-if="record.firstSeen" color="blue">首次出现</a-tag><a-tag v-if="record.special" color="purple">特殊案例</a-tag></template>
            <template v-else-if="column.key === 'conclusion'"><a-tag v-if="record.stale" color="orange">待重新核实</a-tag><a-tag v-else>{{ conclusions[record.conclusion] }}</a-tag><small class="block">{{ record.stale ? `历史：${conclusions[record.conclusion]} / ${dispositions[record.disposition]}` : record.conclusion === 'unknown' ? '待补证，尚未确认问题' : dispositions[record.disposition] }}</small></template>
            <template v-else-if="column.key === 'state'"><a-tag :color="record.state === 'done' ? 'green' : 'blue'">{{ followStates[record.state] }}</a-tag></template>
            <template v-else-if="column.key === 'nextAt'"><span :class="{ overdue: isOverdue(record as FollowCase) }">{{ formatDateTimeDisplay(record.nextAt) }}{{ isOverdue(record as FollowCase) ? ' · 已逾期' : '' }}</span></template>
            <a-button v-else-if="column.key === 'action'" type="link" @click="openCase(record.id)">查看跟进</a-button>
          </template>
          <template #emptyText>{{ error ? '读取失败，请排查后重试' : '当前条件暂无案例；从风控核对创建或关联案例' }}</template>
        </a-table>
        <p v-if="result?.metrics.stale" class="overdue">{{ result.metrics.stale }} 个案例证据已变化，待重新核实；不计入上方当前认定统计。</p><p class="muted">按案例计数，关联订单在详情分别列示；待补证不计入已确认问题。差错池展示当前认定，不回写财务历史报表。</p>
      </section>
    </template>
    <section v-else class="follow-panel">
      <div class="section-heading"><h2>公司策略版本</h2><a-button v-if="canManageTypes" type="primary" @click="newPolicy">登记策略版本</a-button></div>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <p class="muted">仅登记实际存在且已获业务认可的策略。新版本另行登记，已用于核实的策略快照保留；不自动生成公司业务规则。</p>
      <a-table :data-source="policies" :loading="loading" row-key="id" :columns="policyColumns" :scroll="{ x: 900 }">
        <template #bodyCell="{ column, record }"><span v-if="column.key === 'period'">{{ record.start }} 至 {{ record.end }}</span></template>
      </a-table>
      <h2>问题类型</h2><div class="follow-filters"><a-input v-if="canManageTypes" v-model:value="newType" :maxlength="60" placeholder="新问题类型名称" /><a-button v-if="canManageTypes" :loading="typeBusy" @click="addType">新增问题类型</a-button></div><a-space wrap><a-tag v-for="t in types" :key="t.id">{{ t.name }}</a-tag></a-space>
    </section>
    <a-drawer :open="detailOpen" :width="'min(1100px, 100vw)'" title="案例跟进" :mask-closable="!editing" :keyboard="!editing" @close="closeDetail">
      <a-spin :spinning="detailLoading">
        <a-alert v-if="detailError" type="error" show-icon :message="detailError" />
        <template v-if="detail">
          <div class="section-heading"><div><h2>{{ detail.title }}</h2><small class="muted">{{ detail.id }} · v{{ detail.version }}</small></div><a-space><a-button @click="openCase(detail.id)">刷新详情</a-button><a-button v-if="canReview" type="primary" @click="editCase">{{ detail.state === 'done' ? '补充记录／重新打开' : '记录跟进／调整认定' }}</a-button></a-space></div>
          <a-alert v-if="detail.orders.some(o => o.stale)" type="warning" show-icon message="部分关联订单证据已变化，旧结论仅供参考" description="可以继续跟进；调整认定或完成前，请在订单证据中重新核实。" />
          <a-descriptions bordered :column="2" size="small">
            <a-descriptions-item label="人工结论">{{ conclusions[detail.conclusion] }}</a-descriptions-item><a-descriptions-item label="差错认定">{{ detail.conclusion === 'unknown' ? '待补证，尚未确认问题' : dispositions[detail.disposition] }}</a-descriptions-item>
            <a-descriptions-item label="跟进状态">{{ followStates[detail.state] }}</a-descriptions-item><a-descriptions-item label="负责人">{{ detail.assignee }}</a-descriptions-item>
            <a-descriptions-item label="问题类型">{{ detail.problemType }}</a-descriptions-item><a-descriptions-item label="责任归属">{{ detail.responsibility }}</a-descriptions-item>
            <a-descriptions-item label="发生原因">{{ detail.cause }}</a-descriptions-item><a-descriptions-item label="下次跟进">{{ formatDateTimeDisplay(detail.nextAt) }}</a-descriptions-item>
            <a-descriptions-item label="下一步／完成结果" :span="2">{{ detail.nextStep }}</a-descriptions-item>
            <a-descriptions-item v-if="detail.firstSeen || detail.special" label="案例沉淀" :span="2"><a-tag v-if="detail.firstSeen" color="blue">首次出现</a-tag><a-tag v-if="detail.special" color="purple">特殊案例</a-tag>{{ detail.specialReason }}</a-descriptions-item>
          </a-descriptions>
          <h3>关联订单（{{ detail.orders.length }} 单）</h3><p class="muted">同类订单可在风控核对中通过“关联已有案例”追加；认定调整会作用于本案例全部关联订单。</p>
          <a-table :data-source="detail.orders" :row-key="(row: OrderReview) => `${row.orderId}-${row.issueDate}`" :columns="linkedColumns" :scroll="{ x: 750 }" :pagination="{ pageSize: 10 }"><template #bodyCell="{ column, record }"><template v-if="column.key === 'conclusion'">{{ conclusions[record.conclusion] }}<a-tag v-if="record.stale" color="orange">待重新核实</a-tag></template><a-button v-else-if="column.key === 'action'" type="link" @click="evidenceOrder = record as OrderReview">查看证据／重新核实</a-button></template></a-table>
          <h3>跟进与认定历史</h3><a-alert v-if="detail.eventsTruncated" type="warning" message="仅展示最近500条记录，历史未删除" />
          <a-timeline><a-timeline-item v-for="(e, index) in detail.events" :key="index"><strong>{{ e.kind === 'review' ? '人工核实' : '跟进／认定调整' }}</strong><span class="muted"> · {{ formatDateTimeDisplay(e.at) }} · 账号 {{ e.actor }}</span><p>{{ e.note }}</p><p v-if="e.kind !== 'review'">{{ describe(e.before) }} → {{ describe(e.after) }}</p><p v-else>订单 {{ e.after.orderId }} · {{ conclusions[e.after.conclusion || ''] }}</p></a-timeline-item></a-timeline>
        </template>
      </a-spin>
    </a-drawer>
    <FormDialog :open="editing" title="记录跟进与调整认定" :busy="saving" :dirty="true" :error="saveError" @submit="saveCase" @cancel="editing = false">
      <a-alert v-if="detail" type="info" :message="`本次认定适用于本案例全部 ${detail.orders.length} 笔关联订单，历史记录保留`" />
      <div class="two"><label>人工结论<a-select v-model:value="draft.conclusion" :options="options(conclusions)" /></label><label>差错认定<a-select v-model:value="draft.disposition" :options="options(dispositions)" /></label><label>跟进状态<a-select v-model:value="draft.state" :options="options(followStates)" /></label><label>负责人<a-input v-model:value="draft.assignee" :maxlength="80" /></label></div>
      <label>问题类型<a-select v-model:value="draft.problemType" show-search :options="types.map(t => ({ value: t.name, label: t.name }))" /></label><div class="two"><label>发生原因<a-input v-model:value="draft.cause" :maxlength="500" /></label><label>责任归属<a-input v-model:value="draft.responsibility" :maxlength="500" /></label></div>
      <label>下一步／完成结果<a-textarea v-model:value="draft.nextStep" :rows="2" :maxlength="1000" /></label><label v-if="draft.state !== 'done'">下次跟进时间<DateField v-model="draft.nextAt" with-time /></label>
      <a-space wrap><a-checkbox v-model:checked="draft.firstSeen">首次出现（已核对历史）</a-checkbox><a-checkbox v-model:checked="draft.special">特殊案例</a-checkbox></a-space><label v-if="draft.firstSeen || draft.special">首次或特殊案例说明<a-input v-model:value="draft.specialReason" :maxlength="1000" /></label>
      <label>本次跟进内容／认定调整依据<a-textarea v-model:value="draft.note" :rows="3" :maxlength="2000" /></label>
    </FormDialog>
    <FormDialog :open="policyOpen" title="登记公司策略版本" :busy="saving" :dirty="true" :error="saveError" @submit="savePolicy" @cancel="policyOpen = false">
      <label>策略名称<a-input v-model:value="policyDraft.name" :maxlength="100" /></label><label>版本<a-input v-model:value="policyDraft.policyVersion" :maxlength="60" /></label><div class="two"><label>适用出票日起<DateField v-model="policyDraft.start" /></label><label>适用出票日止<DateField v-model="policyDraft.end" /></label></div><label>适用范围<a-textarea v-model:value="policyDraft.scope" :maxlength="1000" /></label><label>业务认可依据／文件引用<a-textarea v-model:value="policyDraft.basis" :maxlength="2000" /></label>
    </FormDialog>
    <a-drawer :open="!!evidenceOrder" :width="'min(1280px, 100vw)'" title="关联订单核实证据" :destroy-on-close="true" :closable="!evidenceBusy" :mask-closable="!evidenceBusy" :keyboard="!evidenceBusy" @close="closeEvidence"><RiskAutomaticDetail v-if="evidenceOrder" :key="`${evidenceOrder.orderId}-${evidenceOrder.issueDate}`" :order-id="evidenceOrder.orderId" :issue-date="evidenceOrder.issueDate" :reason="''" :source-updated-at="null" @changed="refreshDetail" @busy-change="evidenceBusy = $event" /></a-drawer>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Alert as AAlert, Button as AButton, Checkbox as ACheckbox, Descriptions as ADescriptions, DescriptionsItem as ADescriptionsItem, Drawer as ADrawer, Input as AInput, Select as ASelect, Space as ASpace, Spin as ASpin, Table as ATable, Tabs as ATabs, TabPane as ATabPane, Tag as ATag, Timeline as ATimeline, TimelineItem as ATimelineItem, message } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import FormDialog from '@/components/FormDialog.vue'
import DateField from '@/components/DateField.vue'
import RiskAutomaticDetail from '@/components/RiskAutomaticDetail.vue'
import { riskFollowup, reviewKey, conclusions, dispositions, followStates, type FollowCase, type FollowDetail, type FollowEvent, type FollowList, type ReviewPolicy, type OrderReview } from '@/api/riskFollowup'
import { riskProblems, type RiskProblemType } from '@/api/riskVerification'
import { useAuthStore } from '@/stores/auth'
import { useRiskPermissions } from '@/composables/useRiskPermissions'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const ATextarea = AInput.TextArea
const { canReview, canManageTypes } = useRiskPermissions()
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const mode = computed(() => String(route.meta.followupPage || 'cases'))
const pageTitle = computed(() => ({ workbench: '风控工作台', cases: '案例跟进', library: '专题案例库', policies: '类型与策略' }[mode.value] || '案例跟进'))
const options = (labels: Record<string, string>) => Object.entries(labels).map(([value, label]) => ({ value, label }))
const stateOptions = options(followStates)
const metrics = [{ key: 'pending', label: '待差错认定', note: '已确认问题，等待认定' }, { key: 'unknown', label: '待补证', note: '尚无法判断实际问题' }, { key: 'overdue', label: '逾期未完成', note: '优先补充跟进进展' }, { key: 'total', label: '全部案例', note: '按案例计数，非订单数' }]
const tabs = computed(() => mode.value === 'library' ? [{ value: 'firstSeen', label: '首次出现' }, { value: 'special', label: '特殊案例' }] : [{ value: 'all', label: '全部案例' }, { value: 'pending', label: '待认定池' }, { value: 'included', label: '计入差错池' }, { value: 'excluded', label: '不计入差错池' }, { value: 'unknown', label: '待补证' }])
const tab = ref('all'), query = ref(''), assignee = ref(''), state = ref<string>(), overdue = ref(false), page = ref(1), pageSize = ref(20)
const loading = ref(false), error = ref(''), result = ref<FollowList>(), policies = ref<ReviewPolicy[]>([]), types = ref<RiskProblemType[]>([]), newType = ref(''), typeBusy = ref(false)
const detailOpen = ref(false), detailLoading = ref(false), detailError = ref(''), detail = ref<FollowDetail>(), editing = ref(false), saving = ref(false), saveError = ref(''), policyOpen = ref(false), evidenceOrder = ref<OrderReview>(), evidenceBusy = ref(false)
const draft = reactive({ conclusion: 'problem', disposition: 'pending', state: 'following', assignee: '', nextStep: '', nextAt: '', firstSeen: false, special: false, specialReason: '', problemType: '', cause: '', responsibility: '', note: '' })
const policyDraft = reactive({ name: '', policyVersion: '', start: '', end: '', scope: '', basis: '' })
let requestId = '', editVersion = 0, alive = true, loadId = 0, detailId = 0
const columns = [{ title: '案例', key: 'title', width: 300 }, { title: '人工结论／认定', key: 'conclusion', width: 170 }, { title: '跟进状态', key: 'state', width: 110 }, { title: '负责人', dataIndex: 'assignee', width: 100 }, { title: '下一步', dataIndex: 'nextStep', width: 240, ellipsis: true }, { title: '下次跟进', key: 'nextAt', width: 180 }, { title: '操作', key: 'action', width: 110 }]
const linkedColumns = [{ title: '订单ID', dataIndex: 'orderId' }, { title: '出票日', dataIndex: 'issueDate' }, { title: '人工结论', key: 'conclusion' }, { title: '操作', key: 'action' }]
const policyColumns = [{ title: '名称', dataIndex: 'name' }, { title: '版本', dataIndex: 'policyVersion' }, { title: '适用出票日', key: 'period' }, { title: '适用范围', dataIndex: 'scope', width: 260 }, { title: '依据', dataIndex: 'basis', width: 260 }]
const isOverdue = (c: FollowCase) => c.state !== 'done' && !!c.nextAt && Date.parse(c.nextAt) < Date.now()
const describe = (v: FollowEvent['before']) => v ? `${conclusions[v.conclusion || ''] || '—'} / ${dispositions[v.disposition || ''] || '—'} / ${followStates[v.state || ''] || '—'}` : '无历史认定'
watch(mode, () => { tab.value = mode.value === 'library' ? 'firstSeen' : 'all'; page.value = 1; void load() }, { immediate: true })
watch(() => route.query.case, id => { if (typeof id === 'string') void openCase(id) }, { immediate: true })
onBeforeUnmount(() => { alive = false; loadId++; detailId++ })
async function load() {
  const token = ++loadId; loading.value = true; error.value = ''
  try {
    if (mode.value === 'policies') { const [p, t] = await Promise.all([riskFollowup.policies(), riskProblems.types()]); if (alive && token === loadId) { policies.value = p; types.value = t } }
    else { const params: Record<string, unknown> = { page: page.value, pageSize: pageSize.value, q: query.value || undefined, assignee: assignee.value || undefined, state: state.value, overdue: overdue.value ? '1' : undefined }; if (['pending', 'included'].includes(tab.value)) { params.disposition = tab.value; params.conclusion = 'problem' } else if (tab.value === 'excluded') params.disposition = tab.value; else if (tab.value === 'unknown') params.conclusion = 'unknown'; else if (['firstSeen', 'special'].includes(tab.value)) params[tab.value] = '1'; const value = await riskFollowup.list(params); if (alive && token === loadId) result.value = value }
  } catch (e) { if (alive && token === loadId) { error.value = e instanceof Error ? e.message : '读取失败'; result.value = undefined } }
  finally { if (alive && token === loadId) loading.value = false }
}
function search() { page.value = 1; void load() }
function switchTab(value: string | number) { tab.value = String(value); search() }
function jumpMetric(key: string) { overdue.value = key === 'overdue'; tab.value = ['pending', 'unknown'].includes(key) ? key : 'all'; search() }
function changePage(p: { current?: number; pageSize?: number }) { page.value = p.current || 1; pageSize.value = p.pageSize || 20; void load() }
async function openCase(id: string) {
  const token = ++detailId; detailOpen.value = true; detailLoading.value = true; detailError.value = ''; detail.value = undefined
  try { const value = await riskFollowup.detail(id); if (alive && token === detailId) detail.value = value }
  catch (e) { if (alive && token === detailId) detailError.value = e instanceof Error ? e.message : '案例读取失败' }
  finally { if (alive && token === detailId) detailLoading.value = false }
}
function closeDetail() { if (editing.value) return; detailId++; detailOpen.value = false; if (route.query.case) void router.replace({ query: { ...route.query, case: undefined } }) }
async function refreshDetail() { if (detail.value) await openCase(detail.value.id); await load() }
function closeEvidence() { if (evidenceBusy.value) return; evidenceOrder.value = undefined; void refreshDetail() }
async function editCase() {
  if (!detail.value) return
  saveError.value = ''; requestId = reviewKey(); editVersion = detail.value.version
  Object.assign(draft, detail.value, { note: '', nextAt: detail.value.nextAt?.slice(0, 16) || '' })
  editing.value = true
  try { types.value = await riskProblems.types() } catch (e) { saveError.value = e instanceof Error ? e.message : '类型读取失败' }
}
async function saveCase() {
  if (saving.value || !detail.value) return
  saving.value = true; saveError.value = ''
  try { await riskFollowup.update(detail.value.id, { ...draft, version: editVersion, requestId }); editing.value = false; message.success('跟进记录已保存'); await refreshDetail() }
  catch (e) { saveError.value = e instanceof Error ? e.message : '保存失败，输入已保留' }
  finally { saving.value = false }
}
function newPolicy() { requestId = reviewKey(); Object.assign(policyDraft, { name: '', policyVersion: '', start: '', end: '', scope: '', basis: '' }); saveError.value = ''; policyOpen.value = true }
async function savePolicy() { if (saving.value) return; saving.value = true; saveError.value = ''; try { await riskFollowup.createPolicy({ ...policyDraft, requestId }); policyOpen.value = false; message.success('策略版本已登记'); await load() } catch (e) { saveError.value = e instanceof Error ? e.message : '保存失败' } finally { saving.value = false } }
async function addType() { if (typeBusy.value || !newType.value.trim()) return; typeBusy.value = true; try { await riskProblems.createType(newType.value); newType.value = ''; await load() } catch (e) { error.value = e instanceof Error ? e.message : '新增失败' } finally { typeBusy.value = false } }
</script>
<style scoped>
.followup-page{display:grid;gap:20px}.follow-panel{padding:20px;background:white;border:1px solid #e4e9ef;border-radius:8px;min-width:0}.follow-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.follow-metrics button{display:grid;text-align:left;gap:6px;background:white;border:1px solid #e4e9ef;border-radius:8px;padding:18px;cursor:pointer;font:inherit}.follow-metrics strong{font-size:28px;color:#26364c}.follow-metrics small,.muted,.block{color:#738298;font-size:12px}.follow-filters{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 0 20px}.follow-filters>.ant-input-affix-wrapper,.follow-filters>.ant-input{width:230px}.follow-filters>.ant-select{min-width:160px}.section-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 20px}h2{font-size:18px;margin:0}h3{margin-top:24px}.block{display:block}.overdue{color:#bd483d}label{display:grid;gap:6px;margin:16px 0}.two{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}input[type=date],input[type=datetime-local]{padding:8px;border:1px solid #d9d9d9;border-radius:6px;width:100%;font:inherit}.ant-timeline p{white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0}@media(max-width:900px){.follow-metrics{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.two{grid-template-columns:1fr}.follow-panel{padding:14px}.follow-filters>.ant-input-affix-wrapper,.follow-filters>.ant-input{width:100%}}
</style>
