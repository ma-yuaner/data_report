import { readdirSync, readFileSync, existsSync } from 'node:fs'
import { dirname, resolve, relative, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { parse } from '@vue/compiler-sfc'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../src')
const files = []
function walk(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name)
    if (entry.isDirectory()) walk(path)
    else if (/\.(ts|vue)$/.test(path) && !path.endsWith('.d.ts')) files.push(path)
  }
}
walk(root)
const graph = new Map(files.map((path) => [path, new Set()]))
const errors = []
const label = (path) => relative(root, path).replaceAll('\\', '/')

function targetOf(source, specifier) {
  if (!specifier.startsWith('.') && !specifier.startsWith('@/')) return
  const base = specifier.startsWith('@/') ? resolve(root, specifier.slice(2)) : resolve(dirname(source), specifier)
  return [base, `${base}.ts`, `${base}.vue`, resolve(base, 'index.ts')].find((path) => graph.has(path))
}

for (const path of files) {
  const source = readFileSync(path, 'utf8')
  const descriptor = extname(path) === '.vue' ? parse(source, { filename: path }).descriptor : undefined
  const script = descriptor
    ? `${descriptor.script?.content || ''}\n${descriptor.scriptSetup?.content || ''}`
    : source
  const ast = ts.createSourceFile(path, script, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  function visit(node) {
    let specifier
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
      specifier = node.moduleSpecifier.text
    } else if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      if (node.arguments[0] && ts.isStringLiteral(node.arguments[0])) specifier = node.arguments[0].text
    }
    if (specifier) {
      const target = targetOf(path, specifier)
      if (target) {
        graph.get(path).add(target)
        const from = label(path)
        const to = label(target)
        if (from.startsWith('features/') && (to.startsWith('views/') || (to.startsWith('api/') && to !== 'api/http.ts'))) {
          errors.push(`${from}: feature depends on legacy entry ${to}`)
        }
        if (from.startsWith('utils/') && /^(features|views|stores|router)\//.test(to)) {
          errors.push(`${from}: shared utility depends on ${to}`)
        }
      } else if (specifier.startsWith('.') || specifier.startsWith('@/')) {
        const base = specifier.startsWith('@/') ? resolve(root, specifier.slice(2)) : resolve(dirname(path), specifier)
        if (!existsSync(base)) errors.push(`${label(path)}: unresolved local import ${specifier}`)
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(ast)
}

const done = new Set()
const active = []
function visit(path) {
  if (active.includes(path)) {
    errors.push(`Frontend cycle: ${[...active.slice(active.indexOf(path)), path].map(label).join(' -> ')}`)
    return
  }
  if (done.has(path)) return
  active.push(path)
  for (const target of graph.get(path)) visit(target)
  active.pop()
  done.add(path)
}
for (const path of files) visit(path)
console.log(`Frontend architecture: ${files.length} modules checked`)
for (const error of errors) console.error(error)
process.exitCode = errors.length ? 1 : 0
