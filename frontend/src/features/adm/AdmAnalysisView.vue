<template>
 <div class="adm-analysis">
  <PageHeader eyebrow="ADM OPERATIONS" title="ADM 业务分析" description="先定位跟进积压，再分析航司、供应商及问题根因；点击分组可下钻。">
   <a-space><a-button @click="router.push({name:'adm-cases',query:{scope:'mine'}})">任务台账</a-button><a-button v-if="canNotify" @click="openSettings">提醒与阶段时限</a-button></a-space>
  </PageHeader>
  <a-alert v-if="error" type="error" :message="error" show-icon />
  <a-card v-if="canAnalyze" class="panel" size="small">
   <a-space wrap><span>下发日期</span><a-input v-model:value="query.startDate" type="date" /><span>至</span><a-input v-model:value="query.endDate" type="date" />
    <a-select v-model:value="query.dimension" :options="dimensions" style="width:170px" /><a-button type="primary" :loading="loading" @click="load(1)">查询</a-button><a-button @click="reset">清除下钻条件</a-button><a-button :loading="exporting" @click="exportReport">导出本次分析</a-button>
   </a-space>
   <div class="scope-tags"><a-tag v-for="(value,key) in scope" :key="key" closable @close.prevent="removeFilter(String(key))">{{ dimensionLabel(String(key)) }}：{{ displayBucket(String(key),value) }}</a-tag></div>
  </a-card>
  <template v-if="canAnalyze && data">
   <p class="muted">{{ data.scope }} · {{ data.generatedAt }}</p>
   <div class="metrics"><a-card v-for="item in metrics" :key="item.label" size="small"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></a-card></div>
   <div class="charts">
    <a-card title="各阶段当前积压" size="small"><div v-for="stage in data.stages" :key="stage.stage" class="bar-row" @click="drill('stage',stage.stage)"><span>{{ stageName(stage.stage) }}</span><a-progress :percent="percent(stage.pendingCount,stageMax)" :show-info="false" /><b>{{ stage.pendingCount || 0 }}</b><small>超时 {{ stage.overdueCount || 0 }} · 平均 {{ stage.avgHours ?? '—' }}h</small></div><a-empty v-if="!data.stages.length" /></a-card>
    <a-card title="下发主单数量趋势" size="small"><div class="trend"><div v-for="day in data.trend" :key="day.day" class="trend-day"><span>{{ day.caseCount }}</span><i :style="{height:Math.max(2,percent(day.caseCount,trendMax))+'px'}" /><small>{{ String(day.day).slice(5) }}</small></div><a-empty v-if="!data.trend.length" /></div><p class="muted">按主单去重，不代表历史积压趋势。阶段停留优先使用流转日志，缺失时从建单时间起算。</p></a-card>
   </div>
   <a-card :title="dimensionLabel(query.dimension)+'对比'" class="panel" size="small"><p class="muted">金额口径：{{ data.amountBasis }}。跨平台或人员分组的主单数不可相加。</p>
    <a-table :data-source="data.groups" :pagination="false" row-key="bucket" size="small" :columns="groupColumns"><template #bodyCell="{column,record}"><a-button v-if="column.key==='bucket'" type="link" @click="drill(query.dimension,record.bucket)">{{ record.label }}</a-button></template></a-table>
   </a-card>
   <a-card title="问题与跟进明细" class="panel" size="small"><a-table :loading="loading" :data-source="rows.items" :columns="rowColumns" :pagination="{current:rows.page,total:rows.total,pageSize:50,showSizeChanger:false}" :scroll="{x:1450}" :row-key="(row:Fields)=>`${row.caseId}-${row.lineId||0}`" @change="(page:any)=>loadRows(page.current)">
    <template #bodyCell="{column,record}">
     <a-button v-if="column.key==='adm'" type="link" @click="openCase(record.caseId)">{{ record.admNo }}</a-button>
     <a-tag v-else-if="column.key==='risk'" :color="record.overdue?'red':record.soon?'orange':'default'">{{ record.overdue?'超时':record.soon?'临期':record.active?'正常':'已完成' }}</a-tag>
    </template>
   </a-table></a-card>
  </template>
  <a-alert v-else-if="!canAnalyze" type="info" message="当前账号未获ADM业务分析权限；可按授权配置提醒。" />
  <a-drawer v-model:open="detailOpen" title="ADM详情" width="min(1280px,96vw)" destroy-on-close><AdmDetailView v-if="selectedCase" :panel="{caseId:selectedCase}" @close="detailOpen=false" @changed="load(1)" /></a-drawer>
  <a-modal v-model:open="settingsOpen" title="每日提醒与阶段时限" width="min(900px,96vw)" :confirm-loading="savingSettings" @ok="saveSettings">
   <a-alert v-if="settingsError" type="error" :message="settingsError" />
   <a-alert type="info" message="每天09:30全量提醒、16:30只提醒临期和超时（北京时间）；默认关闭。选择正式群后再启用，首次启用需服务器开启外部通知开关。" />
   <a-form layout="vertical"><a-form-item label="自动提醒"><a-switch v-model:checked="settings.enabled" /></a-form-item>
    <a-form-item label="企业微信群"><a-select v-model:value="settings.endpointId" :options="endpoints" placeholder="复用通知中心配置的有效群" /></a-form-item>
    <a-form-item label="每天一到两个提醒时间"><a-select v-model:value="settings.times" mode="tags" placeholder="09:30、16:30" /></a-form-item>
    <a-form-item label="中台页面地址"><a-input v-model:value="settings.baseUrl" placeholder="例如 http://中台地址:1818" /></a-form-item>
    <a-alert v-if="settings.deliveryEnabled===false" type="warning" message="服务器外部发送开关尚未开启，保存配置不会发送消息。" />
    <h4>阶段目标时限（小时，建议初值，可调整）</h4><div class="sla-grid"><label v-for="(hours,stage) in settings.slaHours" :key="stage">{{ stageName(String(stage)) }}<a-input-number v-model:value="settings.slaHours[stage]" :min="1" :max="720" /></label></div>
   </a-form>
   <a-button :loading="previewing" @click="previewMessage">预览提醒（不发送）</a-button><pre v-if="previewText" class="preview">{{ previewText }}</pre>
   <h4>最近发送记录</h4><a-table :data-source="settings.history||[]" :columns="historyColumns" size="small" row-key="id" :pagination="{pageSize:5}" />
  </a-modal>
 </div>
</template>
<script setup lang="ts">
import {computed,onMounted,reactive,ref} from 'vue'
import {useRouter} from 'vue-router'
import {message} from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import {useAuthStore} from '@/stores/auth'
import AdmDetailView from './AdmDetailView.vue'
import {operationsApi,causeOptions} from './operationsApi'
import {errorText,type Fields} from './api'
const auth=useAuthStore(),router=useRouter()
const canAnalyze=computed(()=>auth.user?.isAdmin||auth.user?.permissions?.includes('adm.analysis'))
const canNotify=computed(()=>auth.user?.isAdmin||auth.user?.permissions?.includes('adm.notify.manage'))
const dimensions=[['stage','处理阶段'],['person','当前跟进人'],['airline','航司'],['supplier','供应商'],['platform','平台'],['category','业务分类'],['penalty','罚单事项'],['cause','根本原因'],['leader','组长'],['operator','操作员'],['source','ADM来源']].map(([value,label])=>({value,label}))
const stageNames:Fields={LEADER_DECISION:'恢复判断',OWNER_RECOVERY:'待操作恢复',RECOVERING:'正在恢复',RECOVERED:'待录入订单',NOT_REQUIRED:'待录入订单',PENDING_LEADER:'待分配组长',PENDING_OPERATOR:'待派单',PENDING_ACCEPT:'待接单',PROCESSING:'办理中',PENDING_REVIEW:'待审核',WAITING_DIFF:'待匹配差异单',WAITING_COLLECTION:'待回款',COMPLETED:'已完成',TRANSFER_ACCEPT:'待确认转派'}
const stageName=(value:string)=>stageNames[value]||value
const dimensionLabel=(value:string)=>dimensions.find(item=>item.value===value)?.label||value
const displayBucket=(key:string,value:any)=>key==='stage'?stageName(value):key==='cause'?causeOptions.find(item=>item.value===value)?.label||value:value
const date=(d:Date)=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
const query=reactive<Fields>({startDate:date(new Date(Date.now()-29*86400000)),endDate:date(new Date()),dimension:'stage'})
const scope=reactive<Fields>({}),data=ref<Fields|null>(null),rows=ref<Fields>({items:[],total:0,page:1}),loading=ref(false),error=ref('')
let request=0
const parameters=()=>({...query,...scope})
async function load(page=1){if(!canAnalyze.value)return;const seq=++request;loading.value=true;error.value='';try{const [a,b]=await Promise.all([operationsApi.analysis(parameters()),operationsApi.rows({...parameters(),page})]);if(seq===request){data.value=a;rows.value=b}}catch(e){if(seq===request)error.value=errorText(e)}finally{if(seq===request)loading.value=false}}
async function loadRows(page=1){loading.value=true;try{rows.value=await operationsApi.rows({...parameters(),page})}catch(e){error.value=errorText(e)}finally{loading.value=false}}
const exporting=ref(false)
async function exportReport(){exporting.value=true;try{const response=await operationsApi.report(parameters());const url=URL.createObjectURL(response.data);const link=document.createElement('a');link.href=url;link.download='ADM业务分析.xlsx';link.click();window.setTimeout(()=>URL.revokeObjectURL(url),60000)}catch(e){error.value=errorText(e)}finally{exporting.value=false}}
function drill(key:string,value:string){scope[key]=value;void load(1)}
function removeFilter(key:string){delete scope[key];void load(1)}
function reset(){Object.keys(scope).forEach(key=>delete scope[key]);void load(1)}
const metrics=computed(()=>{const t=data.value?.totals||{};const resolved=Number(t.succeeded||0)+Number(t.failed||0);return [{label:'主单数',value:t.caseCount||0},{label:'主单冻结人民币',value:t.masterAmount||'0.00'},{label:'当前待办项',value:t.pendingCount||0},{label:'超时项',value:t.overdueCount||0},{label:'原因待查明项',value:t.unknownCount||0},{label:'申诉成功率',value:resolved?(Number(t.succeeded||0)*100/resolved).toFixed(1)+'%':'—'}]})
const stageMax=computed(()=>Math.max(1,...(data.value?.stages||[]).map((row:Fields)=>Number(row.pendingCount||0))))
const trendMax=computed(()=>Math.max(1,...(data.value?.trend||[]).map((row:Fields)=>Number(row.caseCount||0))))
const percent=(value:any,max:number)=>Math.min(100,Number(value||0)*100/max)
const groupColumns=[{title:'分组（点击下钻）',key:'bucket'},{title:'主单数',dataIndex:'caseCount'},{title:'明细数',dataIndex:'lineCount'},{title:'金额（CNY）',dataIndex:'amount'},{title:'当前待办项',dataIndex:'pendingCount'}]
const rowColumns=[{title:'ADM主单',key:'adm',fixed:'left'},{title:'当前阶段',dataIndex:'stageName'},{title:'跟进人',dataIndex:'person'},{title:'已停留(h)',dataIndex:'elapsedHours'},{title:'应完成时间',dataIndex:'dueAt'},{title:'风险',key:'risk'},{title:'航司',dataIndex:'airline'},{title:'供应商',dataIndex:'supplier'},{title:'平台',dataIndex:'platform'},{title:'根因',dataIndex:'causeName'},{title:'原因说明',dataIndex:'causeDetail'},{title:'阻塞原因',dataIndex:'blockingReason'}]
const detailOpen=ref(false),selectedCase=ref(0)
function openCase(id:number){selectedCase.value=id;detailOpen.value=true}
const settingsOpen=ref(false),settings=reactive<Fields>({slaHours:{},times:['09:30','16:30'],enabled:false,history:[]}),endpoints=ref<Fields[]>([]),settingsError=ref(''),savingSettings=ref(false),previewing=ref(false),previewText=ref('')
async function openSettings(){settingsOpen.value=true;settingsError.value='';try{Object.assign(settings,await operationsApi.settings());const items=await operationsApi.endpoints();endpoints.value=(items as any).map((row:Fields)=>({value:String(row.id),label:row.name}))}catch(e){settingsError.value=errorText(e)}}
async function saveSettings(){savingSettings.value=true;try{Object.assign(settings,await operationsApi.saveSettings(settings));void message.success('提醒和阶段时限已保存');settingsOpen.value=false;if(canAnalyze.value)await load()}catch(e){settingsError.value=errorText(e)}finally{savingSettings.value=false}}
async function previewMessage(){previewing.value=true;try{previewText.value=(await operationsApi.preview()).text}catch(e){settingsError.value=errorText(e)}finally{previewing.value=false}}
const historyColumns=[{title:'计划时段',dataIndex:'slotKey'},{title:'发送结果',dataIndex:'status',customRender:({text}:any)=>({CLAIMED:'已占用 / 待核对',SENT:'发送成功',FAILED:'发送失败',UNKNOWN:'结果不明',SKIPPED:'无待办，跳过'} as Fields)[text]||text},{title:'待办项',dataIndex:'taskCount'},{title:'完成时间',dataIndex:'finishedAt'}]
onMounted(()=>load())
</script>
<style scoped>
.adm-analysis{padding:24px}.panel{margin-top:16px}.metrics{display:grid;grid-template-columns:repeat(6,minmax(100px,1fr));gap:12px;margin:16px 0}.metrics strong{display:block;font-size:22px;margin-top:8px}.charts{display:grid;grid-template-columns:1fr 1fr;gap:16px}.bar-row{display:grid;grid-template-columns:120px 1fr 40px;align-items:center;gap:8px;cursor:pointer;padding:5px 0}.bar-row small{grid-column:2/4;color:#64748b}.trend{display:flex;gap:8px;align-items:end;min-height:145px;overflow:auto}.trend-day{min-width:36px;display:flex;flex-direction:column;align-items:center;gap:4px}.trend-day i{display:block;background:#1677ff;width:18px}.trend-day small{font-size:10px}.scope-tags{margin-top:12px}.muted{color:#64748b;font-size:12px}.sla-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.sla-grid label{display:flex;justify-content:space-between;gap:8px}.preview{white-space:pre-wrap;background:#f5f7fa;padding:12px;max-height:320px;overflow:auto}@media(max-width:1000px){.charts{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(3,1fr)}}
</style>
