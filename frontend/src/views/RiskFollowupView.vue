<template>
 <div class="page-wrap followup-page">
  <PageHeader eyebrow="风控分析" :title="pageTitle" description="核查、咨询与差错认定形成闭环；规则与历史记录统一留存。"><a-button v-if="mode !== 'policies' && mode !== 'workbench'" @click="load">刷新</a-button><a-button @click="router.push('/risk-verification')">去风控核对</a-button></PageHeader>
  <RiskAnalyticsDashboard v-if="mode === 'workbench'" />
  <RiskRulesLibrary v-else-if="mode === 'policies'" />
  <section v-else class="follow-panel">
   <a-tabs :active-key="tab" @change="switchTab"><a-tab-pane v-for="t in tabs" :key="t.value" :tab="t.label" /></a-tabs>
   <div class="follow-filters"><a-input v-model:value="query" placeholder="实际盈亏原因或订单号" allow-clear @press-enter="search" /><a-select v-model:value="state" :options="stateOptions" placeholder="全部跟进状态" allow-clear /><a-button type="primary" :loading="loading" @click="search">查询</a-button></div>
   <a-alert v-if="error" type="error" show-icon :message="error" />
   <a-table :columns="columns" :data-source="result?.items || []" row-key="id" :loading="loading" :scroll="{ x: 1230 }" :pagination="{ current: page, pageSize, total: result?.total || 0, showSizeChanger: true, showTotal: (n: number) => `共 ${n} 个案例` }" @change="changePage">
    <template #bodyCell="{ column, record }">
     <template v-if="column.key === 'order'">
      <a-button v-if="record.primaryOrder" type="link" @click="evidenceOrder = record.primaryOrder">{{ orderNo(record.primaryOrder) }}</a-button>
      <span v-else>{{ record.orderCount > 1 ? '历史多单案例' : '—' }}</span>
     </template>
     <template v-else-if="column.key === 'title'"><span class="reason-text">{{ record.actualProfitReason || '未记录实际盈亏原因' }}</span><a-tag v-if="record.special" color="purple">特殊案例</a-tag><a-tag v-if="record.firstSeen" color="blue">首次出现</a-tag></template>
     <span v-else-if="column.key === 'platform'">{{ record.primaryOrder?.otaCode || '—' }}</span>
     <span v-else-if="column.key === 'airlines'">{{ record.primaryOrder?.airlines.join(' / ') || '—' }}</span>
     <span v-else-if="column.key === 'consultation'">{{ consultationLabel(record.consultation) }}</span>
     <span v-else-if="column.key === 'disposition'">{{ dispositions[record.disposition] }}</span>
     <a-tag v-else-if="column.key === 'state'" :color="record.state === 'done' ? 'green' : record.state === 'following' ? 'blue' : 'orange'">{{ followStates[record.state] }}</a-tag>
     <a-button v-else-if="column.key === 'action'" type="link" @click="openCase(record.id)">查看跟进</a-button>
    </template>
   </a-table>
   <p class="muted">待认定、计入差错、不计入差错按当前认定划分。全部案例保留历史记录。</p>
  </section>
  <a-drawer :open="detailOpen" :width="'min(1100px, 100vw)'" title="案例跟进" :closable="!saving" :mask-closable="!editing && !saving" :keyboard="!editing && !saving" @close="closeDetail">
   <a-spin :spinning="detailLoading"><a-alert v-if="detailError" type="error" show-icon :message="detailError" />
    <template v-if="detail">
     <div class="section-heading">
      <h2 class="reason-text">{{ detail.actualProfitReason || '未记录实际盈亏原因' }}</h2>
      <a-space wrap>
       <a-button v-if="canReview && detail.conclusion === 'problem' && detail.state !== 'done'" @click="editCase('progress')">记录跟进进展</a-button>
       <a-button v-if="canReview && detail.conclusion === 'problem'" type="primary" @click="editCase('finish')">{{ detail.state === 'done' ? '调整认定' : '完结跟进' }}</a-button>
       <a-button v-if="canReview && detail.conclusion !== 'unknown' && !detail.special && !detail.firstSeen" @click="archive('special')">加入特殊案例</a-button>
       <a-button v-if="canReview && detail.conclusion !== 'unknown' && detail.special" @click="archive('firstSeen')">转为首次出现</a-button>
      </a-space>
     </div>
     <a-alert v-if="detail.orders.some(o => o.stale)" type="warning" show-icon message="证据已变化；调整认定或完结前须重新核实当前证据。" />
     <a-alert v-if="(detail.orderCount ?? 0) > 1" type="info" show-icon message="历史多单案例按原案例保留，跟进和认定仍作用于整案。" />
     <a-descriptions bordered :column="2" size="small">
      <a-descriptions-item label="订单号">
       <a-button v-if="detail.primaryOrder" type="link" @click="evidenceOrder = detail.primaryOrder">{{ orderNo(detail.primaryOrder) }}</a-button>
       <a-select v-else-if="(detail.orderCount ?? 0) > 1" aria-label="选择原订单查看证据" placeholder="选择订单查看证据" :options="detail.orders.map((o, i) => ({ value: i, label: orderNo(o) }))" @change="openHistoricalEvidence" />
       <span v-else>—</span>
      </a-descriptions-item>
      <a-descriptions-item label="是否已咨询">{{ consultationLabel(detail.consultation) }}</a-descriptions-item>
      <a-descriptions-item label="平台">{{ detail.primaryOrder?.otaCode || '—' }}</a-descriptions-item>
      <a-descriptions-item label="航司">{{ detail.primaryOrder?.airlines.join(' / ') || '—' }}</a-descriptions-item>
      <a-descriptions-item label="政策员">{{ detail.policyOperators?.join(' / ') || '—' }}</a-descriptions-item>
      <a-descriptions-item label="出票员">{{ detail.issueOperators?.join(' / ') || '—' }}</a-descriptions-item>
      <a-descriptions-item label="退票员">{{ detail.refundOperators?.join(' / ') || '—' }}</a-descriptions-item>
      <a-descriptions-item label="跟进状态">{{ followStates[detail.state] }}</a-descriptions-item>
      <a-descriptions-item label="差错认定" :span="2">{{ dispositions[detail.disposition] }}</a-descriptions-item>
      <a-descriptions-item label="首次盈亏原因分类">{{ reasonDisplay(detail.primaryOrder?.firstProfitReason, detail.primaryOrder?.firstProfitReasonLabel) }} <a-tag v-if="detail.primaryOrder?.firstProfitReason">已锁定</a-tag></a-descriptions-item>
      <a-descriptions-item label="最新盈亏原因分类">
       {{ reasonDisplay(detail.primaryOrder?.latestProfitReason, detail.primaryOrder?.latestProfitReasonLabel) }}
       <p v-if="detail.primaryOrder?.latestReasonSyncedAt" class="muted">最近成功同步 {{ formatDateTimeDisplay(detail.primaryOrder.latestReasonSyncedAt) }}</p>
      </a-descriptions-item>
      <a-descriptions-item label="下一步／完成结果" :span="2">{{ detail.nextStep || '—' }}</a-descriptions-item>
      <a-descriptions-item label="备注" :span="2">{{ detail.remark || '—' }}</a-descriptions-item>
      <a-descriptions-item v-if="detail.special || detail.firstSeen" label="专项归档" :span="2">{{ detail.special ? '特殊案例' : '首次出现' }} · {{ detail.specialReason }}</a-descriptions-item>
     </a-descriptions>
     <p v-if="detail.personnelTruncated" class="muted">人员记录较多，此处展示前 100 组。</p>
     <RiskHandbookCaseLinks :case-id="detail.id" />
     <h3>跟进与认定历史</h3><a-timeline><a-timeline-item v-for="(event, i) in detail.events" :key="i"><strong>{{ formatDateTimeDisplay(event.at) }}</strong><span class="muted"> · 账号 {{ event.actor }}</span><p>{{ event.note }}</p><p v-if="event.kind === 'direct_error'">直接计入差错</p><p v-else-if="event.kind === 'direct_pending'">直接转入待认定</p><p v-else-if="event.after.disposition">{{ dispositions[event.before?.disposition || ''] || '待认定' }} → {{ dispositions[event.after.disposition] }}</p></a-timeline-item></a-timeline><p v-if="detail.eventsTruncated" class="muted">仅展示最近500条，历史未删除。</p>
    </template>
   </a-spin>
  </a-drawer>
  <FormDialog :open="editing" :title="dialogTitle" :busy="saving" :dirty="true" :error="saveError" @submit="saveCase" @cancel="editing = false">
   <template v-if="!libraryAction">
    <label>是否已咨询<a-select v-model:value="draft.consultation" :options="[{ value: 'pending', label: '待咨询' }, { value: 'consulted', label: '已咨询' }]" /></label>
    <label v-if="editAction === 'finish'">差错认定 <span class="required">必选</span><a-select v-model:value="draft.disposition" :options="dispositionOptions" placeholder="请选择差错认定" /></label>
    <template v-else>
     <label>下一步<a-textarea v-model:value="draft.nextStep" :maxlength="1000" :rows="2" /></label>
     <label>下次跟进时间（选填）<DateField v-model="draft.nextAt" with-time /></label>
    </template>
    <label>备注<a-textarea v-model:value="draft.remark" :maxlength="2000" :rows="2" /></label>
   </template>
   <label>{{ libraryAction ? '归档说明' : editAction === 'finish' ? '完结说明' : '本次跟进进展' }} <span v-if="libraryAction || editAction === 'progress'" class="required">必填</span><a-textarea v-model:value="draft.note" :maxlength="2000" :rows="4" /></label>
  </FormDialog>
  <a-drawer :open="!!evidenceOrder" :width="'min(1280px, 100vw)'" title="订单核查证据" :destroy-on-close="true" :closable="!evidenceBusy" :mask-closable="!evidenceBusy" :keyboard="!evidenceBusy" @close="evidenceOrder = undefined; refreshDetail()"><RiskAutomaticDetail v-if="evidenceOrder" :current-case-id="detailOpen ? detail?.id : undefined" :order-id="evidenceOrder.orderId" :issue-date="evidenceOrder.issueDate" :reason="''" :source-updated-at="null" @changed="refreshDetail" @busy-change="evidenceBusy = $event" /></a-drawer>
 </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Alert as AAlert, Button as AButton, Descriptions as ADescriptions, DescriptionsItem as ADescriptionsItem, Drawer as ADrawer, Input as AInput, Select as ASelect, Space as ASpace, Spin as ASpin, Table as ATable, Tabs as ATabs, TabPane as ATabPane, Tag as ATag, Timeline as ATimeline, TimelineItem as ATimelineItem, message } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import FormDialog from '@/components/FormDialog.vue'
import DateField from '@/components/DateField.vue'
import RiskAutomaticDetail from '@/components/RiskAutomaticDetail.vue'
import RiskRulesLibrary from '@/components/RiskRulesLibrary.vue'
import RiskHandbookCaseLinks from '@/components/RiskHandbookCaseLinks.vue'
import RiskAnalyticsDashboard from '@/components/RiskAnalyticsDashboard.vue'
import { riskFollowup, reviewKey, consultationLabel, dispositions, followStates, type CaseOrder, type FollowDetail, type FollowList, type OrderReview } from '@/api/riskFollowup'
import { useRiskPermissions } from '@/composables/useRiskPermissions'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const ATextarea = AInput.TextArea
const { canReview } = useRiskPermissions(), route = useRoute(), router = useRouter()
const mode = computed(() => String(route.meta.followupPage || 'cases'))
const pageTitle = computed(() => ({ workbench: '风控分析看板', cases: '案例跟进', library: '专项案例库', policies: '规章制度' }[mode.value] || '案例跟进'))
const stateOptions = Object.entries(followStates).map(([value,label]) => ({value,label}))
const tabs = computed(() => mode.value === 'library' ? [{ value: 'special', label: '特殊案例' }, { value: 'firstSeen', label: '首次出现' }] : [{ value: 'all', label: '全部案例' }, { value: 'pending', label: '待认定池' }, { value: 'included', label: '计入差错池' }, { value: 'excluded', label: '不计入差错池' }])
const tab = ref('all'), query = ref(''), state = ref<string>(), page = ref(1), pageSize = ref(20), loading = ref(false), error = ref(''), result = ref<FollowList>()
const detailOpen = ref(false), detailLoading = ref(false), detailError = ref(''), detail = ref<FollowDetail>(), editing = ref(false), saving = ref(false), saveError = ref(''), libraryAction = ref(''), evidenceOrder = ref<Pick<OrderReview, 'orderId' | 'issueDate'>>(), evidenceBusy = ref(false)
const editAction = ref<'progress' | 'finish'>('progress')
const draft = reactive({ disposition: undefined as string | undefined, consultation: 'pending', nextStep: '', nextAt: '', remark: '', note: '' })
const dispositionOptions = ['included', 'excluded'].map(value => ({ value, label: dispositions[value] }))
const dialogTitle = computed(() => libraryAction.value ? (libraryAction.value === 'special' ? '加入特殊案例' : '转为首次出现') : editAction.value === 'progress' ? '记录跟进进展' : detail.value?.state === 'done' ? '调整差错认定' : '完结跟进')
const columns = [
 { title:'订单号',key:'order',width:195 }, { title:'实际盈亏原因',key:'title',width:260 },
 { title:'平台',key:'platform',width:100 }, { title:'航司',key:'airlines',width:100 },
 { title:'是否已咨询',key:'consultation',width:120 }, { title:'跟进状态',key:'state',width:120 },
 { title:'差错认定',key:'disposition',width:120 }, { title:'操作',key:'action',width:110 },
]
function orderNo(order: Pick<CaseOrder, 'otaOrderNo' | 'businessOrderNo' | 'orderId'>) {
 return order.otaOrderNo || order.businessOrderNo || `内部ID ${order.orderId}`
}
function reasonDisplay(code?: string, label?: string) {
 return label && code ? `${label}（${code}）` : code || '未留存'
}
function openHistoricalEvidence(value: unknown) {
 if (typeof value === 'number') evidenceOrder.value = detail.value?.orders[value]
}
let alive = true, loadId = 0, detailId = 0, requestId = '', editVersion = 0
watch(mode, () => { tab.value = mode.value === 'library' ? 'special' : 'all'; search() }, { immediate:true })
watch(() => route.query.case, (id, previous) => { if (typeof id === 'string') { evidenceOrder.value = undefined; if (['pending','included','excluded'].includes(String(route.query.pool))) { tab.value = String(route.query.pool); search() } void openCase(id) } else if (typeof previous === 'string') { detailOpen.value = false; detailId++ } }, { immediate:true })
onBeforeUnmount(() => { alive = false; loadId++; detailId++ })
async function load() { if (['workbench','policies'].includes(mode.value)) return; const token = ++loadId; loading.value = true; error.value = ''; try { const params: Record<string,unknown> = {page:page.value,pageSize:pageSize.value,q:query.value || undefined,state:state.value}; if (['pending','included','excluded'].includes(tab.value)) { params.disposition=tab.value; if (tab.value !== 'excluded') params.conclusion='problem' } else if (['firstSeen','special'].includes(tab.value)) params[tab.value]='1'; const value=await riskFollowup.list(params); if(alive && token===loadId) result.value=value } catch(e) { if(alive && token===loadId) {error.value=e instanceof Error?e.message:'案例读取失败';result.value=undefined} } finally {if(alive && token===loadId) loading.value=false} }
function search() {page.value=1;void load()}
function switchTab(value:string|number){tab.value=String(value);search()}
function changePage(value:{current?:number;pageSize?:number}){page.value=value.current||1;pageSize.value=value.pageSize||20;void load()}
async function openCase(id:string){const token=++detailId;detailOpen.value=true;detailLoading.value=true;detailError.value='';detail.value=undefined;try{const value=await riskFollowup.detail(id);if(alive&&token===detailId)detail.value=value}catch(e){if(alive&&token===detailId)detailError.value=e instanceof Error?e.message:'详情读取失败'}finally{if(alive&&token===detailId)detailLoading.value=false}}
function closeDetail(){if(editing.value||saving.value)return;detailOpen.value=false;detailId++;if(route.query.case){if(typeof route.query.policy==='string'&&typeof route.query.section==='string'){void router.push({name:'risk-followup-policies',query:{policy:route.query.policy,section:route.query.section}})}else{void router.replace({query:{...route.query,case:undefined,pool:undefined}})}}}
async function refreshDetail(){if(detail.value)await openCase(detail.value.id);await load()}
function editCase(action: 'progress' | 'finish') {
 const item = detail.value
 if (!item) return
 editAction.value = action
 libraryAction.value = ''
 requestId = reviewKey()
 editVersion = item.version
 Object.assign(draft, {
  disposition: item.state === 'done' ? item.disposition : undefined,
  consultation: item.consultation || 'pending', nextStep: item.nextStep,
  nextAt: item.nextAt?.slice(0, 16) || '', remark: item.remark || '', note: '',
 })
 saveError.value = ''
 editing.value = true
}
function archive(action: string) {
 editCase('progress')
 libraryAction.value = action
}
async function saveCase() {
 const item = detail.value
 if (saving.value || !item) return
 const finishing = !libraryAction.value && editAction.value === 'finish'
 if (finishing && !dispositionOptions.some(o => o.value === draft.disposition)) {
  saveError.value = '请选择计入差错或不计入差错'
  return
 }
 if (!finishing && !draft.note.trim()) {
  saveError.value = libraryAction.value ? '请填写归档说明' : '请填写本次跟进进展'
  return
 }
 saving.value = true
 saveError.value = ''
 try {
  const base = { workflowVersion: 3, version: editVersion, requestId, note: draft.note }
  const update = libraryAction.value ? { libraryAction: libraryAction.value } : {
   consultation: draft.consultation, remark: draft.remark,
   disposition: finishing ? draft.disposition : item.disposition,
   state: finishing ? 'done' : 'following', nextStep: draft.nextStep,
   nextAt: finishing ? null : draft.nextAt,
  }
  const saved = await riskFollowup.update(item.id, { ...base, ...update })
  editing.value = false
  if (finishing && mode.value === 'cases' && tab.value !== 'all') {
   tab.value = saved.disposition
   page.value = 1
   if (route.query.case === item.id) await router.replace({ query: { ...route.query, pool: saved.disposition } })
  }
  message.success(finishing ? '差错认定已保存，跟进已完结' : '跟进记录已保存')
  await refreshDetail()
 } catch (e) {
  saveError.value = e instanceof Error ? e.message : '保存失败，输入已保留'
 } finally {
  saving.value = false
 }
}
</script>
<style scoped>
.reason-text{white-space:pre-wrap;overflow-wrap:anywhere}.followup-page{display:grid;gap:20px}.follow-panel{padding:20px;background:white;border:1px solid var(--platform-border, #dfe7ef);border-radius:8px;min-width:0}.follow-filters,.section-heading{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:16px 0}.follow-filters>.ant-input,.follow-filters>.ant-input-affix-wrapper{width:230px}.follow-filters>.ant-select{min-width:160px}.section-heading{justify-content:space-between}.section-heading h2{font-size:18px;margin:0}h3{margin-top:24px}.muted{color:#738298;font-size:12px}label{display:grid;gap:8px;margin:16px 0}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.required{font-size:12px;color:#a33b35}.ant-timeline p{white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:650px){.two{grid-template-columns:1fr}.follow-filters>.ant-input,.follow-filters>.ant-input-affix-wrapper{width:100%}}
</style>
