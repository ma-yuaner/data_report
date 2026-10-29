import { readFile, writeFile } from 'node:fs/promises'
import { parse } from '@vue/compiler-dom'

// Read the actual production sidebar; never import its stores, authentication or API calls.
const source = await readFile(new URL('../../src/layouts/AppLayout.vue', import.meta.url), 'utf8')
const template = source.slice(source.indexOf('<template>') + 10, source.indexOf('</template>\r\n\r\n<script') > 0 ? source.indexOf('</template>\r\n\r\n<script') : source.lastIndexOf('</template>'))
const root = parse(template)
const elements = node => (node.children || []).filter(child => child.type === 1)
const findMenu = node => node.tag === 'a-menu' ? node : elements(node).map(findMenu).find(Boolean)
const attribute = (node, name) => node.props.find(prop => prop.type === 6 && prop.name === name)?.value?.content
const text = node => node.type === 2 ? node.content : (node.children || []).map(text).join('')
const isTitle = node => node.tag === 'template' && node.props.some(prop => prop.type === 7 && prop.name === 'slot' && prop.arg?.content === 'title')
function convert(node) {
  const id = attribute(node,'key')
  if(!id) throw Error('Production menu is missing a static key; update the prototype mapping.')
  const titleSlot=elements(node).find(isTitle)
  const title=(titleSlot ? text(titleSlot) : (node.children || []).filter(child=>child.tag!=='template').map(text).join('')).trim()
  const children=elements(node).filter(child=>['a-menu-item','a-sub-menu'].includes(child.tag)).map(convert)
  return {id,title,route:id.startsWith('/')?id:'',disabled:node.props.some(prop=>prop.type===6&&prop.name==='disabled'),children}
}
const menu=findMenu(root)
if(!menu)throw Error('Production sidebar menu not found')
const nodes=elements(menu).filter(node=>['a-menu-item','a-sub-menu'].includes(node.tag)).map(convert)
const count=nodes=>nodes.reduce((total,node)=>total+(node.children.length?count(node.children):1),0)
await writeFile(new URL('./system-navigation.ts',import.meta.url),`// Generated from src/layouts/AppLayout.vue by generate-system-navigation.mjs. Do not hand-edit.\nexport interface SystemMenuNode { id:string; title:string; route:string; disabled:boolean; children:SystemMenuNode[] }\nexport const systemMenus: SystemMenuNode[] = ${JSON.stringify(nodes,null,2)}\nexport const systemMenuSource = 'src/layouts/AppLayout.vue'\n`,'utf8')
console.log(`Production navigation snapshot: ${nodes.length} top-level entries, ${count(nodes)} leaf entries (including disabled placeholders).`)
