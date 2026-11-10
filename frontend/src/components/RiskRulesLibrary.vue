<template>
  <a-alert v-if="error" type="error" show-icon :message="error" />
  <a-alert v-if="linkError" type="warning" show-icon :message="linkError" />
  <a-spin :spinning="loading">
    <div class="handbook-bar">
      <a-select v-model:value="versionId" aria-label="手册版本" :options="versions" @change="switchVersion" />
      <a-space wrap>
        <a-button :loading="exporting" :disabled="!chapter" @click="download(chapter?.node.id)">导出本章 Word</a-button>
        <a-button :loading="exporting" :disabled="!current" @click="download()">导出整本 Word</a-button>
        <a-button v-if="canManageTypes" type="primary" @click="openEditor">编辑目录与正文</a-button>
      </a-space>
    </div>
    <section class="handbook-layout">
      <nav class="handbook-directory" aria-label="手册目录">
        <h2>手册目录</h2>
        <a-input v-model:value="query" placeholder="搜索章节、正文或问答" allow-clear />
        <div v-for="row in visibleRows" :key="row.node.id" class="outline-row" :style="{paddingInlineStart: (row.depth - 1) * 14 + 'px'}">
          <button v-if="row.node.children.length && !query" class="toggle" type="button"
            :aria-expanded="!collapsed.has(row.node.id)" :aria-label="row.node.title" @click="toggle(row.node.id)">{{ collapsed.has(row.node.id) ? '▸' : '▾' }}</button>
          <button class="section-link" type="button" :aria-current="active?.node.id === row.node.id ? 'location' : undefined"
            @click="selectSection(row.node.id)"><span>{{ row.number }}</span> {{ row.node.title }}</button>
        </div>
        <a-empty v-if="!visibleRows.length" description="暂无匹配章节" />
      </nav>
      <article v-if="active && current" class="handbook-paper">
        <header>
          <p class="muted">{{ current.name }} / {{ current.policyVersion }}</p>
          <h1>{{ active.number }} {{ active.node.title }}</h1>
          <a-tag v-if="current.id === trainingHandbook.id" color="gold">培训整理稿 · 待确认</a-tag>
          <p class="muted">{{ current.scope }}<template v-if="current.start"> · {{ current.start }} 至 {{ current.end }}</template></p>
          <p class="muted">来源 · {{ handbook.source }}</p>
        </header>
        <template v-for="(block, index) in active.node.blocks" :key="index">
          <ol v-if="block.kind === 'list'"><li v-for="(line, i) in lines(block.text)" :key="i">{{ line }}</li></ol>
          <div v-else-if="block.kind === 'table'" class="table-wrap">
            <table><thead><tr><th v-for="(cell, i) in cells(lines(block.text)[0])" :key="i">{{ cell }}</th></tr></thead>
              <tbody><tr v-for="(line, i) in lines(block.text).slice(1)" :key="i"><td v-for="(cell, j) in cells(line)" :key="j">{{ cell }}</td></tr></tbody></table>
          </div>
          <p v-else class="body-text" :class="{callout: block.kind !== 'paragraph'}"><strong v-if="block.kind === 'question'">问答 </strong><strong v-if="block.kind === 'note'">提示 </strong>{{ block.text }}</p>
        </template>
        <div v-if="active.node.children.length" class="section-index">
          <h2>本章条款</h2>
          <button v-for="child in active.node.children" :key="child.id" class="text-link" type="button" @click="selectSection(child.id)">{{ child.title }}</button>
        </div>
        <div v-if="active.node.examples.length || active.node.cases.length" class="section-index">
          <h2>关联案例</h2>
          <a-space direction="vertical">
            <button v-for="(item, i) in active.node.examples" :key="i" type="button" class="text-link" @click="example = item">{{ item.title }} <small>培训示例</small></button>
            <RouterLink v-for="item in active.node.cases" :key="item.id"
              :to="{ path: '/risk-followup/library', query: { case: item.id, policy: current.id, section: active.node.id } }">{{ item.title }} ↗</RouterLink>
          </a-space>
        </div>
      </article>
      <a-empty v-else description="选择左侧章节查看正文" />
    </section>
  </a-spin>
  <a-drawer :open="!!example" :width="'min(640px, 100vw)'" :title="example?.title || '培训示例'" @close="example = undefined">
    <a-tag color="gold">脱敏培训示例</a-tag>
    <p class="body-text">{{ example?.detail }}</p>
  </a-drawer>
  <RiskHandbookEditor v-if="editor" :initial="current" @close="editor = false" @published="published" />
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Alert as AAlert, Button as AButton, Drawer as ADrawer, Empty as AEmpty, Input as AInput, Select as ASelect, Space as ASpace, Spin as ASpin, Tag as ATag } from 'ant-design-vue'
import { riskFollowup, type ReviewPolicy, type RiskHandbook } from '@/api/riskFollowup'
import { useRiskPermissions } from '@/composables/useRiskPermissions'
import { handbookOutline, legacyHandbook, trainingHandbook } from '@/features/risk/riskHandbook'
import RiskHandbookEditor from './RiskHandbookEditor.vue'

const { canManageTypes } = useRiskPermissions()
const route = useRoute(), router = useRouter()
const policies = ref<ReviewPolicy[]>([trainingHandbook])
const versionId = ref(trainingHandbook.id)
const selected = ref('difference')
const query = ref('')
const collapsed = ref(new Set<string>())
const loading = ref(false), exporting = ref(false), editor = ref(false), error = ref('')
const linkError = ref('')
const example = ref<{ title: string; detail: string }>()
const current = computed(() => policies.value.find(policy => policy.id === versionId.value) || trainingHandbook)
const handbook = computed<RiskHandbook>(() => current.value.handbook || legacyHandbook(current.value))
const outline = computed(() => handbookOutline(handbook.value.chapters))
const active = computed(() => outline.value.find(row => row.node.id === selected.value) || outline.value[0])
const chapter = computed(() => outline.value.find(row => row.number === active.value?.number.split('.')[0]))
const versions = computed(() => policies.value.map(policy => ({ value: policy.id, label: `${policy.name} · ${policy.policyVersion}` })))
const visibleRows = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (term) return outline.value.filter(({ node }) => [node.title, ...node.blocks.map(block => block.text), ...node.cases.map(item => item.title), ...node.examples.map(item => item.title)].some(value => value.toLowerCase().includes(term)))
  const prefixes = outline.value.filter(row => collapsed.value.has(row.node.id)).map(row => row.number + '.')
  return outline.value.filter(row => !prefixes.some(prefix => row.number.startsWith(prefix)))
})

function lines(value: string) { return value.split('\n').filter(line => line.trim()) }
function cells(value = '') { return value.split('|').map(cell => cell.trim()) }
function toggle(id: string) { if (collapsed.value.has(id)) collapsed.value.delete(id); else collapsed.value.add(id) }
function selectSection(id: string) {
  selected.value = id
  void router.replace({ query: { policy: versionId.value, section: id } })
}
function switchVersion() {
  collapsed.value.clear()
  query.value = ''
  selectSection(outline.value[0]?.node.id || '')
}
function syncQuery() {
  const id = route.query.policy
  linkError.value = ''
  if (typeof id === 'string' && policies.value.some(policy => policy.id === id)) versionId.value = id
  else {
    versionId.value = policies.value[0].id
    if (typeof id === 'string') linkError.value = '链接中的历史版本当前不可用。'
  }
  const sectionId = route.query.section
  if (typeof sectionId === 'string' && outline.value.some(row => row.node.id === sectionId)) selected.value = sectionId
  else {
    if (typeof sectionId === 'string' && !linkError.value) linkError.value = '链接中的条款当前不可用。'
    selected.value = current.value.id === trainingHandbook.id ? 'difference' : ''
  }
}
watch(() => [route.query.policy, route.query.section], syncQuery)
onMounted(async () => {
  loading.value = true
  try {
    const list = await riskFollowup.policies()
    policies.value = [...list.filter(policy => policy.ruleDocument !== false), trainingHandbook]
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '制度读取失败'
  } finally {
    syncQuery()
    loading.value = false
  }
})
function openEditor() { editor.value = true }
function published(policy: ReviewPolicy) {
  policies.value.unshift(policy)
  versionId.value = policy.id
  switchVersion()
  editor.value = false
}
async function download(chapterId?: string) {
  exporting.value = true
  error.value = ''
  try {
    const { name, policyVersion, start, end, scope } = current.value
    const blob = await riskFollowup.exportPolicy({ name, policyVersion, start, end, scope, chapterId, handbook: handbook.value })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${name}-${policyVersion}.docx`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 30000)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Word 导出失败'
  } finally { exporting.value = false }
}
</script>

<style scoped>
.handbook-bar{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px}.handbook-bar>.ant-select{min-width:min(320px,100%)}
.handbook-layout{display:grid;grid-template-columns:minmax(220px,290px) minmax(0,1fr);gap:20px;align-items:start}
.handbook-directory,.handbook-paper{padding:20px;background:white;border:1px solid #e4e9ef;border-radius:8px;min-width:0}.handbook-paper{max-width:1000px;padding:30px 36px;min-height:460px;overflow-wrap:anywhere}
.handbook-paper header{border-bottom:1px solid #e4e9ef;margin-bottom:18px;padding-bottom:12px}.handbook-paper h1{font-size:25px;margin:5px 0 10px}.handbook-directory h2,.section-index h2{font-size:16px;margin:0 0 12px}
.outline-row{display:flex;align-items:flex-start;margin-top:3px}.outline-row:first-of-type{margin-top:12px}.toggle,.section-link,.text-link{border:0;background:transparent;cursor:pointer;font:inherit;color:inherit}.toggle{padding:7px 4px}.section-link{flex:1;text-align:left;padding:7px 6px;overflow-wrap:anywhere}.section-link span{color:#596b82;margin-right:4px}.section-link[aria-current]{background:#eaf3ff;color:#185ab8;border-radius:4px;font-weight:600}
.body-text,.handbook-paper li{white-space:pre-wrap;line-height:1.8;margin:12px 0}.callout{background:#f3f7ff;border-left:3px solid #216ad2;padding:8px 12px}.muted,small{color:#596b82;font-size:12px}.muted{margin:5px 0}
.table-wrap{overflow-x:auto;margin:14px 0}.table-wrap table{border-collapse:collapse;width:100%}.table-wrap td,.table-wrap th{padding:8px;text-align:left;border:1px solid #e4e9ef}.table-wrap th{background:#f2f5f9}
.section-index{border-top:1px solid #e4e9ef;padding-top:14px;margin-top:18px}.text-link{padding:0 10px 0 0;color:#185ab8;text-align:left}
@media(max-width:880px){.handbook-layout{grid-template-columns:1fr}.handbook-paper{padding:20px}}
</style>
