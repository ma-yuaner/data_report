import { readFile } from 'node:fs/promises'
import { parse as sfcParse } from '@vue/compiler-sfc'
import { parse } from '@vue/compiler-dom'
const controls=new Set(['a-input','a-textarea','a-input-number','a-select','a-checkbox','a-switch','a-radio-group','a-radio','DateField','AccountSelect','input'])
const buttons=new Set(['a-button','button','router-link','summary'])
const layers=new Set(['a-modal','a-drawer','FormDialog'])
const plain=node=>node.type===2?node.content:(node.children||[]).map(plain).join('')
const attr=(node,name)=>node.props.find(prop=>prop.type===6&&prop.name===name)?.value?.content
const directive=(node,name)=>node.props.find(prop=>prop.type===7&&prop.name===name)
export async function inspectFile(path){
  const source=await readFile(path,'utf8'),descriptor=sfcParse(source).descriptor
  if(!descriptor.template)return {entries:[],source}
  const template=descriptor.template.content,tree=parse(template),script=descriptor.scriptSetup?.content||'',file=path.split(/[\\/]/).pop(),component=file.replace('.vue',''),entries=[],edits=[]
  let serial=0
  function visit(node,ancestors=[]){
    if(node.type!==1){for(const child of node.children||[])visit(child,ancestors);return}
    const field=controls.has(node.tag),action=buttons.has(node.tag),layer=layers.has(node.tag),tab=node.tag==='a-tab-pane',table=node.tag==='a-table',tabs=node.tag==='a-tabs',display=node.tag==='a-descriptions-item'||node.tag==='a-descriptions'
    if(field||action||layer||tab||table||tabs||display){
      const binding=directive(node,'model')?.exp?.content || attr(node,'aria-label') || directive(node,'on')?.exp?.content || ''
      const parentLabel=[...ancestors].reverse().find(parent=>parent.tag==='label')
      const title=attr(node,'title')||attr(node,'label')||attr(node,'tab')||attr(node,'aria-label')||plain(parentLabel || node).replace(/\s+/g,' ').trim()||({field:'字段',action:'操作',layer:'操作窗口',tab:'页签',table:'数据表',tabs:'页签导航',display:'展示字段'}[field?'field':action?'action':layer?'layer':tab?'tab':display?'display':tabs?'tabs':'table'])
      const key=`ADM04:${component}:${++serial}`,kind=field?'field':action?'action':layer?'layer':tab?'tab':display?'display':tabs?'tabs':'table'
      const condition=[...ancestors,node].map(item=>directive(item,'if')?.exp?.content).filter(Boolean).join('；')
      const list=[...ancestors,node].map(item=>directive(item,'for')?.exp?.content).find(value=>/^field in /.test(value||''))
      let variants=[]
      if(list){const listName=/field in (\w+)/.exec(list)?.[1];const block=listName&&new RegExp(`const ${listName}[^=]*=\\s*\\[([\\s\\S]*?)\\]\\s*(?:\\r?\\n|as)`).exec(script)?.[1];if(block){variants=[...block.matchAll(/\[\s*'([^']+)'\s*,\s*'([^']+)'\s*\]/g)].map(match=>({key:match[1],name:match[2]}));if(!variants.length)variants=[...block.matchAll(/\{\s*key:\s*'([^']+)'\s*,\s*label:\s*'([^']+)'[^}]*\}/g)].map(match=>({key:match[1],name:match[2],object:true}))}}
      const base={id:key,component,file:`frontend/src/features/adm/${file}`,kind,title,binding,condition,control:node.tag,required:!!parentLabel&&plain(parentLabel).includes('*'),limit:attr(node,'maxlength')||node.props.find(prop=>prop.type===7&&prop.arg?.content==='maxlength')?.exp?.content||'',options:node.props.find(prop=>prop.type===7&&prop.arg?.content==='options')?.exp?.content||'',placeholder:attr(node,'placeholder')||'',...(node.tag==='a-descriptions-item'?{fieldKey:/(?:record|line)\??\.(\w+)/.exec(node.loc.source)?.[1]}:{})}
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
export function liveAnnotation(){return {name:'adm-live-component-prd',enforce:'pre',async transform(code,id){const filename=id.split('?')[0];if(id.includes('?')||!filename.endsWith('.vue')||!(/\/src\/features\/adm\//.test(filename.replaceAll('\\','/'))||filename.replaceAll('\\','/').endsWith('/src/components/FormDialog.vue')))return;return {code:(await inspectFile(filename)).source,map:null}}}}
