import { copyFile, mkdir, readFile, writeFile, constants } from 'node:fs/promises'

// Generated artifacts and raw inputs stay outside the Git checkout.
const workspace = new URL('../../../../', import.meta.url)
const output = new URL('产品评审台/', workspace)
const inbox = new URL('产品评审资料/ADM/', workspace)
const artifacts = [
  [new URL('../adm-review/dist/index.html', import.meta.url), '产品原型工作台_1.0.html'],
  [new URL('../design-review/设计基线_1.0.html', import.meta.url), 'GDS需求与设计基线_1.0.html'],
  [new URL('../adm-review/dist/index.html', import.meta.url), '资源治理原页面评审_DEMO_0.2.html'],
  [new URL('../resource-review/PRD_0.2.html', import.meta.url), '资源治理PRD_0.2.html'],
  [new URL('./dist/index.html', import.meta.url), 'index.html'],
  [new URL('../adm-review/dist/index.html', import.meta.url), 'ADM产品验收台_DEMO_0.4.html'],
  [new URL('../adm-review/使用说明_0.4.html', import.meta.url), 'ADM产品验收台_先看使用说明.html'],
  [new URL('../adm-review/PRD_0.4.html', import.meta.url), 'ADM管理PRD_0.4.html'],
]
// Check all inputs before updating the deliverable directory.
for (const [source] of artifacts) {
  const html = await readFile(source, 'utf8')
  if (/<script[^>]+src=|<link[^>]+rel="stylesheet"/.test(html)) throw new Error(`External entry assets remain: ${source}`)
}
await mkdir(output, { recursive: true })
await mkdir(inbox, { recursive: true })
for (const [source, name] of artifacts) await copyFile(source, new URL(name, output))
try {
  await copyFile(new URL('./需求整理模板.txt', import.meta.url), new URL('ADM需求整理模板.txt', inbox), constants.COPYFILE_EXCL)
} catch (error) { if (error.code !== 'EEXIST') throw error }
await writeFile(new URL('产品评审台_打开我.html', workspace), '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta http-equiv="refresh" content="0;url=产品评审台/index.html"><title>打开本地产品评审台</title><a href="产品评审台/index.html">点击进入本地产品评审台</a></html>', 'utf8')
console.log('Generated 产品评审台_打开我.html, 产品评审台/ and 产品评审资料/ADM/ in the workspace root. Existing requirement inputs were preserved.')
