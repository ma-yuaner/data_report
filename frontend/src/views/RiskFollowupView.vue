<template>
 <div class="page-wrap followup-page">
  <PageHeader eyebrow="风控分析" :title="pageTitle" description="核查、咨询与差错认定形成闭环；规则与历史记录统一留存。"><a-button v-if="mode !== 'policies' && mode !== 'workbench'" @click="load">刷新</a-button><a-button @click="router.push('/risk-verification')">去风控核对</a-button></PageHeader>
  <RiskAnalyticsDashboard v-if="mode === 'workbench'" />
  <RiskRulesLibrary v-else-if="mode === 'policies'" />
  <section v-else class="follow-panel">
   <a-tabs :active-key="tab" @change="switchTab"><a-tab-pane v-for="t in tabs" :key="t.value" :tab="t.label" /></a-tabs>
   <div class="follow-filters"><a-input v-model:value="query" placeholder="案例标题或完整编号" allow-clear @press-enter="search" /><a-input v-model:value="assignee" placeholder="负责人姓名" allow-clear @press-enter="search" /><a-select v-model:value="state" :options="stateOptions" placeholder="全部跟进状态" allow-clear /><a-button type="primary" :loading="loading" @click="search">查询</a-button></div>
   <a-alert v-if="error" type="error" show-icon :message="error" />
   <a-table :columns="columns" :data-source="result?.items || []" row-key="id" :loading="loading" :scroll="{ x: 1100 }" :pagination="{ current: page, pageSize, total: result?.total || 0, showSizeChanger: true, showTotal: (n: number) => `共 ${n} 个案例` }" @change="changePage">
    <template #bodyCell="{ column, record }">
     <template v-if="column.key === 'title'"><a-button type="link" @click="openCase(record.id)">{{ record.title }}</a-button><a-tag v-if="record.special" color="purple">特殊案例</a-tag><a-tag v-if="record.firstSeen" color="blue">首次出现</a-tag></template>
     <template v-else-if="column.key === 'conclusion'"><a-tag v-if="record.stale" color="orange">待重新核实</a-tag><span v-else>{{ caseStatus(record as FollowCase) }}</span></template>
     <span v-else-if="column.key === 'disposition'">{{ record.conclusion === 'no_issue' && record.disposition === 'pending' ? '核实无问题，已完成' : dispositions[record.disposition] }}</span>
     <span v-else-if="column.key === 'state'">{{ followStates[record.state] }}</span>
     <a-button v-else-if="column.key === 'action'" type="link" @click="openCase(record.id)">查看跟进</a-button>
    </template>
   </a-table>
   <p class="muted">全部案例保留待认定后核实无问题的历史。待认定、计入差错、不计入差错按当前认定划分，不重复计数；特殊案例先由人工加入。</p>
  </section>
  <a-drawer :open="detailOpen" :width="'min(1100px, 100vw)'" title="案例跟进" :closable="!saving" :mask-closable="!editing && !saving" :keyboard="!editing && !saving" @close="closeDetail">
   <a-spin :spinning="detailLoading"><a-alert v-if="detailError" type="error" show-icon :message="detailError" />
    <template v-if="detail">
     <div class="section-heading"><h2>{{ detail.title }}</h2><a-space wrap><a-button v-if="canReview" type="primary" @click="editCase">记录跟进／调整认定</a-button><a-button v-if="canReview && detail.conclusion !== 'unknown' && !detail.special && !detail.firstSeen" @click="archive('special')">加入特殊案例</a-button><a-button v-if="canReview && detail.conclusion !== 'unknown' && detail.special" @click="archive('firstSeen')">转为首次出现</a-button></a-space></div>
     <a-alert v-if="detail.orders.some(o => o.stale)" type="warning" show-icon message="证据已变化；调整认定或完成前须重新核实当前证据。" />
     <a-descriptions bordered :column="2" size="small"><a-descriptions-item label="人工核实状态">{{ caseStatus(detail) }}</a-descriptions-item><a-descriptions-item label="差错认定">{{ detail.conclusion === 'no_issue' && detail.disposition === 'pending' ? '核实无问题，已完成' : dispositions[detail.disposition] }}</a-descriptions-item><a-descriptions-item label="跟进状态">{{ followStates[detail.state] }}</a-descriptions-item><a-descriptions-item label="负责人">{{ detail.assignee || '未指定' }}</a-descriptions-item><a-descriptions-item label="发生原因" :span="2">{{ detail.cause }}</a-descriptions-item><a-descriptions-item label="下一步／完成结果" :span="2">{{ detail.nextStep }}</a-descriptions-item><a-descriptions-item label="备注" :span="2">{{ detail.remark || '—' }}</a-descriptions-item><a-descriptions-item v-if="detail.special || detail.firstSeen" label="专项归档" :span="2">{{ detail.special ? '特殊案例' : '首次出现' }} · {{ detail.specialReason }}</a-descriptions-item></a-descriptions>
     <RiskHandbookCaseLinks :case-id="detail.id" />
     <h3>关联订单</h3><a-table :data-source="detail.orders" :row-key="(o: OrderReview) => `${o.orderId}-${o.issueDate}`" :columns="linkedColumns" :pagination="{ pageSize: 10 }"><template #bodyCell="{ column, record }"><span v-if="column.key === 'conclusion'">{{ record.conclusion === 'no_issue' ? '核查无问题' : record.conclusion === 'problem' ? `有问题-${record.consultation === 'consulted' ? '已咨询' : '待咨询'}` : '历史未判定，待重新核实' }}</span><a-button v-else-if="column.key === 'action'" type="link" @click="evidenceOrder = record as OrderReview">查看证据／重新核实</a-button></template></a-table>
     <h3>跟进与认定历史</h3><a-timeline><a-timeline-item v-for="(event, i) in detail.events" :key="i"><strong>{{ formatDateTimeDisplay(event.at) }}</strong><span class="muted"> · 账号 {{ event.actor }}</span><p>{{ event.note }}</p><p v-if="event.after.conclusion">{{ humanReviewLabel(event.after) }}</p><p v-if="event.after.disposition">{{ dispositions[event.before?.disposition || ''] || '待认定' }} → {{ dispositions[event.after.disposition] }}</p></a-timeline-item></a-timeline><p v-if="detail.eventsTruncated" class="muted">仅展示最近500条，历史未删除。</p>
    </template>
   </a-spin>
  </a-drawer>
  <FormDialog :open="editing" :title="libraryAction ? (libraryAction === 'special' ? '加入特殊案例' : '转为首次出现') : '跟进与差错认定'" :busy="saving" :dirty="true" :error="saveError" @submit="saveCase" @cancel="editing = false">
   <template v-if="!libraryAction">
    <a-alert v-if="detail" type="info" show-icon :message="`本次调整作用于本案例全部 ${detail.orders.length} 笔订单`" />
    <div class="two"><label>人工结论<a-select v-model:value="draft.conclusion" :options="[{ value: 'problem', label: '有问题' }, { value: 'no_issue', label: '核查无问题' }]" /></label><label v-if="draft.conclusion === 'problem'">咨询状态<a-select v-model:value="draft.consultation" :options="[{ value: 'pending', label: '待咨询' }, { value: 'consulted', label: '已咨询' }]" /></label></div>
    <label v-if="draft.conclusion === 'problem'">差错认定<a-select v-model:value="draft.disposition" :options="dispositionOptions" /></label><p v-else class="muted">保存后完成核实；待认定案例仅保留在全部案例，已计入差错的案例转到不计入差错池。</p>
    <div class="two"><label v-if="draft.conclusion === 'problem'">跟进状态<a-select v-model:value="draft.state" :options="stateOptions.filter(o => draft.disposition !== 'pending' || o.value !== 'done')" /></label><label>负责人<a-input v-model:value="draft.assignee" :maxlength="80" /></label></div>
    <label>下一步／完成结果<a-textarea v-model:value="draft.nextStep" :maxlength="1000" :rows="2" /></label><label v-if="draft.state !== 'done' && draft.conclusion === 'problem'">下次跟进时间（选填）<DateField v-model="draft.nextAt" with-time /></label><label>备注<a-textarea v-model:value="draft.remark" :maxlength="2000" :rows="2" /></label>
   </template>
   <label>{{ libraryAction ? '归档说明' : '本次跟进／认定依据' }} <span class="required">必填</span><a-textarea v-model:value="draft.note" :maxlength="2000" :rows="4" /></label>
  </FormDialog>
  <a-drawer :open="!!evidenceOrder" :width="'min(1280px, 100vw)'" title="订单核查证据" :destroy-on-close="true" :closable="!evidenceBusy" :mask-closable="!evidenceBusy" :keyboard="!evidenceBusy" @close="evidenceOrder = undefined; refreshDetail()"><RiskAutomaticDetail v-if="evidenceOrder" :order-id="evidenceOrder.orderId" :issue-date="evidenceOrder.issueDate" :reason="''" :source-updated-at="null" @changed="refreshDetail" @busy-change="evidenceBusy = $event" /></a-drawer>
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
import { riskFollowup, reviewKey, humanReviewLabel, dispositions, followStates, type FollowCase, type FollowDetail, type FollowList, type OrderReview } from '@/api/riskFollowup'
import { useRiskPermissions } from '@/composables/useRiskPermissions'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const ATextarea = AInput.TextArea
const { canReview } = useRiskPermissions(), route = useRoute(), router = useRouter()
const mode = computed(() => String(route.meta.followupPage || 'cases'))
const pageTitle = computed(() => ({ workbench: '风控分析看板', cases: '案例跟进', library: '专项案例库', policies: '规章制度' }[mode.value] || '案例跟进'))
const stateOptions = Object.entries(followStates).map(([value,label]) => ({value,label}))
const tabs = computed(() => mode.value === 'library' ? [{ value: 'special', label: '特殊案例' }, { value: 'firstSeen', label: '首次出现' }] : [{ value: 'all', label: '全部案例' }, { value: 'pending', label: '待认定池' }, { value: 'included', label: '计入差错池' }, { value: 'excluded', label: '不计入差错池' }])
const tab = ref('all'), query = ref(''), assignee = ref(''), state = ref<string>(), page = ref(1), pageSize = ref(20), loading = ref(false), error = ref(''), result = ref<FollowList>()
const detailOpen = ref(false), detailLoading = ref(false), detailError = ref(''), detail = ref<FollowDetail>(), editing = ref(false), saving = ref(false), saveError = ref(''), libraryAction = ref(''), evidenceOrder = ref<OrderReview>(), evidenceBusy = ref(false)
const draft = reactive({ conclusion:'problem', disposition:'pending', state:'following', consultation:'pending', assignee:'', nextStep:'', nextAt:'', remark:'', note:'' })
const dispositionOptions = computed(() => (detail.value?.disposition === 'pending' ? ['pending','included'] : ['included','excluded']).map(value => ({value,label:dispositions[value]})))
const columns = [{ title:'案例',key:'title',width:300 },{ title:'人工核实状态',key:'conclusion',width:180 },{ title:'差错认定',key:'disposition',width:170 },{ title:'跟进状态',key:'state',width:120 },{ title:'负责人',dataIndex:'assignee',width:120 },{ title:'操作',key:'action',width:110 }]
const linkedColumns = [{ title:'OTA订单号',dataIndex:'otaOrderNo' },{ title:'出票日',dataIndex:'issueDate' },{ title:'人工核实状态',key:'conclusion' },{ title:'操作',key:'action' }]
const caseStatus = humanReviewLabel
let alive = true, loadId = 0, detailId = 0, requestId = '', editVersion = 0
watch(mode, () => { tab.value = mode.value === 'library' ? 'special' : 'all'; search() }, { immediate:true })
watch(() => route.query.case, (id, previous) => { if (typeof id === 'string') { if (['pending','included','excluded'].includes(String(route.query.pool))) { tab.value = String(route.query.pool); search() } void openCase(id) } else if (typeof previous === 'string') { detailOpen.value = false; detailId++ } }, { immediate:true })
onBeforeUnmount(() => { alive = false; loadId++; detailId++ })
async function load() { if (['workbench','policies'].includes(mode.value)) return; const token = ++loadId; loading.value = true; error.value = ''; try { const params: Record<string,unknown> = {page:page.value,pageSize:pageSize.value,q:query.value || undefined,assignee:assignee.value || undefined,state:state.value}; if (['pending','included','excluded'].includes(tab.value)) { params.disposition=tab.value; if (tab.value !== 'excluded') params.conclusion='problem' } else if (['firstSeen','special'].includes(tab.value)) params[tab.value]='1'; const value=await riskFollowup.list(params); if(alive && token===loadId) result.value=value } catch(e) { if(alive && token===loadId) {error.value=e instanceof Error?e.message:'案例读取失败';result.value=undefined} } finally {if(alive && token===loadId) loading.value=false} }
function search() {page.value=1;void load()}
function switchTab(value:string|number){tab.value=String(value);search()}
function changePage(value:{current?:number;pageSize?:number}){page.value=value.current||1;pageSize.value=value.pageSize||20;void load()}
async function openCase(id:string){const token=++detailId;detailOpen.value=true;detailLoading.value=true;detailError.value='';detail.value=undefined;try{const value=await riskFollowup.detail(id);if(alive&&token===detailId)detail.value=value}catch(e){if(alive&&token===detailId)detailError.value=e instanceof Error?e.message:'详情读取失败'}finally{if(alive&&token===detailId)detailLoading.value=false}}
function closeDetail(){if(editing.value||saving.value)return;detailOpen.value=false;detailId++;if(route.query.case){if(typeof route.query.policy==='string'&&typeof route.query.section==='string'){void router.push({name:'risk-followup-policies',query:{policy:route.query.policy,section:route.query.section}})}else{void router.replace({query:{...route.query,case:undefined,pool:undefined}})}}}
async function refreshDetail(){if(detail.value)await openCase(detail.value.id);await load()}
function editCase(){if(!detail.value)return;libraryAction.value='';requestId=reviewKey();editVersion=detail.value.version;Object.assign(draft,detail.value,{conclusion:detail.value.conclusion==='unknown'?'':detail.value.conclusion,consultation:detail.value.consultation||'pending',remark:detail.value.remark||'',nextAt:detail.value.nextAt?.slice(0,16)||'',note:''});saveError.value='';editing.value=true}
function archive(action:string){editCase();libraryAction.value=action}
async function saveCase(){if(saving.value||!detail.value)return;saving.value=true;saveError.value='';try{await riskFollowup.update(detail.value.id,{...draft,workflowVersion:3,version:editVersion,requestId,libraryAction:libraryAction.value||undefined});editing.value=false;message.success('跟进记录已保存');await refreshDetail()}catch(e){saveError.value=e instanceof Error?e.message:'保存失败，输入已保留'}finally{saving.value=false}}
</script>
<style scoped>
.followup-page{display:grid;gap:20px}.follow-panel{padding:20px;background:white;border:1px solid #e4e9ef;border-radius:8px;min-width:0}.follow-filters,.section-heading{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:16px 0}.follow-filters>.ant-input,.follow-filters>.ant-input-affix-wrapper{width:230px}.follow-filters>.ant-select{min-width:160px}.section-heading{justify-content:space-between}.section-heading h2{font-size:18px;margin:0}h3{margin-top:24px}.muted{color:#738298;font-size:12px}label{display:grid;gap:8px;margin:16px 0}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.required{font-size:12px;color:#a33b35}.ant-timeline p{white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:650px){.two{grid-template-columns:1fr}.follow-filters>.ant-input,.follow-filters>.ant-input-affix-wrapper{width:100%}}
</style>
