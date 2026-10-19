import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const sourceRoot = join(root, 'src')
const mainSource = readFileSync(join(sourceRoot, 'main.ts'), 'utf8')
const registration = mainSource.match(/;\[([\s\S]*?)\]\.forEach\(component => app\.use\(component\)\)/)?.[1] ?? ''
const componentByTag = {
  'a-alert': 'Alert', 'a-avatar': 'Avatar', 'a-badge': 'Badge',
  'a-breadcrumb': 'Breadcrumb', 'a-breadcrumb-item': 'Breadcrumb',
  'a-button': 'Button', 'a-card': 'Card', 'a-checkbox': 'Checkbox',
  'a-checkbox-group': 'Checkbox', 'a-col': 'Col', 'a-config-provider': 'ConfigProvider',
  'a-date-picker': 'DatePicker', 'a-range-picker': 'DatePicker',
  'a-descriptions': 'Descriptions', 'a-descriptions-item': 'Descriptions',
  'a-divider': 'Divider', 'a-drawer': 'Drawer', 'a-dropdown': 'Dropdown',
  'a-empty': 'Empty', 'a-form': 'Form', 'a-form-item': 'Form',
  'a-input': 'Input', 'a-input-password': 'Input', 'a-input-search': 'Input',
  'a-textarea': 'Input', 'a-input-number': 'InputNumber',
  'a-layout': 'Layout', 'a-layout-content': 'Layout', 'a-layout-header': 'Layout',
  'a-layout-sider': 'Layout', 'a-list': 'List', 'a-list-item': 'List',
  'a-menu': 'Menu', 'a-menu-divider': 'Menu', 'a-menu-item': 'Menu', 'a-sub-menu': 'Menu',
  'a-modal': 'Modal', 'a-pagination': 'Pagination', 'a-progress': 'Progress',
  'a-radio': 'Radio', 'a-radio-button': 'Radio', 'a-radio-group': 'Radio', 'a-result': 'Result',
  'a-row': 'Row', 'a-segmented': 'Segmented', 'a-select': 'Select',
  'a-space': 'Space', 'a-spin': 'Spin', 'a-steps': 'Steps', 'a-switch': 'Switch',
  'a-table': 'Table', 'a-table-column': 'Table', 'a-tab-pane': 'Tabs', 'a-tabs': 'Tabs', 'a-tag': 'Tag',
  'a-timeline': 'Timeline', 'a-tooltip': 'Tooltip',
}

const vueFiles = []
const visit = (directory) => {
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) visit(path)
    else if (path.endsWith('.vue')) vueFiles.push(path)
  }
}
visit(sourceRoot)

const missing = []
for (const path of vueFiles) {
  const source = readFileSync(path, 'utf8')
  const tags = new Set([...source.matchAll(/<\/?(a-[a-z0-9-]+)/g)].map(match => match[1]))
  for (const tag of tags) {
    const plugin = componentByTag[tag]
    if (!plugin) missing.push(`${relative(root, path)} 使用了未登记检查映射的 <${tag}>`)
    else if (!new RegExp(`\\b${plugin}\\b`).test(registration)) {
      missing.push(`${relative(root, path)} 使用 <${tag}>，但 main.ts 未注册 ${plugin}`)
    }
  }
}

if (missing.length) {
  console.error(missing.join('\n'))
  process.exit(1)
}
console.log(`Ant Design Vue 组件注册检查通过：${vueFiles.length} 个页面组件`)
