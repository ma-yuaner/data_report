<template>
 <div class="analytics">
  <FilterPanel :instant="false" :show-reset="false" :loading="loading" hint="每小时刷新当天分析；查询只读汇总，历史范围需单独加工，单次最多31天。"><template #period><DateRangeField v-model:start="start" v-model:end="end" /></template><template #actions><a-button type="primary" :loading="loading" @click="load">查询分析</a-button></template></FilterPanel>
  <a-alert v-if="error" type="error" show-icon :message="error" /><a-alert v-if="data && !data.dataFreshness.complete" type="warning" show-icon message="所选期间部分日期未同步，当前分析仅含已发布数据" />
  <a-alert v-if="pendingMessage" type="info" show-icon :message="pendingMessage" description="当天分析等待小时任务刷新；历史范围需单独加工。若目录未同步，须先完成对应日期清洗。页面只检查结果，不实时逐单计算。" />
  <a-alert v-if="data?.lastErrorCode" type="warning" show-icon message="本次刷新未确认成功，展示最近可读取的成功快照" :description="data.lastErrorCode" />
  <a-alert v-else-if="snapshotLate" type="warning" show-icon message="分析快照最近30分钟尚未核对，请检查调度运行状态" />
  <p v-if="data" class="muted">已查询：{{ data.period.startDate }} 至 {{ data.period.endDate }}（出票日期）<br />分析源快照：{{ formatDateTimeDisplay(data.sourceCutoff) }}；最近核对：{{ formatDateTimeDisplay(data.checkedAt) }}；目录最近同步：{{ formatDateTimeDisplay(data.dataFreshness.newestSyncedAt) }}。{{ data.refreshPending ? '已请求刷新，先展示上次成功结果。' : '人工认定将在下一次成功刷新后反映。' }}</p>
  <div class="analysis-metrics"><div><span>目录订单数</span><strong>{{ data?.metrics.orders ?? '—' }}</strong></div><div><span>自动形成结论占比</span><strong>{{ ratio(data?.metrics.autoConcluded) }}</strong><small>自动通过＋疑似问题 / 目录订单</small></div><div><span>自动通过占比</span><strong>{{ ratio(data?.metrics.autoPassed) }}</strong></div><div><span>人工核实占比</span><strong>{{ ratio(data?.metrics.humanReviewed) }}</strong><small>当前有效人工结论 / 目录订单</small></div><div><span>人工确认有问题</span><strong>{{ data?.metrics.humanProblems ?? '—' }}</strong></div><div><span>计入差错订单</span><strong>{{ data?.metrics.includedErrors ?? '—' }}</strong></div></div>
  <a-alert v-if="data?.metrics.profitMissing" type="warning" show-icon :message="`${data.metrics.profitMissing} 单利润未同步或缺失；受影响分类不展示利润合计，不以0代替。`" />
  <div class="analysis-charts"><section class="chart-panel"><h2>各类型订单利润与亏损</h2><p>订单全部出票明细利润原值合计，CNY；亏损利润仅汇总负利润订单。</p><BaseChart v-if="data?.categories.length" :option="profitOption" chart-label="各盈亏原因类型的总利润和亏损利润" /><a-empty v-else description="暂无分类数据" /></section><section class="chart-panel"><h2>业务部门问题分布</h2><p>按人工确认问题订单数排列前10；业务归属不代表责任认定。</p><BaseChart v-if="data?.departments.length" :option="departmentOption" chart-label="业务部门人工问题及计入差错订单数" /><a-empty v-else description="暂无部门数据" /></section></div>
  <section class="chart-panel"><h2>分类分析明细</h2><a-table :columns="columns" :data-source="data?.categories || []" row-key="key" :pagination="{pageSize:10}" :scroll="{x:1100}"><template #bodyCell="{column,record}"><span v-if="column.key==='profit'">{{ record.totalProfit ?? '未同步／缺失' }}</span><span v-else-if="column.key==='loss'">{{ record.lossProfit ?? '未同步／缺失' }}</span></template></a-table></section>
  <p v-for="note in data?.notes || []" :key="note" class="muted">{{ note }}</p>
 </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { Alert as AAlert, Button as AButton, Empty as AEmpty, Table as ATable } from 'ant-design-vue'
import BaseChart from '@/components/BaseChart.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import DateRangeField from '@/components/DateRangeField.vue'
import { http, type ApiEnvelope } from '@/api/http'
import type { RiskCatalogFreshness } from '@/api/riskVerification'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
interface Group {key:string;label:string;orders:number;problemOrders:number;includedErrors:number;profitMissing:number;totalProfit:string|null;lossProfit:string|null}
interface Analytics {status:'ready';sourceCutoff:string;generatedAt:string;checkedAt:string;refreshPending:boolean;lastErrorCode:string|null;period:{startDate:string;endDate:string};metrics:{orders:number;autoPassed:number;autoConcluded:number;humanReviewed:number;humanProblems:number;includedErrors:number;profitMissing:number};categories:Group[];departments:Group[];notes:string[];dataFreshness:RiskCatalogFreshness}
const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date())
const start=ref(today),end=ref(today),loading=ref(false),error=ref(''),data=ref<Analytics>(),pendingMessage=ref('')
interface PendingSnapshot {status:'pending';message:string;lastErrorCode?:string|null}
let epoch=0,alive=true,timer:ReturnType<typeof setTimeout>|undefined
let applied={startDate:start.value,endDate:end.value}
onBeforeUnmount(()=>{alive=false;epoch++;if(timer)clearTimeout(timer)});onMounted(load)
async function read(token:number){
 const response=await http.get<ApiEnvelope<Analytics|PendingSnapshot>>('/v1/risk-verification/analytics',{params:{...applied}})
 if(!response.data.success)throw new Error(response.data.message)
 if(!alive||token!==epoch)return
 error.value=''
 if(response.data.data.status==='ready'){data.value=response.data.data;pendingMessage.value=''}
 else{data.value=undefined;pendingMessage.value=response.data.data.message+(response.data.data.lastErrorCode?`（${response.data.data.lastErrorCode}）`:'')}
}
function schedule(token:number){
 if(!alive||token!==epoch)return
 if(timer)clearTimeout(timer)
 timer=setTimeout(async()=>{
  if(!alive||token!==epoch)return
  if(!document.hidden){try{await read(token)}catch(e){if(alive&&token===epoch)error.value=e instanceof Error?e.message:'分析快照读取失败'}}
  schedule(token)
 },pendingMessage.value||data.value?.refreshPending?30000:60000)
}
async function load(){
 const token=++epoch;if(timer)clearTimeout(timer)
 applied={startDate:start.value,endDate:end.value};loading.value=true;error.value='';data.value=undefined;pendingMessage.value=''
 try{
  const request=await http.post<ApiEnvelope<unknown>>('/v1/risk-verification/analytics/requests',{...applied})
  if(!request.data.success)throw new Error(request.data.message)
  if(alive&&token===epoch)await read(token)
 }catch(e){if(alive&&token===epoch)error.value=e instanceof Error?e.message:'分析快照读取失败'}
 finally{if(alive&&token===epoch){loading.value=false;schedule(token)}}
}
const snapshotLate=computed(()=>{
 if(!data.value?.checkedAt)return false
 const value=data.value.checkedAt.replace(' ','T')
 const timestamp=Date.parse(/[zZ]$|[+-]\d{2}:\d{2}$/.test(value)?value:`${value}+08:00`)
 return Number.isFinite(timestamp)&&Date.now()-timestamp>30*60000
})

const ratio=(value?:number)=>data.value?.metrics.orders&&value!=null?`${(value/data.value.metrics.orders*100).toFixed(1)}%`:'—'
const profitOption=computed(()=>({tooltip:{trigger:'axis'},legend:{data:['总利润','亏损利润']},grid:{left:76,right:20,top:45,bottom:90},xAxis:{type:'category',data:(data.value?.categories||[]).map(c=>c.label),axisLabel:{rotate:25}},yAxis:{type:'value',name:'CNY'},series:[{name:'总利润',type:'bar',data:(data.value?.categories||[]).map(c=>c.totalProfit==null?null:Number(c.totalProfit)),itemStyle:{color:'#2c68d7'}},{name:'亏损利润',type:'bar',data:(data.value?.categories||[]).map(c=>c.lossProfit==null?null:Number(c.lossProfit)),itemStyle:{color:'#cf5b55'}}]}))
const departmentOption=computed(()=>({tooltip:{trigger:'axis'},legend:{data:['问题订单','计入差错']},grid:{left:120,right:24,top:45,bottom:30},xAxis:{type:'value',minInterval:1},yAxis:{type:'category',inverse:true,data:(data.value?.departments||[]).slice(0,10).map(c=>c.label)},series:[{name:'问题订单',type:'bar',data:(data.value?.departments||[]).slice(0,10).map(c=>c.problemOrders),itemStyle:{color:'#d9824c'}},{name:'计入差错',type:'bar',data:(data.value?.departments||[]).slice(0,10).map(c=>c.includedErrors),itemStyle:{color:'#cf5b55'}}]}))
const columns=[{title:'盈亏原因类型',dataIndex:'label',width:230},{title:'订单数',dataIndex:'orders',width:100},{title:'总利润（CNY）',key:'profit',width:170},{title:'亏损利润（CNY）',key:'loss',width:170},{title:'人工问题订单',dataIndex:'problemOrders',width:140},{title:'计入差错',dataIndex:'includedErrors',width:110},{title:'利润缺失订单',dataIndex:'profitMissing',width:140}]
</script>
<style scoped>
.analytics{display:grid;gap:20px}.analysis-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.analysis-metrics>div{display:grid;gap:8px;padding:20px;background:white;border:1px solid #e4e9ef;border-radius:8px}.analysis-metrics strong{font-size:28px;color:#182235}.analysis-metrics span{font-size:14px}.analysis-metrics small,.muted{font-size:12px;color:#738298}.analysis-charts{display:grid;grid-template-columns:1fr 1fr;gap:20px}.chart-panel{padding:20px;background:white;border:1px solid #e4e9ef;border-radius:8px;min-width:0}.chart-panel h2{font-size:18px;margin:0 0 8px}.chart-panel p{font-size:12px;color:#738298}.chart-panel :deep(.base-chart){height:360px;width:100%}@media(max-width:1100px){.analysis-charts{grid-template-columns:1fr}}@media(max-width:650px){.analysis-metrics{grid-template-columns:1fr 1fr}}
</style>
