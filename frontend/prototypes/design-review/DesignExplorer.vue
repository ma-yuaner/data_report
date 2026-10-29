<template>
  <section class="design-explorer" :class="{'is-compact':compact}">
    <header><h2>GDS 需求与设计工作台 <small>1.0</small></h2><p>{{designRegistry.boundary}}</p><div class="design-actions"><button @click="download('GDS设计基线1.0.json',designRegistry)">导出完整设计包</button><button @click="download('资源治理接口评审摘录.json',apiContract)">导出接口契约</button><button v-if="compact" @click="router.push('/review/design')">完整工作台</button><button v-else @click="router.push('/resource-governance/gds')">进入GDS演示</button></div><p v-if="notice" role="status">{{notice}}</p></header>
    <p class="design-evidence">需求、原型、正式实现、部署、业务验收分别记录。已有聚合字段不证明具备逐请求链路数据；待确认项不会自动转为开发规则。</p>
    <label class="design-search">搜索编号、业务含义或字段<input v-model="query" placeholder="例如 MPIS、白名单、configVersion" /></label>
    <nav class="design-sections"><button v-for="section in sections" :key="section.id" :aria-pressed="active===section.id" @click="active=section.id;focused=''">{{section.title}}（{{(designRegistry[section.id] as any[]).length}}）</button></nav>
    <p v-if="componentId" class="design-context">来自组件：{{componentId}}。下方按稳定需求编号追溯，不以组件存在判定需求完成。</p>
    <div ref="cards" class="design-cards">
      <article v-for="entry in filtered" :id="entry.id" :key="entry.id" :class="{'is-focused':focused===entry.id}">
        <header><strong>{{entry.id}} · {{entry.title}}</strong><span v-if="entry.status">{{entry.status}}</span></header>
        <dl><template v-for="(value,key) in details(entry)" :key="key"><dt>{{labels[key] || key}}</dt><dd v-if="String(key).endsWith('Ids')"><button v-for="id in value" :key="id" class="design-reference" @click="jump(id)">{{id}} · {{lookup(id)?.title}}</button></dd><dd v-else-if="key==='route'"><button @click="router.push(String(value))">打开原页面：{{value}}</button></dd><dd v-else-if="Array.isArray(value)"><ol><li v-for="item in value" :key="item">{{item}}</li></ol></dd><dd v-else>{{value}}</dd></template></dl>
        <div v-if="active==='requirements'" class="design-relations"><strong>关联字段</strong><button v-for="field in designRegistry.fields.filter(item=>item.requirementIds.includes(entry.id))" :key="field.id" @click="jump(field.id)">{{field.title}} · {{field.status}}</button></div>
        <button v-if="active==='scenarios'&&scenarioId(entry.id)" @click="rehearse(entry.id)">进入此场景</button>
      </article><p v-if="!filtered.length">没有符合搜索条件的条目，请缩小搜索范围。</p>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { designRegistry } from './generated'
import apiContract from './openapi.review.json'
import { selectScenario } from './runtime'
const props=defineProps<{compact?:boolean;componentId?:string;requirementId?:string}>()
const router=useRouter(),query=ref(''),active=ref<Collection>('requirements'),focused=ref(''),notice=ref(''),cards=ref<HTMLElement|null>(null)
type Collection='sources'|'requirements'|'rules'|'pages'|'fields'|'apis'|'tables'|'scenarios'
const sections:{id:Collection;title:string}[]=[{id:'requirements',title:'需求'},{id:'sources',title:'来源'},{id:'rules',title:'规则'},{id:'pages',title:'原型索引'},{id:'fields',title:'字段'},{id:'apis',title:'接口'},{id:'tables',title:'表与数据来源'},{id:'scenarios',title:'场景'}]
const labels:Record<string,string>={kind:'分类',content:'内容',evidence:'证据',status:'状态',purpose:'用途',gap:'缺口与待确认',implementation:'实现',deployment:'部署',acceptance:'验收',owner:'负责人',sourceIds:'需求来源',pageIds:'页面',ruleIds:'规则',apiIds:'接口',tableIds:'数据表',description:'说明',question:'待确认',route:'路由',component:'组件',key:'字段标识',type:'类型',api:'接口字段',storage:'存储映射',requirementIds:'关联需求',method:'方法',path:'路径',request:'请求',response:'响应',grain:'粒度',execution:'执行状态',steps:'操作步骤',expected:'预期',scope:'适用范围'}
const filtered=computed<any[]>(()=>designRegistry[active.value].filter(item=>JSON.stringify(item).toLowerCase().includes(query.value.trim().toLowerCase())))
function details(entry:any):Record<string,any>{return Object.fromEntries(Object.entries(entry).filter(([key])=>!['id','title','status'].includes(key)))}
function lookup(id:string){return sections.flatMap(section=>designRegistry[section.id] as any[]).find(item=>item.id===id)}
async function jump(id:string){const section=sections.find(section=>(designRegistry[section.id] as any[]).some(item=>item.id===id));if(!section)return;query.value='';active.value=section.id;focused.value=id;await nextTick();cards.value?.querySelector(`[id="${id}"]`)?.scrollIntoView({block:'nearest',behavior:'smooth'})}
function download(name:string,value:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice.value='已发起本机下载，未上传任何数据。'}
function scenarioId(id:string){return ({'SCN-NORMAL':'normal','SCN-EMPTY':'empty','SCN-PARTIAL':'partial','SCN-ERROR':'error','SCN-DENIED':'denied'} as Record<string,string>)[id]}
function rehearse(id:string){const value=scenarioId(id);if(value){selectScenario(value);void router.push('/resource-governance/gds')}}
watch(()=>props.requirementId,value=>{if(value)void jump(value)},{immediate:true})
</script>
<style>
.design-explorer{padding:24px;max-width:1400px;margin:0 auto;color:#182235;overflow-wrap:anywhere}.design-explorer.is-compact{padding:16px;max-width:none;margin:0}.design-explorer h2{font-size:21px;margin:0 0 8px}.design-explorer small{font-size:12px;color:#64748b}.design-explorer p{font-size:13px;line-height:1.8}.design-explorer button{cursor:pointer;background:#fff;border:1px solid #cbd5e1;border-radius:5px;padding:5px 9px;font:inherit;color:#26364b;text-align:left}.design-actions,.design-sections{display:flex;flex-wrap:wrap;gap:8px}.design-actions button{font-size:12px}.design-evidence{background:#fff8e7;padding:10px 12px;border-left:3px solid #d89f24}.design-search{display:grid;gap:6px;font-size:12px;margin:16px 0}.design-search input{font:inherit;padding:8px;border:1px solid #cbd5e1;border-radius:5px;width:100%;box-sizing:border-box}.design-sections{margin-bottom:16px}.design-sections button[aria-pressed=true]{border-color:#2563eb;color:#2563eb;background:#eff6ff}.design-context{color:#64748b}.design-cards{display:grid;gap:14px}.design-cards article{padding:16px;background:#fff;border:1px solid #dbe3ee;border-radius:7px;scroll-margin:12px}.design-cards article.is-focused{border-color:#2563eb}.design-cards article>header{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between}.design-cards article>header>span{font-size:11px;color:#52637a;background:#f1f5f9;padding:2px 6px;border-radius:4px}.design-cards dl{margin:12px 0 0;display:grid;grid-template-columns:110px minmax(0,1fr);gap:8px 14px;font-size:13px}.design-cards dt{color:#64748b}.design-cards dd{margin:0;min-width:0}.design-cards ol{margin:0;padding-left:20px}.design-cards .design-reference{font-size:12px;margin:0 6px 6px 0;color:#2563eb}.design-relations{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px;align-items:center;font-size:12px}.design-relations strong{width:100%}.is-compact .design-cards dl{grid-template-columns:1fr;gap:3px}.is-compact .design-cards dd{margin-bottom:8px}.is-compact .design-cards article{padding:12px}.is-compact h2{font-size:17px}
@media(max-width:760px){.design-explorer{padding:16px}.design-cards dl{grid-template-columns:1fr;gap:3px}.design-cards dd{margin-bottom:8px}}
</style>
