<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Modal, type TableColumnsType } from 'ant-design-vue'
import { http, type ApiEnvelope } from '@/api/http'

const ruleFields = [
  ['auditVoluntary', '审核 · 自愿'], ['auditInvoluntary', '审核 · 非自愿'],
  ['operationVoluntary', '操作 · 自愿改期'], ['operationInvoluntary', '操作 · 非自愿改期'],
] as const
const accountFields = [
  ['owner', '负责人'], ['department', '部门'],
  ['group', '群名称'], ['channel', '沟通方式'],
] as const
type RuleKey = typeof ruleFields[number][0]
type FieldKey = RuleKey | typeof accountFields[number][0] | 'platform' | 'auditMode'
type Band = { fromMinutes: number | null; untilMinutes: number | null; limitMinutes: number | null; includeFrom: boolean; includeUntil: boolean }
type Limit = Record<FieldKey, string> & { id: string; sourceRow?: number; segments?: Partial<Record<RuleKey, Band[]>> }
type Settings = { revision: number; rows: Limit[]; canApplyPlatformBands?: boolean }
const endpoint = '/v1/analysis/change-sla/limits'
const state = ref<Settings>()
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const platform = ref<string>()
const open = ref(false)
const draft = ref<Partial<Limit>>({})
const activeRule = ref<RuleKey>('auditVoluntary')
const ruleOptions = ruleFields.map(([value,label]) => ({ value, label }))
const activeBands = computed(() => draft.value.segments?.[activeRule.value] ?? [])
const editRevision = ref<number>()
const file = ref<HTMLInputElement>()
const platforms = computed(() => [...new Set(state.value?.rows.map(row => row.platform))].sort((a,b)=>a.localeCompare(b,'zh-CN'))
  .map(value=>({value,label:value})))
const rows = computed(() => (state.value?.rows ?? []).filter(row =>
  !platform.value || row.platform===platform.value
))
const columns: TableColumnsType<Limit> = [
  {title:'OTA 平台',dataIndex:'platform',width:130,fixed:'left'},
  {title:'审单',dataIndex:'auditMode',width:75},
  ...ruleFields.map(([key,title])=>({title,key,dataIndex:key,width:155})),
  {title:'来源',key:'source',width:100},
  {title:'操作',key:'actions',width:85,fixed:'right'},
]
const ruleKeys = new Set<string>(ruleFields.map(([key])=>key))
const canSave = computed(()=>Boolean(draft.value.platform?.trim() && ruleFields.some(([key])=>
  draft.value[key]?.trim() || draft.value.segments?.[key]?.length)))
function fixedMinutes(raw?: string) {
  const match = raw?.match(/^(\d+)\s*([HM])$/i)
  return match ? Number(match[1]) * (match[2].toUpperCase() === 'H' ? 60 : 1) : null
}
function setFixed(value: number | string | null) {
  draft.value[activeRule.value] = value == null ? '' : value + 'M'
}
function addBand() {
  const segments = draft.value.segments ??= {}
  const bands = segments[activeRule.value] ??= []
  const prior = bands.at(-1)
  bands.push({ fromMinutes: prior ? prior.untilMinutes : 0, untilMinutes: null, limitMinutes: null,
    includeFrom: !prior?.includeUntil, includeUntil: false })
}
function removeBand(index: number) {
  activeBands.value.splice(index, 1)
}
function edit(row?: Limit){
  error.value=''; message.value=''
  draft.value=row?{...row, segments: JSON.parse(JSON.stringify(row.segments ?? {}))}:{auditMode:'是', segments:{}}
  activeRule.value='auditVoluntary'
  editRevision.value=state.value?.revision
  open.value=true
}
function describe(error: unknown){ return error instanceof Error ? error.message : '请求失败，请稍后重试' }
async function reload(){
  if(loading.value || saving.value)return
  loading.value=true
  error.value=''
  try {state.value=(await http.get<ApiEnvelope<Settings>>(endpoint)).data.data}
  catch (failure) {error.value=describe(failure)}
  finally {loading.value=false}
}
async function submit(body: FormData | { revision: number; action: 'upsert'; record: Partial<Limit> } |
  { revision: number; action: 'apply-platform-bands' }, success: string, unchanged = '源表中的配置已存在，保留已录入的版本。'){
  if(saving.value || loading.value)return
  error.value=''; message.value=''; saving.value=true
  try {
    const prior=state.value?.revision
    state.value=(await http.post<ApiEnvelope<Settings>>(endpoint,body)).data.data
    message.value=state.value.revision===prior ? unchanged : success
    open.value=false
  } catch (failure) {error.value=describe(failure)}
  finally {saving.value=false}
}
function save(){
  if(editRevision.value===undefined || !canSave.value)return
  return submit({revision:editRevision.value,action:'upsert',record:draft.value},'时限配置已保存')
}
function applyPlatformBands() {
  const revision = state.value?.revision
  if (revision === undefined) return
  Modal.confirm({
    title: '应用 TVLK / 飞猪航班分段',
    content: '非自愿审核和操作共用各平台分段。TVLK 距起飞 0 至 72 小时（含）为 2 小时，超过 72 小时为 24 小时。飞猪 12 至不足 26 小时为 8 小时，26 至 50 小时（含）为 20 小时，超过 50 小时为 40 小时，少于 12 小时待确认。',
    okText: '应用分段',
    cancelText: '取消',
    onOk: () => submit({revision, action: 'apply-platform-bands'}, 'TVLK / 飞猪航班分段已保存', '没有待转换的航班分段。'),
  })
}
function duration(minutes: number | null) {
  if (minutes === null) return '待补充'
  return minutes % 60 === 0 ? `${minutes / 60}h` : `${minutes}min`
}
function bandLabel(band: Band) {
  const lower = `${band.includeFrom ? '≥' : '>'}${duration(band.fromMinutes)}`
  const range = band.untilMinutes === null ? lower : `${lower} 且 ${band.includeUntil ? '≤' : '<'}${duration(band.untilMinutes)}`
  return `${range} → ${duration(band.limitMinutes)}`
}
function importFile(event: Event){
  const input=event.target as HTMLInputElement
  const selected=input.files?.[0]
  input.value=''
  if(!selected || !state.value)return
  if(!selected.name.toLowerCase().endsWith('.xlsx') || selected.size>2*1024*1024){
    error.value='请选择不超过 2 MB 的原始 .xlsx 文件。'
    return
  }
  const body=new FormData()
  body.set('revision',String(state.value.revision))
  body.set('file',selected)
  return submit(body,'平台时限已导入')
}
onMounted(reload)
</script>

<template>
  <div class="limits-panel">
    <div class="limits-toolbar">
      <a-space wrap>
        <a-select v-model:value="platform" class="platform-filter" :options="platforms" allow-clear show-search
          placeholder="全部 OTA 平台" aria-label="筛选 OTA 平台" />
        <a-tag v-if="state?.revision">配置版本 {{state.revision}}</a-tag>
        <span v-if="state">{{rows.length}} 条配置</span>
      </a-space>
      <a-space wrap>
        <a-button v-if="state?.canApplyPlatformBands" :disabled="loading || saving" @click="applyPlatformBands">应用 TVLK / 飞猪分段</a-button>
        <a-button :disabled="loading || saving || !state" @click="file?.click()">导入原始 Excel</a-button>
        <a-button type="primary" :disabled="loading || saving || !state" @click="edit()">新增配置</a-button>
        <input ref="file" type="file" hidden accept=".xlsx" @change="importFile" />
      </a-space>
    </div>
    <a-alert type="info" show-icon message="时限从节点开始时间计算。首次判定使用当时生效的配置，已判定记录保留原结果。" />
    <a-alert v-if="message" type="success" show-icon :message="message" />
    <a-alert v-if="error && !open" type="error" show-icon :message="error">
      <template #action><a-button size="small" @click="reload">重新加载</a-button></template>
    </a-alert>
    <a-table :columns="columns" :data-source="rows" :loading="loading || saving" row-key="id" size="small"
      :scroll="{x:1010}" :pagination="{pageSize:10,showSizeChanger:false}" :locale="{emptyText:'暂无匹配配置，可导入原始 Excel 或新增'}">
        <template #bodyCell="{column,record}">
          <a-button v-if="column.key==='actions'" type="link" size="small" @click="edit(record)">查看 / 编辑</a-button>
          <span v-else-if="column.key==='source'">{{record.sourceRow ? 'Excel 第 '+record.sourceRow+' 行' : '手工录入'}}</span>
          <span v-else-if="ruleKeys.has(String(column.key))" class="rule-text">
            <template v-if="record.segments?.[column.key]?.length">
              <span v-for="(band, index) in record.segments[column.key]" :key="index" class="band-summary">{{bandLabel(band)}}</span>
            </template>
            <template v-else>{{record[String(column.key)] || '待补充'}}</template>
          </span>
        </template>
    </a-table>
    <a-drawer v-model:open="open" width="min(760px,100vw)" :title="draft.id?'查看 / 编辑时限配置':'新增时限配置'" :mask-closable="false">
      <a-alert v-if="error" class="limits-note" type="error" show-icon :message="error" />
      <a-form layout="vertical" @finish="save">
        <div class="form-grid">
          <a-form-item label="OTA 平台" required><a-input v-model:value="draft.platform" :maxlength="2000" /></a-form-item>
          <a-form-item label="审单"><a-select v-model:value="draft.auditMode" allow-clear :options="['是','手工','否'].map(value=>({value,label:value}))" /></a-form-item>
        </div>
        <a-card size="small" class="limits-note" title="考核时限">
          <a-select v-model:value="activeRule" :options="ruleOptions" aria-label="选择节点与进单类型" class="limits-note" />
          <a-form-item v-if="!activeBands.length" label="固定完成时限（分钟）">
            <a-input-number :value="fixedMinutes(draft[activeRule])" :min="1" :max="14400" :precision="0" @change="setFixed" />
          </a-form-item>
          <p v-if="draft[activeRule] && fixedMinutes(draft[activeRule])===null" class="rule-text">规则原文：{{draft[activeRule]}}</p>
          <p v-if="activeBands.length">距起飞时间按申请时点计算。勾选「含边界」决定恰好等于上下限时是否命中。</p>
          <div v-for="(band,index) in activeBands" :key="index" class="band-fields">
            <a-form-item label="距起飞下限（分钟）">
              <a-input-number v-model:value="band.fromMinutes" :min="0" :max="525600" :precision="0" />
              <a-checkbox v-model:checked="band.includeFrom">含下限</a-checkbox>
            </a-form-item>
            <a-form-item label="距起飞上限（分钟）">
              <a-input-number v-model:value="band.untilMinutes" :min="1" :max="525600" :precision="0" placeholder="不限" />
              <a-checkbox v-model:checked="band.includeUntil" :disabled="band.untilMinutes==null">含上限</a-checkbox>
            </a-form-item>
            <a-form-item label="完成时限（分钟）"><a-input-number v-model:value="band.limitMinutes" :min="1" :max="14400" :precision="0" /></a-form-item>
            <a-button type="link" danger @click="removeBand(index)">移除此档</a-button>
          </div>
          <a-button :disabled="activeBands.length>=12" @click="addBand">添加航班分段</a-button>
        </a-card>
        <div class="form-grid">
          <a-form-item v-for="[key,label] in accountFields" :key="key" :label="label">
            <a-input v-model:value="draft[key]" :maxlength="2000" />
          </a-form-item>
        </div>
        <a-space><a-button type="primary" html-type="submit" :loading="saving" :disabled="!canSave || loading">保存配置</a-button>
          <a-button :disabled="saving" @click="open=false; error=''">取消</a-button></a-space>
      </a-form>
    </a-drawer>
  </div>
</template>

<style scoped>
.limits-panel { display:grid; min-width:0; gap:16px; }
.limits-toolbar { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; }
.platform-filter { width:200px; max-width:100%; }
.limits-note { margin-bottom:16px; }
.form-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px; }
.band-fields { display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:8px;align-items:center; }
.band-fields :deep(.ant-input-number) { width:100%; }
.band-summary { display:block; }
.rule-text { white-space:pre-wrap;overflow-wrap:anywhere; }
@media(max-width:550px) { .form-grid,.band-fields { grid-template-columns:1fr; } }
</style>
