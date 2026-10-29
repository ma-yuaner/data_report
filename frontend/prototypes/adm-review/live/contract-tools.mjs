import { readFile } from 'node:fs/promises'
import { parse as sfcParse } from '@vue/compiler-sfc'
import { parse } from '@vue/compiler-dom'
const controls=new Set(['a-input','a-textarea','a-input-number','a-select','a-checkbox','a-switch','a-radio-group','a-radio','a-date-picker','a-range-picker','a-segmented','DateField','AccountSelect','input'])
const buttons=new Set(['a-button','button','router-link','summary'])
const layers=new Set(['a-modal','a-drawer','FormDialog'])
const plain=node=>node.type===2?node.content:(node.children||[]).map(plain).join('')
const attr=(node,name)=>node.props.find(prop=>prop.type===6&&prop.name===name)?.value?.content
const directive=(node,name)=>node.props.find(prop=>prop.type===7&&prop.name===name)
export async function inspectFile(path){
  const source=await readFile(path,'utf8'),descriptor=sfcParse(source).descriptor
  if(!descriptor.template)return {entries:[],source}
  const template=descriptor.template.content,tree=parse(template),script=descriptor.scriptSetup?.content||'',file=path.split(/[\\/]/).pop(),component=file.replace('.vue',''),entries=[],edits=[]
  const normalized=path.replaceAll('\\','/'),sourceFile=`frontend/${normalized.split('/frontend/')[1] || `src/features/adm/${file}`}`,prefix=/resource-governance|GdsRouteGovernanceView|ResourceGovernanceView/.test(normalized)?'RG01':'ADM04'
  let serial=0
  function visit(node,ancestors=[]){
    if(node.type!==1){for(const child of node.children||[])visit(child,ancestors);return}
    const field=controls.has(node.tag),action=buttons.has(node.tag),layer=layers.has(node.tag),tab=node.tag==='a-tab-pane',table=node.tag==='a-table',tabs=node.tag==='a-tabs',display=node.tag==='a-descriptions-item'||node.tag==='a-descriptions'||node.tag==='a-table-column',chart=node.tag==='BaseChart'
    if(field||action||layer||tab||table||tabs||display||chart){
      const binding=directive(node,'model')?.exp?.content || attr(node,'aria-label') || directive(node,'on')?.exp?.content || node.props.find(prop=>prop.type===7&&prop.arg?.content==='option')?.exp?.content || ''
      const parentLabel=[...ancestors].reverse().find(parent=>parent.tag==='label')
      const title=attr(node,'title')||attr(node,'label')||attr(node,'tab')||attr(node,'aria-label')||plain(parentLabel || node).replace(/\s+/g,' ').trim()||({field:'字段',action:'操作',layer:'操作窗口',tab:'页签',table:'数据表',tabs:'页签导航',display:'展示字段',chart:'统计图表'}[field?'field':action?'action':layer?'layer':tab?'tab':display?'display':tabs?'tabs':chart?'chart':'table'])
      const key=`${prefix}:${component}:${++serial}`,kind=field?'field':action?'action':layer?'layer':tab?'tab':display?'display':tabs?'tabs':chart?'chart':'table'
      const condition=[...ancestors,node].map(item=>directive(item,'if')?.exp?.content).filter(Boolean).join('；')
      const list=[...ancestors,node].map(item=>directive(item,'for')?.exp?.content).find(value=>/^field in /.test(value||''))
      let variants=[]
      if(list){const listName=/field in (\w+)/.exec(list)?.[1];const block=listName&&new RegExp(`const ${listName}[^=]*=\\s*\\[([\\s\\S]*?)\\]\\s*(?:\\r?\\n|as)`).exec(script)?.[1];if(block){variants=[...block.matchAll(/\[\s*'([^']+)'\s*,\s*'([^']+)'\s*\]/g)].map(match=>({key:match[1],name:match[2]}));if(!variants.length)variants=[...block.matchAll(/\{\s*key:\s*'([^']+)'\s*,\s*label:\s*'([^']+)'[^}]*\}/g)].map(match=>({key:match[1],name:match[2],object:true}))}}
      const base={id:key,component,file:sourceFile,kind,title,binding,condition,control:node.tag,required:!!parentLabel&&plain(parentLabel).includes('*'),limit:attr(node,'maxlength')||node.props.find(prop=>prop.type===7&&prop.arg?.content==='maxlength')?.exp?.content||'',options:node.props.find(prop=>prop.type===7&&prop.arg?.content==='options')?.exp?.content||'',placeholder:attr(node,'placeholder')||'',...(node.tag==='a-descriptions-item'?{fieldKey:/(?:record|line)\??\.(\w+)/.exec(node.loc.source)?.[1]}:{})}
      if(variants.length){for(const variant of variants)entries.push({...base,id:`${key}:${variant.key}`,title:variant.name,binding:binding.replace(/field\[0\]|field\.key/g,`'${variant.key}'`),fieldKey:variant.key});edits.push({offset:node.loc.start.offset+1+node.tag.length,text:` :data-prd="'${key}:' + ${variants[0].object?'field.key':'field[0]'}"`})}
      else {entries.push(base);edits.push({offset:node.loc.start.offset+1+node.tag.length,text:` data-prd="${key}"`})}
      if(['a-modal','a-drawer'].includes(node.tag)&&!node.props.some(prop=>prop.name==='get-container'||prop.arg?.content==='get-container'))edits.push({offset:node.loc.start.offset+1+node.tag.length,text:' :get-container="false"'})
    }
    for(const child of node.children||[])visit(child,[...ancestors,node])
  }
  visit(tree)
  let updated=template
  for(const edit of edits.sort((a,b)=>b.offset-a.offset))updated=updated.slice(0,edit.offset)+edit.text+updated.slice(edit.offset)
  const start=descriptor.template.loc.start.offset
  let output=source.slice(0,start)+updated+source.slice(start+template.length)
  if(component==='FormDialog')output=output.replace('Modal.confirm({',"Modal.confirm({ getContainer: () => document.querySelector('.live-viewport') || document.body,")
  return {entries,source:output}
}
export function liveAnnotation(){return {name:'live-component-prd',enforce:'pre',async transform(code,id){const filename=id.split('?')[0],normalized=filename.replaceAll('\\','/');if(normalized.endsWith('/src/stores/gdsRouteGovernance.ts')&&!id.includes('?'))return {code:code.replace("'gds-route-governance-review-state-v1'","'product-review-resource-governance-v01'"),map:null};if(id.includes('?')||!filename.endsWith('.vue')||!(/\/src\/features\/(adm|resource-governance)\//.test(normalized)||/\/src\/views\/(GdsRouteGovernanceView|ResourceGovernanceView)\.vue$/.test(normalized)||normalized.endsWith('/src/components/FormDialog.vue')))return;let output=(await inspectFile(filename)).source;if(/ResourceGovernancePage|GdsRouteGovernanceView/.test(normalized))output=output.replaceAll('实际数据 · MySQL ADS','合成样例 · 未连接MySQL').replaceAll('Hive实际数据','本机航线样例').replaceAll('航线视图已接入Hive日汇总','本机模拟航线日汇总（未连接Hive）').replaceAll('直接读取lywz.dws_gds_airroute_day','正式组件预期读取lywz.dws_gds_airroute_day，本原型仅使用本机样例').replaceAll('航线视图已经接入真实Hive；','本原型没有连接真实Hive；');return {code:output,map:null}}}}
