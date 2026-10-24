<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { workbenchApi as api } from './api'
import type { Catalog, Field, Job, Preview, Recipe, Step } from './types'
import StepEditor from './StepEditor.vue'

const auth = useAuthStore()
const catalog = ref<Catalog>({ datasets: [], recipes: [], jobs: [], operators: [], limits: {} })
const sourceId = ref(''),
  name = ref('未命名加工流程'),
  steps = ref<Step[]>([]),
  recipe = ref<Recipe>(),
  selectedStep = ref(-1)
const preview = ref<Preview>(),
  currentJob = ref<Job>(),
  resultJobId = ref(''),
  resultSignature = ref(''),
  resultStep = ref(-1)
const error = ref(''),
  notice = ref(''),
  loading = ref(false),
  busy = ref(false),
  uploading = ref(false),
  saving = ref(false),
  downloading = ref(false)
const editorOpen = ref(false),
  editing = ref<Step>(),
  uploadOpen = ref(false),
  uploadName = ref(''),
  sheetName = ref(''),
  file = ref<File>(),
  fileInput = ref<HTMLInputElement>()
const leftOpen = ref(true),
  rightOpen = ref(true),
  leftWidth = ref(230),
  rightWidth = ref(290),
  root = ref<HTMLElement>(),
  viewport = ref(1200)
const page = ref(1),
  savedSignature = ref(''),
  initialized = ref(false),
  disposed = ref(false),
  publishing = ref(false),
  historical = ref(false),
  insertIndex = ref(0)
let requestVersion = 0,
  contextVersion = 0,
  catalogVersion = 0,
  pendingSignature = '',
  poll: ReturnType<typeof setTimeout> | undefined,
  resizeObserver: ResizeObserver | undefined
let drag: { side: 'left' | 'right'; start: number; width: number; target: HTMLElement; pointer: number } | undefined
const labels: Record<string, string> = {
  trim: '去除首尾空格',
  replace: '精确替换',
  cast: '类型转换',
  filter: '筛选行',
  derive: '新增字段',
  group: '分组汇总',
  join: '关联数据集',
  append: '追加数据集',
  select: '保留字段',
}
const statuses: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  cancel_requested: '取消中',
  cancelled: '已取消',
  succeeded: '已完成',
  failed: '失败',
}
const source = computed(() => catalog.value.datasets.find((d) => d.id === sourceId.value))
const signature = computed(() => JSON.stringify({ name: name.value, sourceId: sourceId.value, steps: steps.value }))
const computeSignature = computed(() => JSON.stringify({ sourceId: sourceId.value, steps: steps.value }))
const dirty = computed(() => initialized.value && signature.value !== savedSignature.value)
const active = computed(
  () => !!currentJob.value && ['queued', 'running', 'cancel_requested'].includes(currentJob.value.status),
)
const resultReady = computed(
  () =>
    !!resultJobId.value &&
    currentJob.value?.id === resultJobId.value &&
    currentJob.value.status === 'succeeded' &&
    !busy.value &&
    !loading.value,
)
const stale = computed(
  () => !historical.value && !!resultJobId.value && resultSignature.value !== computeSignature.value,
)
const availableFields = computed(() =>
  fieldsThrough(editing.value ? steps.value.findIndex((s) => s.id === editing.value?.id) - 1 : insertIndex.value - 1),
)
const displayFields = computed(() => preview.value?.fields || [])
const reportText = computed(() => JSON.stringify(currentJob.value?.report || preview.value?.report || {}, null, 2))
const reportSteps = computed(
  () =>
    ((currentJob.value?.report || preview.value?.report)?.steps || []) as {
      id: string
      op: string
      inputRows?: number
      outputRows?: number
      invalidValues?: number
      precisionChanges?: number
      divisionByZero?: number
      join?: { estimatedRows?: number; manyToMany?: boolean; unmatchedLeft?: number; unmatchedRight?: number }
    }[],
)
const columnsStyle = computed(() =>
  viewport.value < 1050
    ? undefined
    : {
        gridTemplateColumns: `${leftOpen.value ? leftWidth.value : 0}px ${leftOpen.value ? 10 : 0}px minmax(280px,1fr) ${rightOpen.value ? 10 : 0}px ${rightOpen.value ? rightWidth.value : 0}px`,
      },
)
const layoutKey = computed(() => `data-workbench:layout:${auth.user?.id ?? 'anonymous'}`)
function fieldsThrough(index: number): Field[] {
  let fields = [...(source.value?.fields || [])]
  for (const step of steps.value.slice(0, index + 1)) {
    if (step.op === 'select')
      fields = fields.filter((f) => (step.columns as string[]).includes(f.id) || f.id === '_source_row')
    if (step.op === 'trim')
      fields = fields.map((f) => ((step.columns as string[]).includes(f.id) ? { ...f, type: 'text' } : f))
    if (step.op === 'replace') fields = fields.map((f) => (f.id === step.column ? { ...f, type: 'text' } : f))
    if (step.op === 'cast') fields = fields.map((f) => (f.id === step.column ? { ...f, type: String(step.type) } : f))
    if (step.op === 'derive')
      fields.push({
        id: `d_${step.id}`,
        name: String(step.name),
        type: ['concat', 'condition'].includes(String(step.kind)) ? 'text' : 'decimal',
      })
    if (step.op === 'group')
      fields = [
        ...fields.filter((f) => (step.keys as string[]).includes(f.id)),
        ...(step.aggregations as { name: string; fn: string; column: string }[]).map((a, i) => ({
          id: `g_${step.id}_${i}`,
          name: a.name,
          type: a.fn === 'count' ? 'integer' : fields.find((f) => f.id === a.column)?.type || 'text',
        })),
      ]
    if (step.op === 'join' && step.how !== 'anti')
      fields.push(
        ...(catalog.value.datasets.find((d) => d.id === step.rightSourceId)?.fields || []).map((f) => ({
          ...f,
          id: `r_${step.id}_${f.id}`,
          name: `右表·${f.name}`,
        })),
      )
  }
  return fields
}
function fail(e: unknown) {
  error.value = e instanceof Error ? e.message : '操作失败，请重试'
}
function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v))
}
function canDiscard() {
  return !dirty.value || window.confirm('当前流程有未保存修改，继续将丢弃这些修改。是否继续？')
}
function invalidateContext() {
  contextVersion++
  requestVersion++
  clearTimeout(poll)
  currentJob.value = undefined
  resultJobId.value = ''
  resultSignature.value = ''
  preview.value = undefined
  historical.value = false
  loading.value = false
  error.value = ''
  notice.value = ''
  page.value = 1
}
async function refreshCatalog() {
  const version = ++catalogVersion
  try {
    const data = await api.catalog()
    if (!disposed.value && version === catalogVersion) catalog.value = data
  } catch (e) {
    if (version === catalogVersion && !disposed.value) fail(e)
  }
}
async function chooseSource(id: string, keep = false) {
  if (!keep && !canDiscard()) return
  if (keep && steps.value.length) {
    const incoming = catalog.value.datasets.find((d) => d.id === id)
    const shape = (fields: Field[]) =>
      JSON.stringify(fields.map((f) => [f.id, f.sourceName ?? f.name, f.type, f.position]))
    if (!incoming || !source.value || shape(incoming.fields) !== shape(source.value.fields)) {
      error.value =
        '新来源的字段名称、顺序或类型不兼容，不能仅凭 c0001 等位置 ID 套用旧规则。请新建流程或先整理为相同结构。'
      return
    }
    if (!window.confirm('新来源结构兼容。是否保留步骤更换来源？历史任务不会改变，当前结果需重新运行。')) return
  }
  invalidateContext()
  sourceId.value = id
  selectedStep.value = -1
  if (!keep) {
    steps.value = []
    recipe.value = undefined
    name.value = '未命名加工流程'
    savedSignature.value = signature.value
  } else notice.value = '已更换来源，字段引用将按稳定 ID 校验；请预览确认后再运行。'
  await loadPage(1)
}
async function openRecipe(value: Recipe) {
  if (!canDiscard()) return
  invalidateContext()
  sourceId.value = value.sourceId
  steps.value = clone(value.steps)
  name.value = value.name
  recipe.value = value
  selectedStep.value = -1
  savedSignature.value = signature.value
  await loadPage(1)
}
async function loadPage(next: number) {
  if (!sourceId.value && !resultJobId.value) return
  const version = ++requestVersion,
    targetJob = resultJobId.value
  loading.value = true
  error.value = ''
  try {
    const data = targetJob
      ? await api.result(targetJob, (next - 1) * 100)
      : await api.sourcePreview(sourceId.value, (next - 1) * 100)
    if (version === requestVersion && !disposed.value) {
      preview.value = data
      page.value = next
    }
  } catch (e) {
    if (version === requestVersion) fail(e)
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
function selectSourcePreview() {
  contextVersion++
  selectedStep.value = -1
  historical.value = false
  resultJobId.value = ''
  resultSignature.value = ''
  currentJob.value = undefined
  clearTimeout(poll)
  void loadPage(1)
}
async function submit(kind: 'preview' | 'run', index = steps.value.length - 1) {
  if (!sourceId.value || busy.value || active.value) return
  busy.value = true
  error.value = ''
  const context = contextVersion
  const frozen = computeSignature.value
  try {
    const job = await api.run({
      sourceId: sourceId.value,
      steps: clone(steps.value.slice(0, index + 1)),
      kind,
      ...(recipe.value && !dirty.value ? { recipeId: recipe.value.id, recipeRevision: recipe.value.revision } : {}),
    })
    if (context !== contextVersion || disposed.value) return
    requestVersion++
    historical.value = false
    currentJob.value = job
    selectedStep.value = index
    pendingSignature = frozen
    notice.value = '任务已提交后台。关闭页面不会停止任务；当前表格保留至新结果完成，旧结果暂不可导出或发布。'
    void pollJob(job.id, context)
  } catch (e) {
    if (context === contextVersion) fail(e)
  } finally {
    busy.value = false
  }
}
async function pollJob(id: string, context: number) {
  clearTimeout(poll)
  try {
    const job = await api.job(id)
    if (disposed.value || context !== contextVersion || currentJob.value?.id !== id) return
    currentJob.value = job
    if (['queued', 'running', 'cancel_requested'].includes(job.status)) {
      poll = setTimeout(() => void pollJob(id, context), 1500)
      return
    }
    if (job.status === 'succeeded') {
      resultJobId.value = id
      resultStep.value = job.steps.length - 1
      if (!historical.value) resultSignature.value = pendingSignature
      notice.value = `${job.kind === 'preview' ? '步骤预览' : '全量运行'}完成。`
      await loadPage(1)
      void refreshCatalog()
    }
    if (job.status === 'failed') error.value = job.error || '任务失败，请查看检查报告并调整步骤。'
    if (job.status === 'cancelled') notice.value = '任务已取消，未发布本次结果。'
  } catch (e) {
    if (context === contextVersion && !disposed.value) {
      fail(e)
      notice.value = '状态刷新暂停，任务可能仍在后台运行，请点击“刷新任务状态”。'
    }
  }
}
async function cancel() {
  if (!currentJob.value) return
  const id = currentJob.value.id,
    context = contextVersion
  try {
    const job = await api.cancel(id)
    if (disposed.value || context !== contextVersion || currentJob.value?.id !== id) return
    currentJob.value = job
    void pollJob(id, context)
  } catch (e) {
    if (context === contextVersion) fail(e)
  }
}
async function save() {
  if (!sourceId.value || saving.value) return
  if (!name.value.trim()) {
    error.value = '请输入流程名称'
    return
  }
  saving.value = true
  error.value = ''
  const frozen = signature.value,
    context = contextVersion
  try {
    const value = await api.save(
      { name: name.value, sourceId: sourceId.value, steps: clone(steps.value) },
      recipe.value,
    )
    if (context === contextVersion && !disposed.value) {
      recipe.value = value
      savedSignature.value = frozen
      notice.value = `已保存版本 ${value.revision}。`
    }
    await refreshCatalog()
  } catch (e) {
    if (context === contextVersion) fail(e)
  } finally {
    saving.value = false
  }
}
async function copyRecipe() {
  if (!recipe.value) return
  if (dirty.value) {
    error.value = '请先保存当前修改再复制，或重新打开已保存版本。'
    return
  }
  const context = contextVersion
  try {
    const value = await api.copy(recipe.value.id)
    await refreshCatalog()
    if (!disposed.value && context === contextVersion) await openRecipe(value)
  } catch (e) {
    fail(e)
  }
}
async function upload() {
  if (!file.value) return
  uploading.value = true
  error.value = ''
  try {
    const dataset = await api.upload(file.value, uploadName.value, sheetName.value)
    await refreshCatalog()
    uploadOpen.value = false
    file.value = undefined
    await chooseSource(dataset.id)
    notice.value = '已导入为独立新数据集，不会静默覆盖或追加。'
  } catch (e) {
    fail(e)
  } finally {
    uploading.value = false
  }
}
function beginUpload() {
  file.value = undefined
  uploadName.value = ''
  sheetName.value = ''
  if (fileInput.value) fileInput.value.value = ''
  uploadOpen.value = true
}
function editStep(step: Step) {
  editing.value = clone(step)
  editorOpen.value = true
}
function beginAdd() {
  editing.value = undefined
  insertIndex.value = selectedStep.value >= 0 ? selectedStep.value + 1 : steps.value.length
  editorOpen.value = true
}
function applyStep(step: Step) {
  const index = steps.value.findIndex((s) => s.id === step.id)
  if (index >= 0) steps.value.splice(index, 1, step)
  else steps.value.splice(insertIndex.value, 0, step)
  editorOpen.value = false
  editing.value = undefined
  notice.value = '草稿已更新。请执行步骤预览检查下游字段和计算结果。'
}
async function showJob(job: Job) {
  contextVersion++
  requestVersion++
  clearTimeout(poll)
  historical.value = true
  currentJob.value = job
  resultStep.value = job.steps.length - 1
  resultJobId.value = ''
  preview.value = undefined
  loading.value = false
  error.value = ''
  if (job.status === 'succeeded') {
    resultJobId.value = job.id
    await loadPage(1)
  } else if (['queued', 'running', 'cancel_requested'].includes(job.status)) void pollJob(job.id, contextVersion)
  else if (job.error) error.value = job.error
}
async function publish() {
  if (
    !resultJobId.value ||
    stale.value ||
    active.value ||
    busy.value ||
    publishing.value ||
    currentJob.value?.id !== resultJobId.value
  )
    return
  publishing.value = true
  try {
    const dataset = await api.publish(resultJobId.value)
    await refreshCatalog()
    notice.value = `已保存为数据集“${dataset.name}”，可从左侧选择继续加工。`
  } catch (e) {
    fail(e)
  } finally {
    publishing.value = false
  }
}
function removeStep(index: number) {
  if (!window.confirm('删除此步骤可能使下游字段引用失效。确认删除？')) return
  steps.value.splice(index, 1)
  selectedStep.value = Math.min(selectedStep.value, steps.value.length - 1)
  notice.value = '步骤已删除；下游引用将在执行前校验，不会自动改成同名字段。'
}
async function download() {
  if (!resultJobId.value || stale.value || active.value || busy.value || currentJob.value?.id !== resultJobId.value)
    return
  downloading.value = true
  try {
    await api.download(resultJobId.value)
  } catch (e) {
    fail(e)
  } finally {
    downloading.value = false
  }
}
function numeric(field: Field) {
  return /decimal|numeric|int|float|double|real/i.test(field.type)
}
function clamp() {
  const max = Math.max(180, Math.min(420, (viewport.value - 300) / 2))
  leftWidth.value = Math.min(max, Math.max(180, leftWidth.value))
  rightWidth.value = Math.min(max, Math.max(220, rightWidth.value))
}
function persistLayout() {
  try {
    localStorage.setItem(
      layoutKey.value,
      JSON.stringify({
        left: leftWidth.value,
        right: rightWidth.value,
        leftOpen: leftOpen.value,
        rightOpen: rightOpen.value,
      }),
    )
  } catch {
    /* Layout preferences are optional; never store source data. */
  }
}
function resetLayout() {
  leftWidth.value = 230
  rightWidth.value = 290
  leftOpen.value = true
  rightOpen.value = true
  clamp()
  persistLayout()
}
function startDrag(event: PointerEvent, side: 'left' | 'right') {
  if (viewport.value < 1050) return
  endDrag()
  const target = event.currentTarget as HTMLElement
  drag = {
    side,
    start: event.clientX,
    width: side === 'left' ? leftWidth.value : rightWidth.value,
    target,
    pointer: event.pointerId,
  }
  target.setPointerCapture(event.pointerId)
  document.body.classList.add('workbench-resizing')
  event.preventDefault()
}
function moveDrag(event: PointerEvent) {
  if (!drag) return
  const delta = (event.clientX - drag.start) * (drag.side === 'left' ? 1 : -1)
  if (drag.side === 'left') leftWidth.value = drag.width + delta
  else rightWidth.value = drag.width + delta
  clamp()
}
function endDrag() {
  if (drag) {
    if (drag.target.hasPointerCapture(drag.pointer)) drag.target.releasePointerCapture(drag.pointer)
    drag = undefined
    persistLayout()
  }
  document.body.classList.remove('workbench-resizing')
}
function keyResize(event: KeyboardEvent, side: 'left' | 'right') {
  if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return
  event.preventDefault()
  if (event.key === 'Home') {
    resetLayout()
    return
  }
  const change = (event.key === 'ArrowRight' ? 20 : -20) * (side === 'left' ? 1 : -1)
  if (side === 'left') leftWidth.value += change
  else rightWidth.value += change
  clamp()
  persistLayout()
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
watch([leftOpen, rightOpen], persistLayout)
onBeforeRouteLeave(() => canDiscard())
onMounted(async () => {
  try {
    const data = JSON.parse(localStorage.getItem(layoutKey.value) || '{}')
    if (Number.isFinite(data.left)) leftWidth.value = data.left
    if (Number.isFinite(data.right)) rightWidth.value = data.right
    if (typeof data.leftOpen === 'boolean') leftOpen.value = data.leftOpen
    if (typeof data.rightOpen === 'boolean') rightOpen.value = data.rightOpen
  } catch {
    /* Ignore obsolete or invalid layout preferences. */
  }
  resizeObserver = new ResizeObserver((entries) => {
    viewport.value = entries[0]?.contentRect.width || 1200
    clamp()
  })
  if (root.value) resizeObserver.observe(root.value)
  window.addEventListener('pointermove', moveDrag)
  window.addEventListener('pointerup', endDrag)
  window.addEventListener('pointercancel', endDrag)
  window.addEventListener('blur', endDrag)
  window.addEventListener('beforeunload', beforeUnload)
  await refreshCatalog()
  savedSignature.value = signature.value
  initialized.value = true
})
onBeforeUnmount(() => {
  disposed.value = true
  requestVersion++
  contextVersion++
  clearTimeout(poll)
  resizeObserver?.disconnect()
  endDrag()
  window.removeEventListener('pointermove', moveDrag)
  window.removeEventListener('pointerup', endDrag)
  window.removeEventListener('pointercancel', endDrag)
  window.removeEventListener('blur', endDrag)
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>

<template>
  <section ref="root" class="workbench" :class="{ compact: viewport < 1050 }">
    <header class="workbench-header">
      <div>
        <h1>数据加工工作台</h1>
        <p>导入真实数据，用可重复的步骤清洗、汇总和关联。不改写原始业务表。</p>
      </div>
      <a-button type="primary" @click="beginUpload">导入 CSV / XLSX</a-button>
    </header>
    <a-alert v-if="error" :message="error" type="error" show-icon closable @close="error = ''" />
    <a-alert v-if="notice" :message="notice" type="info" show-icon closable @close="notice = ''" />
    <a-alert
      v-if="reportSteps.some((item) => item.invalidValues || item.precisionChanges)"
      message="存在转换失败或小数精度变化，请核对处理检查报告和原始数据，勿直接作为正式核算结果。"
      type="warning"
      show-icon
    />
    <div class="workflow-toolbar">
      <label class="recipe-name">流程名称<a-input v-model:value="name" :maxlength="120" aria-label="流程名称" /></label>
      <span class="draft-label">{{ dirty ? '未保存草稿' : recipe ? `已保存 · v${recipe.revision}` : '新流程' }}</span>
      <a-button :disabled="!sourceId || saving" :loading="saving" @click="save">保存流程</a-button
      ><a-button :disabled="!recipe || dirty" @click="copyRecipe">复制流程</a-button>
      <a-button :disabled="!sourceId || active || busy" :loading="busy" @click="submit('preview')"
        >预览全部步骤</a-button
      ><a-button type="primary" :disabled="!sourceId || active || busy" @click="submit('run')">全量运行</a-button>
    </div>
    <div class="layout-toolbar">
      <a-button size="small" @click="leftOpen = !leftOpen">{{ leftOpen ? '收起' : '展开' }}数据集</a-button
      ><a-button size="small" @click="rightOpen = !rightOpen">{{ rightOpen ? '收起' : '展开' }}步骤</a-button
      ><a-button size="small" @click="resetLayout">重置布局</a-button
      ><span>仅本人数据 · 预览每页 100 行 · 金额由服务端计算</span>
    </div>
    <div class="workbench-grid" :style="columnsStyle">
      <aside v-show="leftOpen" class="dataset-panel">
        <h2>数据集</h2>
        <p class="muted">每次导入创建独立版本</p>
        <div v-if="!catalog.datasets.length" class="panel-empty">还没有数据。请先导入 CSV 或 XLSX。</div>
        <button
          v-for="dataset in catalog.datasets"
          :key="dataset.id"
          class="dataset-item"
          :class="{ selected: dataset.id === sourceId }"
          @click="chooseSource(dataset.id)"
        >
          <strong :title="dataset.name">{{ dataset.name }}</strong
          ><small>{{ dataset.rowCount.toLocaleString() }} 行 · {{ dataset.fields.length }} 字段</small>
        </button>
        <label v-if="sourceId" class="replace-source"
          >替换当前流程的来源<a-select
            :value="sourceId"
            :options="catalog.datasets.map((d) => ({ value: d.id, label: d.name }))"
            @change="(value: unknown) => chooseSource(String(value), true)"
        /></label>
        <h2>已保存流程</h2>
        <div v-if="!catalog.recipes.length" class="panel-empty">保存后可换数据复跑。</div>
        <button v-for="item in catalog.recipes" :key="item.id" class="dataset-item" @click="openRecipe(item)">
          <strong>{{ item.name }}</strong
          ><small>版本 {{ item.revision }} · {{ item.steps.length }} 步</small>
        </button>
        <h2>最近任务</h2>
        <button v-for="job in catalog.jobs.slice(0, 10)" :key="job.id" class="dataset-item" @click="showJob(job)">
          <strong>{{ statuses[job.status] }} · {{ job.kind === 'run' ? '全量' : '预览' }}</strong
          ><small>{{ job.createdAt }}</small></button
        ><a-button size="small" @click="refreshCatalog">刷新列表</a-button>
      </aside>
      <div
        v-show="leftOpen"
        class="panel-separator left-separator"
        role="separator"
        tabindex="0"
        aria-label="调整数据集面板宽度"
        aria-orientation="vertical"
        :aria-valuenow="Math.round(leftWidth)"
        :aria-valuemin="180"
        :aria-valuemax="420"
        @pointerdown="startDrag($event, 'left')"
        @keydown="keyResize($event, 'left')"
      ></div>
      <main class="data-panel">
        <div class="data-heading">
          <div>
            <h2>
              {{
                historical
                  ? catalog.datasets.find((d) => d.id === currentJob?.sourceId)?.name || '历史任务结果'
                  : source?.name || '开始加工数据'
              }}
            </h2>
            <p class="muted">
              {{ resultJobId ? `结果快照 · ${resultStep + 1} 个步骤` : '原始数据预览'
              }}<span v-if="preview">
                · {{ preview.total.toLocaleString() }} 行 ·
                {{
                  preview.scope === 'full' ? '全量结果' : preview.scope === 'preview' ? '步骤预览结果' : '来源数据'
                }}</span
              >
            </p>
          </div>
          <a-button v-if="sourceId" size="small" :disabled="active" @click="selectSourcePreview">查看原始数据</a-button>
        </div>
        <div v-if="currentJob" class="job-status" role="status">
          <span
            >任务：{{ statuses[currentJob.status] }} · {{ currentJob.kind === 'run' ? '全量执行' : '步骤预览' }}</span
          ><a-button v-if="active" size="small" :disabled="currentJob.status === 'cancel_requested'" @click="cancel">{{
            currentJob.status === 'cancel_requested' ? '正在取消' : '取消任务'
          }}</a-button
          ><a-button size="small" @click="pollJob(currentJob.id, contextVersion)">刷新任务状态</a-button>
        </div>
        <p v-if="historical" class="stale-warning" role="status">
          正在查看历史任务冻结结果，与当前编辑草稿独立；来源 {{ currentJob?.sourceId }}。
        </p>
        <p v-else-if="stale" class="stale-warning" role="status">
          当前表格属于历史规则快照，不是当前草稿结果。请重新执行后再导出。
        </p>
        <div class="preview-shell" :aria-busy="loading">
          <div v-if="loading" class="loading-label" role="status">正在加载预览…</div>
          <div v-if="!preview" class="preview-empty">
            <strong>{{ sourceId ? '选择步骤并执行预览' : '从左侧选择数据集，或导入文件' }}</strong>
            <p>步骤由后台真实执行；没有数据时不会填充模拟结果。</p>
          </div>
          <div v-else class="table-scroll" tabindex="0" aria-label="数据预览，可横向和纵向滚动">
            <table>
              <thead>
                <tr>
                  <th class="row-number">行</th>
                  <th v-for="field in displayFields" :key="field.id" :class="{ numeric: numeric(field) }">
                    <span :title="field.name">{{ field.name }}</span
                    ><small>{{ field.type }} · {{ field.id }}</small>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in preview.rows" :key="`${preview.offset + index}`">
                  <td class="row-number">{{ preview.offset + index + 1 }}</td>
                  <td
                    v-for="field in displayFields"
                    :key="field.id"
                    :class="{ numeric: numeric(field), null: row[field.id] === null }"
                    :title="row[field.id] === null ? 'NULL（缺失值，不是零）' : String(row[field.id] ?? '')"
                  >
                    <span>{{
                      row[field.id] === null ? 'NULL' : row[field.id] === '' ? '（空字符串）' : row[field.id]
                    }}</span>
                  </td>
                </tr>
                <tr v-if="!preview.rows.length">
                  <td :colspan="displayFields.length + 1" class="zero-rows">该步骤结果为 0 行，请检查筛选条件。</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="preview-footer">
          <span>{{ preview ? `显示 ${preview.rows.length} 行；并非预览行合计` : '尚无预览' }}</span
          ><a-pagination
            v-if="preview"
            :current="page"
            :total="preview.total"
            :page-size="100"
            :show-size-changer="false"
            size="small"
            :disabled="loading || active || busy"
            @change="loadPage"
          /><a-button :disabled="!resultReady || stale" :loading="publishing" @click="publish">保存为数据集</a-button
          ><a-button :disabled="!resultReady || stale" :loading="downloading" @click="download">导出 CSV</a-button>
        </div>
        <details v-if="currentJob?.report || preview?.report" class="report">
          <summary>处理检查报告 · 每步行数与关联检查</summary>
          <div class="report-scroll">
            <table class="report-table">
              <thead>
                <tr>
                  <th>步骤</th>
                  <th>输入行数</th>
                  <th>输出行数</th>
                  <th>质量检查</th>
                  <th>关联检查</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, index) in reportSteps" :key="item.id">
                  <td>{{ index + 1 }}. {{ labels[item.op] || item.op }}</td>
                  <td>{{ item.inputRows ?? '—' }}</td>
                  <td>{{ item.outputRows ?? '未完成' }}</td>
                  <td>
                    {{ item.invalidValues ? `转换失败 ${item.invalidValues}；` : ''
                    }}{{ item.precisionChanges ? `精度变化 ${item.precisionChanges}（数值转为6位小数，请核对）；` : ''
                    }}{{ item.divisionByZero ? `除零 ${item.divisionByZero}；` : ''
                    }}{{ !item.invalidValues && !item.precisionChanges && !item.divisionByZero ? '无上述异常' : '' }}
                  </td>
                  <td>
                    {{
                      item.join
                        ? `预计 ${item.join.estimatedRows} 行；${item.join.manyToMany ? '多对多' : '非多对多'}；左未匹配 ${item.join.unmatchedLeft} / 右未匹配 ${item.join.unmatchedRight}`
                        : '—'
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <details>
            <summary>完整统计与金额合计（服务端返回）</summary>
            <pre>{{ reportText }}</pre>
          </details>
        </details>
      </main>
      <div
        v-show="rightOpen"
        class="panel-separator right-separator"
        role="separator"
        tabindex="0"
        aria-label="调整步骤面板宽度"
        aria-orientation="vertical"
        :aria-valuenow="Math.round(rightWidth)"
        :aria-valuemin="220"
        :aria-valuemax="420"
        @pointerdown="startDrag($event, 'right')"
        @keydown="keyResize($event, 'right')"
      ></div>
      <aside v-show="rightOpen" class="steps-panel">
        <div class="steps-title">
          <h2>已应用步骤</h2>
          <a-button size="small" :disabled="!sourceId" @click="beginAdd">添加</a-button>
        </div>
        <p class="muted">点击“预览至此”检查中间结果；添加将插入所选步骤之后。修改不会自动执行昂贵计算。</p>
        <button
          class="source-step"
          :class="{ selected: selectedStep === -1 }"
          :disabled="active"
          @click="selectSourcePreview"
        >
          来源 · {{ source?.name || '未选择' }}
        </button>
        <ol class="step-list">
          <li v-for="(step, index) in steps" :key="step.id" :class="{ selected: selectedStep === index }">
            <strong>{{ index + 1 }}. {{ labels[step.op] || step.op }}</strong
            ><small v-if="step.name">{{ step.name }}</small>
            <div>
              <a-button size="small" :disabled="active || busy" @click="submit('preview', index)">预览至此</a-button
              ><a-button size="small" @click="editStep(step)">编辑</a-button
              ><a-button size="small" danger @click="removeStep(index)">删除</a-button>
            </div>
          </li>
        </ol>
        <p v-if="!steps.length" class="panel-empty">添加清洗、派生、汇总或关联步骤，构建自己的流程。</p>
        <div class="rule-notes">
          导入字段初始为文本，金额运算前请先转换为精确数值。NULL 不等于 0；不自动去重。关联超限请补充关联键或先汇总。
        </div>
      </aside>
    </div>
    <a-modal
      v-model:open="uploadOpen"
      title="导入新数据集"
      :footer="null"
      :mask-closable="!uploading"
      :closable="!uploading"
      :keyboard="!uploading"
      :width="560"
      class="workbench-modal"
      ><form class="upload-form" @submit.prevent="upload">
        <p>CSV / XLSX，导入为独立版本。原数据不会被覆盖。</p>
        <label
          >文件<input
            ref="fileInput"
            type="file"
            accept=".csv,.xlsx"
            :disabled="uploading"
            @change="file = ($event.target as HTMLInputElement).files?.[0]" /></label
        ><label>数据集名称（可选）<a-input v-model:value="uploadName" :maxlength="120" /></label
        ><label>工作表名称（XLSX 可选，默认首张）<a-input v-model:value="sheetName" /></label>
        <p v-if="error" role="alert" class="stale-warning">{{ error }}</p>
        <div class="modal-actions">
          <a-button :disabled="uploading" @click="uploadOpen = false">取消</a-button
          ><a-button type="primary" html-type="submit" :loading="uploading" :disabled="!file">导入</a-button>
        </div>
      </form></a-modal
    >
    <a-modal
      v-model:open="editorOpen"
      :title="editing ? '编辑加工步骤' : '添加加工步骤'"
      :footer="null"
      :width="600"
      :destroy-on-close="true"
      class="workbench-modal"
      ><StepEditor
        :fields="availableFields"
        :datasets="catalog.datasets"
        :edit="editing"
        @apply="applyStep"
        @cancel="editorOpen = false"
    /></a-modal>
  </section>
</template>

<style scoped>
.workbench {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: #1e293b;
}
.workbench-header,
.workflow-toolbar,
.layout-toolbar,
.data-heading,
.preview-footer,
.steps-title,
.job-status {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.workbench-header,
.data-heading {
  justify-content: space-between;
}
.workbench h1 {
  font-size: 23px;
  margin: 0 0 6px;
}
.workbench h2 {
  font-size: 15px;
  margin: 0;
}
.workbench p {
  margin: 0;
  line-height: 1.65;
}
.workbench-header p,
.muted,
.layout-toolbar span,
.preview-footer > span {
  color: #64748b;
  font-size: 12px;
}
.recipe-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: 360px;
  flex: 1 1 280px;
  white-space: nowrap;
}
.recipe-name :deep(input) {
  min-width: 80px;
}
.draft-label {
  font-size: 12px;
  color: #64748b;
}
.layout-toolbar {
  padding-bottom: 4px;
}
.layout-toolbar span {
  margin-left: auto;
}
.workbench-grid {
  display: grid;
  min-width: 0;
  min-height: 560px;
  height: calc(100vh - 290px);
  max-height: 1000px;
  border: 1px solid #dce3eb;
  border-radius: 6px;
  overflow: hidden;
  background: white;
}
.dataset-panel,
.steps-panel {
  min-width: 0;
  overflow: auto;
  padding: 16px 12px;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}
.dataset-panel h2:not(:first-child) {
  margin-top: 24px;
}
.dataset-item {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 4px;
  padding: 10px 8px;
  margin: 6px 0;
  cursor: pointer;
  min-width: 0;
}
.dataset-item strong,
.dataset-item small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dataset-item small {
  margin-top: 4px;
  color: #64748b;
}
.dataset-item:hover,
.source-step:hover {
  background: #f1f5f9;
}
.dataset-item.selected,
.source-step.selected,
.step-list li.selected {
  background: #edf5ff;
  border-color: #91caff;
}
.panel-empty {
  font-size: 12px;
  color: #64748b;
  line-height: 1.7;
  padding: 14px 2px;
}
.replace-source {
  display: grid;
  gap: 8px;
  font-size: 12px;
  margin-top: 16px;
}
.replace-source :deep(.ant-select) {
  min-width: 0;
  width: 100%;
}
.panel-separator {
  background: #f4f6f9;
  cursor: col-resize;
  touch-action: none;
  position: relative;
}
.panel-separator:after {
  content: '';
  position: absolute;
  width: 2px;
  height: 36px;
  background: #bcc9d7;
  left: 4px;
  top: 45%;
  border-radius: 2px;
}
.panel-separator:hover,
.panel-separator:focus-visible {
  background: #cce5ff;
  outline: 2px solid #1677ff;
  outline-offset: -2px;
}
.data-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.data-heading {
  padding: 14px 16px;
  border-bottom: 1px solid #e5eaf0;
  flex-shrink: 0;
}
.data-heading h2 {
  overflow-wrap: anywhere;
}
.job-status {
  padding: 8px 12px;
  background: #f0f7ff;
  font-size: 12px;
  flex-shrink: 0;
}
.stale-warning {
  padding: 8px 12px;
  background: #fff7e6;
  color: #8b4a00;
  font-size: 12px;
  flex-shrink: 0;
  overflow-wrap: anywhere;
}
.preview-shell {
  flex: 1;
  position: relative;
  min-height: 180px;
  min-width: 0;
  overflow: hidden;
}
.loading-label {
  position: absolute;
  top: 8px;
  left: 12px;
  background: #e6f4ff;
  color: #0958d9;
  border: 1px solid #91caff;
  padding: 6px 12px;
  z-index: 4;
  border-radius: 4px;
  pointer-events: none;
}
.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 24px;
  gap: 10px;
  text-align: center;
  color: #64748b;
}
.table-scroll {
  height: 100%;
  overflow: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
  scrollbar-width: auto;
}
.table-scroll table {
  border-collapse: separate;
  border-spacing: 0;
  width: max-content;
  min-width: 100%;
  font-size: 12px;
}
.table-scroll th,
.table-scroll td {
  min-width: 170px;
  max-width: 280px;
  width: 180px;
  padding: 9px 12px;
  border-right: 1px solid #edf0f5;
  border-bottom: 1px solid #edf0f5;
  text-align: left;
  vertical-align: top;
}
.table-scroll th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #f5f7fa;
  line-height: 1.45;
  white-space: normal;
  overflow-wrap: anywhere;
}
.table-scroll th small {
  display: block;
  font-weight: 400;
  color: #64748b;
  font-size: 10px;
  margin-top: 4px;
}
.table-scroll td span {
  display: block;
  max-width: 256px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  user-select: text;
}
.table-scroll .numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.table-scroll .row-number {
  min-width: 52px;
  max-width: 52px;
  width: 52px;
  color: #64748b;
  text-align: right;
  background: #fafbfc;
}
.table-scroll .null {
  color: #8994a5;
  font-style: italic;
}
.zero-rows {
  padding: 30px !important;
  text-align: center !important;
}
.preview-footer {
  padding: 10px 12px;
  border-top: 1px solid #dce3eb;
  justify-content: space-between;
  flex-shrink: 0;
}
.report {
  padding: 10px 12px;
  border-top: 1px solid #e5eaf0;
  flex-shrink: 0;
  font-size: 12px;
  max-height: 200px;
  overflow: auto;
}
.report summary {
  cursor: pointer;
}
.report pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 10px 0;
  font-size: 11px;
}
.steps-title {
  justify-content: space-between;
  margin-bottom: 8px;
}
.source-step {
  display: block;
  width: 100%;
  padding: 10px;
  margin: 12px 0;
  border: 1px solid #dce3eb;
  border-radius: 4px;
  background: white;
  text-align: left;
  overflow-wrap: anywhere;
  cursor: pointer;
}
.step-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.step-list li {
  padding: 12px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  margin-bottom: 8px;
  overflow-wrap: anywhere;
}
.step-list strong,
.step-list small {
  display: block;
  font-size: 12px;
}
.step-list small {
  color: #64748b;
  margin-top: 4px;
}
.step-list li > div {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 10px;
}
.rule-notes {
  font-size: 12px;
  background: #f8fafc;
  padding: 12px;
  line-height: 1.7;
  color: #64748b;
  margin-top: 16px;
}
.upload-form {
  display: grid;
  gap: 16px;
}
.upload-form label {
  display: grid;
  gap: 6px;
}
.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  position: sticky;
  bottom: 0;
  background: white;
  padding-top: 10px;
}
:global(.workbench-modal .ant-modal-body) {
  max-height: calc(100dvh - 190px);
  overflow: auto;
  overscroll-behavior: contain;
}
:global(.workbench-resizing) {
  user-select: none !important;
  cursor: col-resize !important;
}
.report-scroll {
  overflow: auto;
  max-height: 130px;
  margin: 10px 0;
}
.report-table {
  border-collapse: collapse;
  width: 100%;
  min-width: 460px;
  font-size: 11px;
}
.report-table td,
.report-table th {
  padding: 6px 8px;
  border-bottom: 1px solid #e2e8f0;
  text-align: left;
  white-space: nowrap;
}
.report-table td:nth-child(2),
.report-table td:nth-child(3) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.compact .workbench-grid {
  grid-template-columns: minmax(0, 1fr) !important;
  height: auto;
  max-height: none;
  min-height: 500px;
  overflow: visible;
}
.compact .panel-separator {
  display: none !important;
}
.compact .dataset-panel {
  max-height: 260px;
  border-bottom: 1px solid #dce3eb;
}
.compact .steps-panel {
  max-height: 380px;
  border-top: 1px solid #dce3eb;
}
.compact .data-panel {
  height: 620px;
  max-height: 85dvh;
  min-height: 420px;
}
.compact .preview-footer > span {
  flex-basis: 100%;
}
@media (max-width: 1100px) {
  .layout-toolbar span {
    margin-left: 0;
  }
  .workbench-header {
    align-items: flex-start;
  }
}
@media (max-width: 1049px) {
  .workbench-grid {
    grid-template-columns: minmax(0, 1fr) !important;
    height: auto;
    max-height: none;
    min-height: 500px;
    overflow: visible;
  }
  .panel-separator {
    display: none !important;
  }
  .dataset-panel {
    max-height: 260px;
    border-bottom: 1px solid #dce3eb;
  }
  .steps-panel {
    max-height: 380px;
    border-top: 1px solid #dce3eb;
  }
  .data-panel {
    height: 620px;
    max-height: 85dvh;
    min-height: 420px;
  }
  .workbench h1 {
    font-size: 20px;
  }
  .recipe-name {
    max-width: none;
  }
  .preview-footer {
    gap: 8px;
  }
  .preview-footer > span {
    flex-basis: 100%;
  }
}
@media (prefers-reduced-motion: reduce) {
  .workbench * {
    scroll-behavior: auto !important;
    transition: none !important;
  }
}
</style>
