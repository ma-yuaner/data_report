<template>
  <FormDialog :open="true" title="编辑目录与正文" :busy="busy" :dirty="dirty" :error="error" ok-text="发布新版本" :width="1050" @submit="publish" @cancel="emit('close')">
    <div class="metadata">
      <label>手册名称<a-input v-model:value="draft.name" :maxlength="100" /></label>
      <label>新版本号<a-input v-model:value="draft.policyVersion" :maxlength="60" placeholder="例如 V1.0" /></label>
      <label>生效日起<DateField v-model="draft.start" /></label>
      <label>生效日止<DateField v-model="draft.end" /></label>
      <label>适用范围<a-input v-model:value="draft.scope" :maxlength="1000" /></label>
      <label>来源与变更说明<a-input v-model:value="draft.handbook.source" :maxlength="500" /></label>
    </div>
    <a-space wrap class="editor-actions">
      <a-button :disabled="busy" @click="addChapter">新增章</a-button>
      <a-button :disabled="!active || active.depth === 3 || busy" @click="addChild">新增下级</a-button>
      <a-button :disabled="busy" @click="markdownOpen = !markdownOpen">导入 Markdown</a-button>
      <a-button :disabled="busy" @click="saveDraft">保存当前会话草稿</a-button>
    </a-space>
    <div v-if="markdownOpen" class="markdown">
      <a-textarea v-model:value="markdown" :rows="5" :maxlength="80000" placeholder="# 章标题，## 节标题，### 条款" />
      <a-space wrap>
        <a-button :disabled="busy" @click="previewMarkdown">预览目录</a-button>
        <a-button :disabled="!preview.length || busy" @click="appendMarkdown">追加到手册</a-button>
      </a-space>
      <p v-for="row in previewRows" :key="row.node.id" :style="{marginInlineStart: (row.depth - 1) * 14 + 'px'}">{{ row.number }} {{ row.node.title }}</p>
    </div>
    <div class="editor-grid">
      <nav aria-label="编辑章节">
        <button v-for="row in outline" :key="row.node.id" type="button" class="outline-item"
          :aria-current="row.node.id === selected ? 'location' : undefined" :style="{paddingInlineStart: 8 + (row.depth - 1) * 14 + 'px'}"
          :draggable="!busy" @dragstart="startDrag($event, row.node.id)" @dragover.prevent @drop.prevent="dropBefore(row.node.id)" @dragend="dragged = ''"
          @click="selected = row.node.id">{{ row.number }} {{ row.node.title }}</button>
      </nav>
      <section v-if="active" class="section-editor">
        <label>章节标题<a-input v-model:value="active.node.title" :maxlength="100" /></label>
        <a-space wrap class="editor-actions">
          <a-button :disabled="active.siblings.indexOf(active.node) === 0 || busy" @click="move(-1)">上移</a-button>
          <a-button :disabled="active.siblings.indexOf(active.node) === active.siblings.length - 1 || busy" @click="move(1)">下移</a-button>
          <a-button danger :disabled="busy" @click="removeSection">删除本节</a-button>
        </a-space>
        <label>移动到其他章节<a-select :value="undefined" :options="destinations" placeholder="选择新的上级章节" @change="reparent" /></label>
        <div v-for="(block, i) in active.node.blocks" :key="i" class="content-block">
          <a-space wrap>
            <a-select v-model:value="block.kind" :options="kinds" aria-label="内容块类型" />
            <a-button type="text" danger @click="active.node.blocks.splice(i, 1)">删除内容块</a-button>
          </a-space>
          <a-textarea v-model:value="block.text" :rows="3" :maxlength="4000" aria-label="内容块正文"
            :placeholder="block.kind === 'table' ? '每行一条记录，列之间用 | 分隔，第一行为表头' : '输入内容。列表每行一项。'" />
        </div>
        <a-button @click="active.node.blocks.push({kind: 'paragraph', text: ''})">新增内容块</a-button>
        <div class="case-editor">
          <h3>关联专项案例</h3>
          <a-space wrap>
            <a-input v-model:value="caseQuery" placeholder="案例标题或完整编号" @press-enter="searchCases" />
            <a-button :loading="searching" @click="searchCases">搜索案例库</a-button>
          </a-space>
          <a-select v-if="caseOptions.length" :value="undefined" :options="caseOptions" placeholder="选择要关联的案例" @change="attachCase" />
          <p v-if="caseMessage">{{ caseMessage }}</p>
          <div v-for="item in active.node.cases" :key="item.id">{{ item.title }} <a-button type="text" @click="detachCase(item.id)">移除引用</a-button></div>
        </div>
        <div class="case-editor">
          <h3>培训示例</h3>
          <div v-for="(item, i) in active.node.examples" :key="i" class="content-block">
            <a-input v-model:value="item.title" :maxlength="150" aria-label="示例标题" />
            <a-textarea v-model:value="item.detail" :maxlength="3000" :rows="3" aria-label="示例详情" />
            <a-button type="text" @click="active.node.examples.splice(i, 1)">移除示例</a-button>
          </div>
          <a-button @click="active.node.examples.push({title: '', detail: ''})">新增培训示例</a-button>
        </div>
      </section>
    </div>
  </FormDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button as AButton, Input as AInput, Modal, Select as ASelect, Space as ASpace, message } from 'ant-design-vue'
import { riskFollowup, reviewKey, type FollowCase, type HandbookSection, type ReviewPolicy, type RiskHandbook } from '@/api/riskFollowup'
import { useAuthStore } from '@/stores/auth'
import { handbookOutline, importMarkdown, legacyHandbook, section } from '@/features/risk/riskHandbook'
import DateField from './DateField.vue'
import FormDialog from './FormDialog.vue'

const ATextarea = AInput.TextArea
const props = defineProps<{ initial: ReviewPolicy }>()
const emit = defineEmits<{ close: []; published: [policy: ReviewPolicy] }>()
const kinds = [{ value: 'paragraph', label: '段落' }, { value: 'list', label: '编号列表' }, { value: 'table', label: '表格' }, { value: 'question', label: '问答' }, { value: 'note', label: '提示' }]
const auth = useAuthStore()
const key = `risk-handbook-draft:${auth.user?.id ?? ''}:${props.initial.id}`
const initialHandbook: RiskHandbook = props.initial.handbook || legacyHandbook(props.initial)
const initial = {
  name: props.initial.name, policyVersion: '', start: '', end: '', scope: props.initial.scope,
  handbook: JSON.parse(JSON.stringify(initialHandbook)) as RiskHandbook,
}
function restore(): typeof initial {
  try {
    const cached = sessionStorage.getItem(key)
    if (cached) return JSON.parse(cached) as typeof initial
  } catch { /* Session storage can be disabled on the browser. */ }
  return initial
}
const draft = ref(restore())
const baseline = ref(JSON.stringify(draft.value))
const dirty = computed(() => JSON.stringify(draft.value) !== baseline.value)
const outline = computed(() => handbookOutline(draft.value.handbook.chapters))
const selected = ref(outline.value[0]?.node.id || '')
const dragged = ref('')
const active = computed(() => outline.value.find(row => row.node.id === selected.value))
const destinations = computed(() => {
  const row = active.value
  if (!row) return []
  const subtreeDepth = Math.max(1, ...handbookOutline(row.node.children).map(child => child.depth + 1))
  const parents = outline.value.filter(target => target.node.id !== row.node.id && !target.number.startsWith(row.number + '.')
    && target.depth + subtreeDepth <= 3 && target.node.children !== row.siblings)
    .map(target => ({ value: target.node.id, label: `${target.number} ${target.node.title}` }))
  return row.depth === 1 ? parents : [{ value: 'root', label: '顶级目录' }, ...parents]
})
const busy = ref(false), error = ref(''), markdownOpen = ref(false), markdown = ref('')
const preview = ref<HandbookSection[]>([])
const previewRows = computed(() => handbookOutline(preview.value))
const caseQuery = ref(''), searching = ref(false), caseMessage = ref('')
const matches = ref<FollowCase[]>([])
const caseOptions = computed(() => matches.value.filter(item => !active.value?.node.cases.some(link => link.id === item.id)).map(item => ({ value: item.id, label: item.title })))
let publishKey = '', lastPayload = ''
watch(markdown, () => { preview.value = [] })

function addChapter() {
  const node = section('新章节')
  draft.value.handbook.chapters.push(node)
  selected.value = node.id
}
function addChild() {
  if (!active.value || active.value.depth === 3) return
  const node = section('新小节')
  active.value.node.children.push(node)
  selected.value = node.id
}
function move(delta: number) {
  const row = active.value
  if (!row) return
  const index = row.siblings.indexOf(row.node)
  const target = index + delta
  if (target < 0 || target >= row.siblings.length) return
  row.siblings.splice(index, 1)
  row.siblings.splice(target, 0, row.node)
}
function startDrag(event: DragEvent, id: string) {
  dragged.value = id
  event.dataTransfer?.setData('text/plain', id)
}
function dropBefore(id: string) {
  const source = outline.value.find(row => row.node.id === dragged.value)
  const target = outline.value.find(row => row.node.id === id)
  dragged.value = ''
  if (busy.value || !source || !target || source.node === target.node || source.siblings !== target.siblings) return
  source.siblings.splice(source.siblings.indexOf(source.node), 1)
  source.siblings.splice(source.siblings.indexOf(target.node), 0, source.node)
  selected.value = source.node.id
}
function reparent(value: unknown) {
  const row = active.value
  if (!row || !destinations.value.some(item => item.value === value)) return
  const target = value === 'root' ? draft.value.handbook.chapters : outline.value.find(item => item.node.id === value)?.node.children
  if (!target) return
  row.siblings.splice(row.siblings.indexOf(row.node), 1)
  target.push(row.node)
}
function removeSection() {
  const row = active.value
  if (!row) return
  Modal.confirm({ title: '删除本节及下级条款？', content: row.node.title, okText: '删除', cancelText: '取消', onOk: () => {
    row.siblings.splice(row.siblings.indexOf(row.node), 1)
    selected.value = outline.value[0]?.node.id || ''
  } })
}
function previewMarkdown() {
  error.value = ''
  try { preview.value = importMarkdown(markdown.value) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : 'Markdown 解析失败' }
}
function appendMarkdown() {
  if (!preview.value.length) return
  draft.value.handbook.chapters.push(...preview.value)
  selected.value = preview.value[0].id
  markdown.value = ''
  preview.value = []
  markdownOpen.value = false
}
function saveDraft() {
  try {
    const snapshot = JSON.stringify(draft.value)
    sessionStorage.setItem(key, snapshot)
    baseline.value = snapshot
    message.success('草稿已保存在当前浏览器会话')
  } catch { error.value = '浏览器无法保存会话草稿，请保持当前编辑窗口打开。' }
}
async function searchCases() {
  if (searching.value) return
  searching.value = true
  caseMessage.value = ''
  try {
    const params = { q: caseQuery.value.trim(), page: 1, pageSize: 20 }
    const groups = await Promise.all([riskFollowup.list({ ...params, special: '1' }), riskFollowup.list({ ...params, firstSeen: '1' })])
    matches.value = Array.from(new Map(groups.flatMap(group => group.items.map(item => [item.id, item] as const))).values())
    if (!matches.value.length) caseMessage.value = '未找到匹配的专项案例。'
  } catch (cause) { caseMessage.value = cause instanceof Error ? cause.message : '专项案例读取失败' }
  finally { searching.value = false }
}
function attachCase(value: unknown) {
  const item = matches.value.find(candidate => candidate.id === value)
  if (item && active.value && !active.value.node.cases.some(link => link.id === item.id)) active.value.node.cases.push({ id: item.id, title: item.title })
}
function detachCase(id: string) {
  if (active.value) active.value.node.cases = active.value.node.cases.filter(item => item.id !== id)
}
async function publish() {
  if (busy.value) return
  const { name, policyVersion, start, end, scope, handbook } = draft.value
  error.value = ''
  if (![name, policyVersion, start, end, scope, handbook.source].every(value => value.trim())) {
    error.value = '请填写名称、版本、生效日期、适用范围和来源。'
    return
  }
  const payload = JSON.stringify(draft.value)
  if (payload !== lastPayload) {
    lastPayload = payload
    publishKey = reviewKey()
  }
  busy.value = true
  try {
    const policy = await riskFollowup.createPolicy({ ...draft.value, basis: '分章管理的风控业务手册', requestId: publishKey, ruleDocument: true })
    try { sessionStorage.removeItem(key) } catch { /* Publication succeeded even if local storage is unavailable. */ }
    message.success('新版本已发布，旧版本仍可查看')
    emit('published', policy)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '发布失败，草稿已保留' }
  finally { busy.value = false }
}
</script>

<style scoped>
.metadata,.editor-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.metadata label,.section-editor label{display:grid;gap:6px}.editor-actions{margin:12px 0}.editor-grid{grid-template-columns:minmax(150px,230px) minmax(0,1fr);align-items:start}.editor-grid nav,.section-editor,.markdown{border:1px solid #e4e9ef;border-radius:6px;padding:10px}.outline-item{display:block;width:100%;border:0;background:transparent;text-align:left;padding:6px;font:inherit;cursor:pointer;overflow-wrap:anywhere}.outline-item[aria-current]{background:#eaf3ff;color:#185ab8}.content-block,.case-editor,.markdown{display:grid;gap:6px;margin:10px 0}.content-block{padding-bottom:8px;border-bottom:1px solid #e4e9ef}.case-editor h3,.markdown p{margin:0}.case-editor .ant-select{max-width:100%}@media(max-width:650px){.metadata,.editor-grid{grid-template-columns:1fr}}
</style>
