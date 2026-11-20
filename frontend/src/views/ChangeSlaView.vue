<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import { nodes, stats, timeout, gap, excluded, evaluateErpNodes } from '@/features/change-sla/model'
import type { ErpRecord, ErpSnapshot, SlaRow } from '@/features/change-sla/model'
import type { TableColumnsType } from 'ant-design-vue'
import { http, type ApiEnvelope } from '@/api/http'

const labels = { platform:'平台', air:'航司', owner:'改期员', kind:'改签性质', node:'SLA 节点' }
type Dimension = keyof typeof labels
type DrillType = 'late' | 'gap' | 'excluded' | 'backfill'
type Filters = Partial<Record<Dimension, string>> & { dates?: [string, string]; id: string }
type Bucket = { id: string; values: string[]; rows: SlaRow[] }
const dimensionKeys = Object.keys(labels) as Dimension[]
const options = (list: string[]) => list.map(value => ({label:value,value}))
const dimensionOptions = dimensionKeys.map(value => ({value,label:labels[value]}))
const defaults = (): Filters => ({ id:'' })
const draft = ref(defaults())
const applied = ref(defaults())
const primary = ref<Dimension>('platform')
const secondary = ref<Dimension>()
const onlyAbnormal = ref(false)
const drill = ref<{ keys: Dimension[]; values: string[]; type: DrillType } | null>(null)
const status = ref('')
const record = ref<SlaRow | null>(null)
const erp = ref<ErpSnapshot | null>(null)
const loading = ref(false)
const error = ref('')
const statusOptions = { late:['全部超时','已完成超时','进行中超时'], gap:['全部缺口','待配置','数据异常'], excluded:['全部单列','已撤回','操作驳回'], backfill:['出票时间回填'] }
const isBackfill = (row: SlaRow) => row.endSource === 'latest_issue_time'
const sourceLabel = (source: ErpRecord['endSource']) => ({'':'—',latest_issue_time:'出票时间回填',ACCEPT:'ACCEPT 状态历史',audit_operator_time:'审核操作时间'}[source] || '—')
const data = computed(() => erp.value?.records ?? {audit:[],operation:[]})
const rules = computed(() => erp.value?.rules ?? [])
const evaluated = computed(() => erp.value ? evaluateErpNodes(data.value,rules.value,erp.value.snapshot) : [])
const filterFields = computed(() => dimensionKeys.map(key => ({
  key, label:labels[key], options:options(key==='kind' ? ['改期','改名','改证件','未分类'] : [...new Set(evaluated.value.map(row => row[key]))].sort()),
})))
const rows = computed(() => evaluated.value.filter(row => {
  const { dates, id, ...filters } = applied.value
  return (!id || row.id === id.trim()) &&
    Object.entries(filters).every(([key,value]) => !value || row[key as Dimension] === value)
}))
const visibleNodes = computed(() => applied.value.node ? [applied.value.node] : nodes)
const summary = computed(() => visibleNodes.value.map(node => {
  const data=rows.value.filter(row=>row.node===node)
  const result=stats(data)
  const completed=data.filter(row => row.end !== null && row.elapsed !== null && row.elapsed>=0 && !excluded(row))
  return {node,metrics:[
    ['节点达标率',result.rate], ['已判定节点',result.judged], ['超时节点',result.late],
    ['进行中超时',data.filter(row=>row.state==='进行中超时').length], ['规则或数据缺口',data.filter(gap).length],
    [node===nodes[0]?'撤回':'操作驳回',data.filter(excluded).length],
    ['平均处理耗时',completed.length ? Math.round(completed.reduce((sum,row)=>sum+(row.elapsed ?? 0),0)/completed.length)+' 分钟' : '—'],
    ['节点记录数',new Set(data.map(row=>row.id)).size],
  ]}
}))
const trend = computed(() => visibleNodes.value.flatMap(node => {
  const data=rows.value.filter(row=>row.node===node)
  return [...new Set(data.map(row=>row.created))].sort().map(date=>({node,date,...stats(data.filter(row=>row.created===date))}))
}))
const keys = computed(() => [...new Set([primary.value,secondary.value,'node'].filter((key): key is Dimension => key !== undefined))])
const groups = computed(() => {
  const buckets = new Map<string, Bucket>()
  for (const row of rows.value) {
    const values = keys.value.map(key=>row[key])
    const id = JSON.stringify(values)
    if (!buckets.has(id)) buckets.set(id,{id,values,rows:[]})
    buckets.get(id)?.rows.push(row)
  }
  return [...buckets.values()].map(group=>{
    const info=stats(group.rows)
    return {...group,...info,total:group.rows.length,lateRate:info.judged ? (100*info.late/info.judged).toFixed(1)+'%' : '—',
      active:group.rows.filter(row=>row.state==='进行中超时').length,missing:group.rows.filter(gap).length,
      excluded:group.rows.filter(excluded).length,backfill:group.rows.filter(isBackfill).length}
  }).filter(group=>!onlyAbnormal.value || group.late || group.missing || group.excluded)
    .sort((a,b)=>b.late-a.late || b.active-a.active || b.missing-a.missing || a.id.localeCompare(b.id,'zh-CN'))
})
const numberCol = (title:string,key:string) => ({title,key,dataIndex:key,align:'right' as const,width:118})
const groupColumns = computed(()=>[
  ...keys.value.map((key,index)=>({title:labels[key],key,dataIndex:['values',index],width:140})),
  numberCol('节点总量','total'),numberCol('已判定','judged'),numberCol('超时率','lateRate'),
  numberCol('超时节点','late'),numberCol('进行中超时','active'),numberCol('规则或数据缺口','missing'),numberCol('撤回／操作驳回','excluded'),
  numberCol('出票时间回填','backfill'),
])
const detailColumns: TableColumnsType<SlaRow> = [
  {title:'ERP 单据 ID',key:'id',dataIndex:'id',width:115},
  ...(['node','platform','air','owner','kind'] as const).map(key=>({title:labels[key],dataIndex:key,width:key==='air'?70:100})),
  {title:'状态',key:'state',dataIndex:'state',width:122},
  {title:'耗时 / 目标（分钟）',key:'elapsed',width:165,align:'right'},
  {title:'规则版本',dataIndex:['rule','id'],width:105},
  {title:'结束时间来源',key:'endSource',width:140},
]
const detailTitle = computed(()=>{ const selected=drill.value; return selected ? selected.keys.map((key,i)=>labels[key]+' '+selected.values[i]).join(' × ') : '' })
const detailRows = computed(()=>{
  if (!drill.value) return []
  const { keys, values, type } = drill.value
  return rows.value.filter(row=>keys.every((key,i)=>row[key]===values[i]) &&
    (type==='backfill'?isBackfill(row):status.value==='全部超时'?timeout(row):status.value==='全部缺口'?gap(row):status.value==='全部单列'?excluded(row):row.state===status.value))
})
async function query(){
  if (loading.value) return
  const requested = {...draft.value}
  const params = requested.dates?.length ? {from:requested.dates[0],to:requested.dates[1]} : {}
  loading.value=true
  error.value=''
  try {
    const response = await http.get<ApiEnvelope<ErpSnapshot>>('/v1/analysis/change-sla',{params})
    erp.value=response.data.data
    if (!requested.dates?.length) draft.value.dates=erp.value.dates
    applied.value=requested
    closeDrill()
  } catch (failure) {
    error.value=failure instanceof Error ? failure.message : 'ERP 改签查询失败'
  } finally {
    loading.value=false
  }
}
function reset(){ draft.value=defaults(); void query() }
onMounted(query)
function selectPrimary(){ if (secondary.value===primary.value) secondary.value=undefined; closeDrill() }
function openDrill(group: Bucket,type: DrillType){
  drill.value={keys:[...keys.value],values:group.values,type}
  status.value=statusOptions[type][0]
}
function closeDrill(){ record.value=null; drill.value=null }
const formatter=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})
const duration = (value: number | null) => value === null ? '—' : Number(value.toFixed(2))
const clock = (value: number | null) => value==null ? '—' : formatter.format(value)
</script>

<template>

    <main class="page-wrap sla-review">
      <PageHeader eyebrow="业务分析 / 改签 SLA" title="客服改签 SLA 管理看板"
        :description="erp ? 'ERP 在线只读 · 数据时间 '+clock(erp.snapshot)+'（北京时间）' : '查询 ERP 改签审核和操作时效'" />
      <FilterPanel stacked :instant="false" :loading="loading" @reset="reset">
        <template #period><label class="picker-label">改签创建时间 <a-range-picker v-model:value="draft.dates" value-format="YYYY-MM-DD" /></label></template>
        <label v-for="field in filterFields" :key="field.key"><span>{{field.label}}</span>
          <a-select v-model:value="draft[field.key]" :options="field.options" placeholder="全部" allow-clear show-search />
        </label>
        <label><span>改签单号</span><a-input v-model:value="draft.id" allow-clear placeholder="输入 ERP 审核或改签单 ID" @press-enter="query" /></label>
        <template #actions><a-button type="primary" :loading="loading" @click="query">查询</a-button></template>
      </FilterPanel>
      <a-alert v-if="error" type="error" show-icon :message="error" class="sla-section" />
      <a-spin :spinning="loading">
      <div v-if="erp">
      <a-alert v-if="rules.length<2" type="info" show-icon message="部分节点未配置正式 SLA 阈值，相关记录显示为待配置。" />

      <a-card v-for="section in summary" :key="section.node" :title="section.node" size="small" class="sla-section">
        <div class="sla-metrics">
          <a-statistic v-for="[label,value] in section.metrics" :key="label" :title="label" :value="value" />
        </div>
      </a-card>

      <a-card title="异常研判" class="sla-section">
        <template #extra>
          <a-space wrap>
            <label>主维度 <a-select v-model:value="primary" :options="dimensionOptions.filter(item=>item.value!=='node')" style="width:116px" @change="selectPrimary" /></label>
            <label>交叉维度 <a-select v-model:value="secondary" :options="dimensionOptions.filter(item=>item.value!==primary)" allow-clear placeholder="无" style="width:116px" @change="closeDrill" /></label>
            <label><a-switch v-model:checked="onlyAbnormal" size="small" @change="closeDrill" /> 仅看有异常</label>
          </a-space>
        </template>
        <p class="sla-hint">审核和操作分别统计，按超时节点数降序。点击数量查看对应单据，出票时间回填可单独核查。</p>
        <a-table size="small" row-key="id" :columns="groupColumns" :data-source="groups"
          :pagination="groups.length>10 ? {pageSize:10,showSizeChanger:false} : false" :scroll="{x:groupColumns.reduce((sum,column)=>sum+column.width,0)}"
          :locale="{emptyText:'当前条件下没有可展示的分组'}">
          <template #bodyCell="{column,record:group}">
            <template v-if="column.key==='late' || column.key==='missing' || column.key==='excluded' || column.key==='backfill'">
              <a-button v-if="group[column.key]" type="link" size="small" :danger="column.key==='late'"
                :aria-label="'查看 '+group.values.join(' × ')+' '+column.title+' '+group[column.key]+' 条'"
                @click="openDrill(group,column.key==='missing'?'gap':column.key)">{{group[column.key]}}</a-button>
              <span v-else>0</span>
            </template>
          </template>
        </a-table>
      </a-card>

      <a-card title="处理趋势" class="sla-section" size="small">
        <p class="sla-hint">按改签创建日期 · 达标率 / 超时节点数</p>
        <div v-for="item in trend" :key="item.node+item.date" class="sla-trend"><span>{{item.node}} · {{item.date}}</span>
          <a-progress :percent="parseFloat(item.rate)||0" :show-info="false" size="small" />
          <span>{{item.rate}} / {{item.late}}</span>
        </div>
        <span v-if="!trend.length" class="sla-hint">当前条件下没有可展示的趋势</span>
      </a-card>

      <a-drawer :open="!!drill" :width="'min(1080px, 100vw)'" title="异常单据" @close="closeDrill">
        <a-space wrap class="sla-hint">
          <a-tag color="blue">{{detailTitle}}</a-tag>
          <label>异常类型 <a-select v-model:value="status" :options="options(drill ? statusOptions[drill.type] : [])" style="width:140px" /></label>
          <span>{{detailRows.length}} 条</span>
        </a-space>
        <a-table size="small" row-key="index" :columns="detailColumns" :data-source="detailRows" :scroll="{x:1190}"
          :pagination="detailRows.length>10 ? {pageSize:10,showSizeChanger:false} : false" :locale="{emptyText:'该分组没有此类异常'}">
          <template #bodyCell="{column,record:item}">
            <a-button v-if="column.key==='id'" type="link" size="small" @click="record=item">{{item.id}}</a-button>
            <a-tag v-else-if="column.key==='state'" :color="timeout(item)?'error':'warning'">{{item.state}}</a-tag>
            <span v-else-if="column.key==='elapsed'">{{duration(item.elapsed)}} / {{item.rule?.minutes??'—'}}</span>
            <span v-else-if="column.key==='endSource'">{{sourceLabel(item.endSource)}}</span>
          </template>
        </a-table>
        <a-drawer :open="!!record" :width="'min(720px, 100vw)'" title="节点判定证据" @close="record=null">
          <a-descriptions v-if="record" bordered size="small" :column="1">
            <a-descriptions-item label="ERP 单据 ID">{{record.id}}</a-descriptions-item>
            <a-descriptions-item label="节点与状态">{{record.node}} / {{record.state}}</a-descriptions-item>
            <a-descriptions-item label="平台 / 航司 / 改期员">{{record.platform}} / {{record.air}} / {{record.owner}}</a-descriptions-item>
            <a-descriptions-item label="改签性质">{{record.kind}}</a-descriptions-item><a-descriptions-item label="节点开始">{{clock(record.start)}}</a-descriptions-item>
            <a-descriptions-item label="节点完成">{{clock(record.end)}}</a-descriptions-item>
            <a-descriptions-item label="结束时间来源">{{sourceLabel(record.endSource)}}</a-descriptions-item>
            <a-descriptions-item label="ERP 状态码">{{record.sourceStatus}}</a-descriptions-item>
            <a-descriptions-item label="有效关联数">{{record.linked}}</a-descriptions-item>
            <a-descriptions-item label="SLA 到期">{{clock(record.due)}}</a-descriptions-item>
            <a-descriptions-item label="超时分钟">{{timeout(record) && record.rule && record.elapsed!==null ? duration(record.elapsed-record.rule.minutes) : '—'}}</a-descriptions-item>
            <a-descriptions-item label="判定规则">{{record.rule ? [record.rule.id,record.rule.minutes+' 分钟'].join(' / ') : '—'}}</a-descriptions-item>
          </a-descriptions>
        </a-drawer>
      </a-drawer>

      </div>
      </a-spin>
    </main>

</template>

<style scoped>
.picker-label { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.sla-metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:12px; }
.sla-section { margin-top:16px; }
.sla-section :deep(.ant-card-head-wrapper) { flex-wrap:wrap; gap:8px 12px; }
.sla-hint { color:#69768a; margin-bottom:12px; }
.sla-trend { display:grid; grid-template-columns:155px minmax(40px,1fr) 80px; align-items:center; gap:8px; }
</style>
