<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { TableColumnsType } from 'ant-design-vue'
import FilterPanel from '@/components/FilterPanel.vue'
import { http, type ApiEnvelope } from '@/api/http'

const ruleFields = [
  ['auditVoluntary', '审核 · 自愿'], ['auditInvoluntary', '审核 · 非自愿'],
  ['operationVoluntary', '操作 · 自愿改期'], ['operationInvoluntary', '操作 · 非自愿改期'],
] as const
const accountFields = [
  ['platform', 'OTA 平台'], ['owner', '负责人'], ['department', '部门'],
  ['group', '群名称'], ['channel', '沟通方式'],
] as const
type RuleKey = typeof ruleFields[number][0]
type FieldKey = RuleKey | typeof accountFields[number][0] | 'auditMode'
type Limit = Record<FieldKey, string> & { id: string; sourceRow?: number }
type Settings = { revision: number; rows: Limit[] }
const endpoint = '/v1/analysis/change-sla/limits'
const state = ref<Settings>()
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const platform = ref<string>()
const conditional = ref(false)
const open = ref(false)
const draft = ref<Partial<Limit>>({})
const editRevision = ref<number>()
const file = ref<HTMLInputElement>()
const platforms = computed(() => [...new Set(state.value?.rows.map(row => row.platform))].sort((a,b)=>a.localeCompare(b,'zh-CN'))
  .map(value=>({value,label:value})))
const rows = computed(() => (state.value?.rows ?? []).filter(row =>
  (!platform.value || row.platform===platform.value) &&
  (!conditional.value || ruleFields.some(([key])=>row[key] && !/^\d+\s*[HM]$/i.test(row[key])))
))
const columns: TableColumnsType<Limit> = [
  {title:'OTA 平台',dataIndex:'platform',width:130,fixed:'left'},
  {title:'部门 / 负责人',key:'owner',width:130},
  {title:'审单',dataIndex:'auditMode',width:75},
  ...ruleFields.map(([key,title])=>({title,key,dataIndex:key,width:165})),
  {title:'沟通方式 / 群名称',key:'contact',width:220},
  {title:'来源',key:'source',width:100},
  {title:'操作',key:'actions',width:85,fixed:'right'},
]
const ruleKeys = new Set<string>(ruleFields.map(([key])=>key))
const canSave = computed(()=>Boolean(draft.value.platform?.trim() && ruleFields.some(([key])=>draft.value[key]?.trim())))
function reset(){ platform.value=undefined; conditional.value=false }
function edit(row?: Limit){
  error.value=''; message.value=''; draft.value=row?{...row}:{auditMode:'是'}
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
async function submit(body: FormData | { revision: number; action: 'upsert'; record: Partial<Limit> }, success: string){
  if(saving.value || loading.value)return
  error.value=''; message.value=''; saving.value=true
  try {
    const prior=state.value?.revision
    state.value=(await http.post<ApiEnvelope<Settings>>(endpoint,body)).data.data
    message.value=state.value.revision===prior ? '源表中的配置已存在，保留已录入的版本。' : success
    open.value=false
  } catch (failure) {error.value=describe(failure)}
  finally {saving.value=false}
}
function save(){
  if(editRevision.value===undefined || !canSave.value)return
  return submit({revision:editRevision.value,action:'upsert',record:draft.value},'时限配置已保存')
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
  <div>
      <a-space wrap class="limits-note">
        <a-tag v-if="state?.revision">配置版本 {{state.revision}}</a-tag>
        <a-button :disabled="loading || saving || !state" @click="file?.click()">导入原始 Excel</a-button>
        <a-button type="primary" :disabled="loading || saving || !state" @click="edit()">新增配置</a-button>
        <input ref="file" type="file" hidden accept=".xlsx" @change="importFile" />
      </a-space>
    <a-alert class="limits-note" type="info" show-icon message="新批次优先匹配平台时限。未命中时审核 60 分钟、操作 90 分钟，已判定记录保留原规则。" />
    <a-alert v-if="message" class="limits-note" type="success" show-icon :message="message" />
    <a-alert v-if="error && !open" class="limits-note" type="error" show-icon :message="error">
      <template #action><a-button size="small" @click="reload">重新加载</a-button></template>
    </a-alert>
    <FilterPanel stacked @reset="reset">
      <label><span>OTA 平台</span><a-select v-model:value="platform" :options="platforms" allow-clear show-search placeholder="全部平台" /></label>
      <label><span>时限规则</span><a-checkbox v-model:checked="conditional">仅看分段或文字规则</a-checkbox></label>
      <template #actions><a-button :loading="loading" :disabled="saving" @click="reload">刷新</a-button></template>
    </FilterPanel>
    <a-card :title="'时限配置 · '+rows.length+' 条'">
      <a-table :columns="columns" :data-source="rows" :loading="loading || saving" row-key="id" size="small"
        :scroll="{x:1400}" :pagination="{pageSize:10,showSizeChanger:false}" :locale="{emptyText:'暂无匹配配置，可导入原始 Excel 或新增'}">
        <template #bodyCell="{column,record}">
          <a-button v-if="column.key==='actions'" type="link" size="small" @click="edit(record)">查看 / 编辑</a-button>
          <span v-else-if="column.key==='owner'">{{record.department || '—'}} / {{record.owner || '—'}}</span>
          <div v-else-if="column.key==='contact'" class="rule-text">{{record.channel || '—'}}<br v-if="record.group" /><small>{{record.group}}</small></div>
          <span v-else-if="column.key==='source'">{{record.sourceRow ? 'Excel 第 '+record.sourceRow+' 行' : '手工录入'}}</span>
          <span v-else-if="ruleKeys.has(String(column.key))" class="rule-text">{{record[String(column.key)] || '待补充'}}</span>
        </template>
      </a-table>
    </a-card>
    <a-drawer v-model:open="open" width="min(760px,100vw)" :title="draft.id?'查看 / 编辑时限配置':'新增时限配置'" :mask-closable="false">
      <a-alert v-if="error" class="limits-note" type="error" show-icon :message="error" />
      <a-form layout="vertical" @finish="save">
        <div class="form-grid">
          <a-form-item v-for="[key,label] in accountFields" :key="key" :label="label" :required="key==='platform'">
            <a-input v-model:value="draft[key]" :maxlength="2000" />
          </a-form-item>
          <a-form-item label="审单"><a-select v-model:value="draft.auditMode" allow-clear :options="['是','手工','否'].map(value=>({value,label:value}))" /></a-form-item>
          <a-form-item v-for="[key,label] in ruleFields" :key="key" :label="label">
            <a-textarea v-model:value="draft[key]" :rows="3" :maxlength="2000" placeholder="例如 1H，或逐行填写分段条件和时限" />
          </a-form-item>
        </div>
        <a-space><a-button type="primary" html-type="submit" :loading="saving" :disabled="!canSave || loading">保存配置</a-button>
          <a-button :disabled="saving" @click="open=false; error=''">取消</a-button></a-space>
      </a-form>
    </a-drawer>
  </div>
</template>

<style scoped>
.limits-note { margin-bottom:16px; }
.form-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px; }
.rule-text { white-space:pre-wrap;overflow-wrap:anywhere; }
.rule-text small { color:#68778a; }
@media(max-width:550px) { .form-grid { grid-template-columns:1fr; } }
</style>
