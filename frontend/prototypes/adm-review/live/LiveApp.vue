<template>
  <div class="live-review" :class="{'demo-only':!showPrd}">
    <header class="live-review-toolbar"><div><strong>{{isGovernance ? "资源治理" : "ADM"}} 原页面交互原型</strong><small>现有组件复用 / 本机模拟</small></div><div class="live-toolbar-actions"><label>模拟操作人<a-select :value="user.id" :options="demoPeople.map(person=>({value:person.id,label:`${person.name} · ${person.role}`}))" @change="changePerson" /></label><button @click="exportBackup">导出本机备份</button><label class="live-file-label">恢复备份<input type="file" accept=".json" @change="restoreBackup" /></label><button @click="showPrd=!showPrd">{{showPrd?'演示模式':'显示PRD'}}</button></div></header>
    <p class="live-local-note">本机模拟数据，不连接真实账号、订单、通知或财务。菜单/页面/表单来自现有中台；点击组件正常操作，同时定位右侧PRD。</p>
    <div class="live-review-workspace" :style="{'--stage-width':`${split}%`}">
      <section class="live-stage" aria-label="左侧真实组件演示舞台" @click.capture="inspectClick" @focusin.capture="inspectClick">
        <div class="live-system-shell">
          <aside class="live-system-menu"><div class="live-brand">企业数据中心<small>原菜单 · 本机演示</small></div><SystemMenuItem v-for="item in systemMenus" :key="item.id" :node="item" :active="activeMenu" @select="selectMenu" /></aside>
          <div class="live-system-main"><header class="live-system-header"><div><button @click="router.back()">返回</button><span>数据中心 / {{route.meta.section || '原菜单'}} / {{route.meta.title || route.path}}</span></div><button @click="exportStore.drawerOpen=true">导出任务 <span>{{exportStore.items.length}}</span></button></header>
            <div ref="viewport" class="live-viewport"><a-config-provider :get-popup-container="popupContainer"><router-view v-slot="{Component}"><component :is="Component" :key="route.path + user.id" /></router-view></a-config-provider>
              <a-drawer v-model:open="exportStore.drawerOpen" title="导出任务（本机模拟）" :get-container="false" :width="560" :root-style="{position:'absolute'}"><p>复用正式页头任务入口的交互，文件在本机生成，不连接真实任务队列。</p><article v-for="item in exportStore.items" :key="item.id"><h3>{{item.name}}</h3><p>{{item.status}}</p><a-button @click="download(item.name,item.content,'text/csv')">下载本机文件</a-button></article><a-empty v-if="!exportStore.items.length" description="暂无任务，请在台账点击导出" /></a-drawer>
            </div>
          </div>
        </div>
      </section>
      <PanelDivider v-if="showPrd" v-model="split" :min="48" :max="82" />
      <aside v-if="showPrd" class="live-prd" aria-label="右侧组件PRD"><header><span>当前组件 PRD</span><h2>{{guideState.title}}</h2><p>{{guideState.component}} · {{guideState.layer}}</p><small>{{route.fullPath}}</small></header>
        <div class="live-prd-body"><label>查找页面或组件<a-select show-search :value="guideState.id || undefined" :options="moduleDefinitions.map(item=>({value:item.id,label:`${item.component} / ${item.title}`}))" :filter-option="filterDefinition" placeholder="可直接点左侧字段或按钮" @change="selectDefinition" /></label>
          <nav class="live-layer-trail"><strong>当前动态图层</strong><span>页面：{{route.meta.title}}</span><span v-for="(layer,index) in layers" :key="`${layer.kind}:${index}`">{{index+1}}. {{layer.kind}} / {{layer.title}}</span><small v-if="!layers.length">当前无弹窗或抽屉，可从页面按钮打开。</small></nav>
          <h3>功能与字段用途</h3><p>{{spec.purpose}}</p><h3>谁能操作 / 什么条件</h3><p>{{spec.when}}</p><h3>填写或点击后会怎样</h3><p>{{spec.result}}</p>
          <template v-if="currentDefinition"><h3>与正式源码的对应</h3><dl><dt>组件文件</dt><dd>{{currentDefinition.file}}</dd><dt>字段绑定 / 动作</dt><dd>{{currentDefinition.binding || '内容区'}}</dd><dt>控件类型</dt><dd>{{currentDefinition.control}}</dd><dt>选项来源</dt><dd>{{currentDefinition.options || '以当前组件展示为准'}}</dd><dt>显示条件</dt><dd>{{currentDefinition.condition || '当前页面已打开'}}</dd><dt>组件编号</dt><dd>{{currentDefinition.id}}</dd></dl></template>
          <h3>本版边界</h3><p>直接复用现有ADM及资源治理前端。资源治理本版仅建立现状基线，新需求待补充。正式服务端权限、接口、事务及新增业务差异仍需另行接入。本版不发送真实通知、不部署。</p>
          <label>对此组件的意见<a-textarea v-model:value="comment" :rows="3" /></label><a-button @click="saveComment">保存本机意见</a-button><p v-for="note in comments.filter(note=>note.id===guideState.id)" :key="note.at" class="live-comment">{{note.at}} · {{note.text}}</p>
        </div>
      </aside>
    </div><footer class="live-status" role="status">{{feedback || transportStatus.error || transportStatus.last}}</footer>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SystemMenuItem from '../SystemMenuItem.vue'
import PanelDivider from '../../shared/PanelDivider.vue'
import { systemMenus, type SystemMenuNode } from '../system-navigation'
import { demoPeople, setDemoPerson, useAuthStore } from './auth'
import { exportLiveState,restoreLiveState,transportStatus } from './http'
import { exportStore } from './exports'
import { describeResource } from '../../resource-review/semantics'
import { definitions } from './all-definitions'
import { guideState,currentDefinition,describe } from './guide'
import { useGdsRouteGovernanceStore } from '../../../src/stores/gdsRouteGovernance'
const governance=useGdsRouteGovernanceStore()
const router=useRouter(),route=useRoute(),user=useAuthStore().user
const showPrd=ref(true),split=ref(70),viewport=ref<HTMLElement|null>(null),layers=ref<{kind:string;title:string}[]>([]),feedback=ref(''),comment=ref('')
const comments=ref<{id:string;text:string;at:string}[]>([])
try{const saved=localStorage.getItem('adm-live-comments-v04');if(saved)comments.value=JSON.parse(saved)}catch{/* No shared approval implied. */}
const isGovernance=computed(()=>route.path.startsWith('/resource-governance'))
const moduleDefinitions=computed(()=>definitions.filter(item=>item.id.startsWith('RG01:')===isGovernance.value))
const spec=computed(()=>isGovernance.value?describeResource(currentDefinition.value,guideState.title):describe(currentDefinition.value,guideState.title))
const activeMenu=computed(()=>route.path.startsWith('/adm/cases/')?'/adm/cases':route.path)
function popupContainer(trigger?:HTMLElement){return trigger?.parentElement || viewport.value || document.body}
function filterDefinition(input:string,option:any){return String(option.label).toLowerCase().includes(input.toLowerCase())}
function selectDefinition(value:unknown){const entry=definitions.find(item=>item.id===value);if(entry)Object.assign(guideState,{id:entry.id,title:entry.title,component:entry.component})}
function inspectClick(event:Event){const target=event.target instanceof Element?event.target:null,element=target?.closest('[data-prd]') as HTMLElement|null,tab=target?.closest('[role="tab"]');const tabTitle=tab?.textContent?.replace(/\s+/g,' ').trim();const cell=target?.closest('.ant-descriptions-item-content,.ant-descriptions-item-label');const displayTitle=(cell?.matches('.ant-descriptions-item-label')?cell.textContent:cell?.previousElementSibling?.matches('.ant-descriptions-item-label')?cell.previousElementSibling.textContent:target?.closest('.ant-descriptions-item')?.querySelector('.ant-descriptions-item-label')?.textContent)?.replace(/[：:]\s*$/,'').trim();const entry=tabTitle?moduleDefinitions.value.find(item=>item.kind==='tab'&&item.title===tabTitle):displayTitle?moduleDefinitions.value.find(item=>item.kind==='display'&&item.title===displayTitle):definitions.find(item=>item.id===element?.dataset.prd);if(!entry)return;const label=element?.closest('label');let title=entry.title;if(entry.kind==='action'||entry.kind==='tab')title=tabTitle || (element?.textContent || entry.title).replace(/\s+/g,' ').trim().slice(0,100);if(entry.kind==='field'&&label)title=(label.textContent || entry.title).replace(/\s+/g,' ').trim().slice(0,100);Object.assign(guideState,{id:entry.id,title,component:entry.component,layer:layers.value.at(-1)?.kind || '页面'})}
function selectMenu(node:SystemMenuNode){void router.push(node.route || `/reference/${encodeURIComponent(node.id)}`)}
function changePerson(value:unknown){if(layers.value.length&&!confirm('切换模拟人员会关闭当前未保存窗口，是否继续？'))return;setDemoPerson(String(value));guideState.id='';feedback.value=`已切换 ${user.displayName}，业务状态保留。`}
function download(name:string,text:string,type='application/json'){const url=URL.createObjectURL(new Blob(['\uFEFF',text],{type}));const anchor=document.createElement('a');anchor.href=url;anchor.download=name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function exportBackup(){download('产品评审台本机备份.json',JSON.stringify({data:JSON.parse(exportLiveState()),comments:comments.value,governance:{events:governance.events,actions:governance.actions}},null,2))}
async function restoreBackup(event:Event){const file=(event.target as HTMLInputElement).files?.[0];if(!file)return;try{if(file.size>8*1024*1024)throw Error('备份最多8MB');const value=JSON.parse((await file.text()).replace(/^\uFEFF/,''));if(!confirm('恢复将替换当前0.4本机数据，建议先导出备份。是否继续？'))return;restoreLiveState(JSON.stringify(value.data || value));if(value.governance&&Array.isArray(value.governance.events)&&Array.isArray(value.governance.actions)){governance.$patch({events:value.governance.events,actions:value.governance.actions});governance.persist()}if(Array.isArray(value.comments))comments.value=value.comments;await router.replace(isGovernance.value?'/resource-governance/gds':'/adm/cases');feedback.value='备份已恢复，请刷新当前列表。'}catch(error){feedback.value=(error as Error).message}}
function saveComment(){if(!guideState.id||!comment.value.trim()){feedback.value='请先选择一个组件并填写意见';return}comments.value.push({id:guideState.id,text:comment.value.trim(),at:new Date().toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})});comment.value='';try{localStorage.setItem('adm-live-comments-v04',JSON.stringify(comments.value));feedback.value='意见已保存在本机，可随备份导出。'}catch{feedback.value='缓存不足，请导出备份保留意见。'}}
let observer:MutationObserver|undefined,scheduled=false
function readLayers(){scheduled=false;if(!viewport.value)return;const result:{kind:string;title:string}[]=[],elements:HTMLElement[]=[];for(const node of viewport.value.querySelectorAll('.ant-modal-wrap,.ant-drawer-content-wrapper')){const element=node as HTMLElement;if(!element.getClientRects().length||getComputedStyle(element).display==='none')continue;const title=element.querySelector('.ant-modal-title,.ant-drawer-title')?.textContent?.trim();if(title){result.push({kind:element.classList.contains('ant-modal-wrap')?'弹窗':'抽屉',title});elements.push(element)}}if(JSON.stringify(result)!==JSON.stringify(layers.value)){layers.value=result;const top=result.at(-1);if(top){const layerElement=elements.at(-1)!;const candidates=[layerElement.closest('[data-prd]'),...layerElement.querySelectorAll('[data-prd]')].filter(Boolean) as HTMLElement[];const definition=candidates.map(element=>definitions.find(item=>item.id===element.dataset.prd)).find(item=>item?.kind==='layer');if(definition){guideState.id=definition.id;guideState.component=definition.component}guideState.title=top.title;guideState.layer=top.kind}else{guideState.id='';guideState.title=String(route.meta.title || '当前页面');guideState.layer='页面'}}}
onMounted(()=>{observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(readLayers)}});if(viewport.value)observer.observe(viewport.value,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style']})})
watch(()=>route.path,()=>{guideState.id='';guideState.title=String(route.meta.title || '原系统菜单');guideState.component=isGovernance.value ? (/\/(gds|ota)$/.test(route.path)?'ResourceGovernancePage':'GdsRouteGovernanceView') : route.path.includes('/cases/')?'AdmDetailView':'AdmCenterView';guideState.layer='页面';guideState.route=route.fullPath},{immediate:true})
onBeforeUnmount(()=>observer?.disconnect())
</script>
