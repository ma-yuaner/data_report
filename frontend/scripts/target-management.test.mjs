import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const source = await readFile(resolve(root, 'src/views/TargetManagementView.vue'), 'utf8')

test('all target scenes show target month and copy action', () => {
  assert.match(source, /title: '目标月份', dataIndex: 'period'/)
  assert.match(source, /@click="openCopy\(record\)"/)
  assert.match(source, /copyMode: Boolean\(copyingSourcePeriod\.value\)/)
})

test('target copy defaults to the following month without reusing item ids', () => {
  assert.match(source, /period: nextMonth\(row\.period\), itemId: undefined, itemIds: \{\}/)
})
