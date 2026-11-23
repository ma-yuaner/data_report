import { readFile, writeFile } from 'node:fs/promises'

const source = 'src/layouts/sidebar-menu.json'
const menu = JSON.parse(await readFile(new URL(`../../${source}`, import.meta.url), 'utf8'))
function convert({ key, label, children }) {
  return {
    id: key,
    title: label,
    route: children ? '' : key,
    disabled: false,
    children: (children ?? []).map(convert),
  }
}
const nodes = menu.map(convert)
const count = nodes => nodes.reduce((total, node) => total + (node.children.length ? count(node.children) : 1), 0)
await writeFile(new URL('./system-navigation.ts', import.meta.url), `// Generated from ${source} by generate-system-navigation.mjs. Do not hand-edit.\nexport interface SystemMenuNode { id:string; title:string; route:string; disabled:boolean; children:SystemMenuNode[] }\nexport const systemMenus: SystemMenuNode[] = ${JSON.stringify(nodes, null, 2)}\nexport const systemMenuSource = '${source}'\n`, 'utf8')
console.log(`Production navigation snapshot: ${nodes.length} top-level entries, ${count(nodes)} leaf entries.`)
