<template>
  <section class="evidence-panel">
    <div class="viewer-tools">
      <a-select
        v-if="files.length"
        :value="fileId"
        :options="files.map((file) => ({ value: file.id, label: file.name }))"
        aria-label="原件"
        class="file-select"
        @change="switchFile"
      />
      <a-button v-if="fileId" size="small" @click="download">下载原件</a-button>
    </div>
    <div v-if="isPdf" class="viewer-tools viewer-mode">
      <a-space>
        <a-button size="small" :type="mode === 'pdf' ? 'primary' : 'default'" @click="switchMode('pdf')">
          PDF 原版
        </a-button>
        <a-button size="small" :type="mode === 'text' ? 'primary' : 'default'" @click="switchMode('text')">
          提取正文
        </a-button>
      </a-space>
      <a-space v-if="mode === 'pdf'" wrap>
        <a-button size="small" :disabled="page <= 1" aria-label="上一页" @click="page--">上页</a-button>
        <span aria-live="polite">{{ page }} / {{ pageCount || '—' }}</span>
        <a-button size="small" :disabled="page >= pageCount" aria-label="下一页" @click="page++">下页</a-button>
        <a-button size="small" :disabled="zoom <= 0.5" aria-label="缩小" @click="zoom -= 0.1">−</a-button>
        <a-button size="small" :disabled="zoom >= 2" aria-label="放大" @click="zoom += 0.1">＋</a-button>
      </a-space>
    </div>
    <p v-if="error" class="viewer-message" role="alert">{{ error }}</p>
    <p v-else-if="loading" class="viewer-message" role="status">正在读取原件…</p>
    <div ref="viewport" class="viewer-scroll" @pointerup="select" @contextmenu="rightSelect">
      <div v-if="isPdf && mode === 'pdf'" ref="pageRoot" class="pdf-page">
        <canvas ref="canvas" />
        <div class="rectangle-layer" aria-hidden="true">
          <span
            v-for="rectangle in visibleRectangles"
            :key="rectangle.key"
            :class="{ active: rectangle.active }"
            :style="rectangleStyle(rectangle)"
          />
        </div>
        <div ref="textLayer" class="textLayer" />
      </div>
      <div v-else-if="visibleSegments.length" class="segments">
        <section v-for="segment in visibleSegments" :key="segment.id" class="segment" :data-segment="segment.id">
          <strong>{{ segment.locator }}</strong>
          <p class="segment-text" :data-segment-text="segment.id">
            <template v-for="part in segmentParts(segment)" :key="part.start">
              <mark v-if="part.highlight" :class="{ active: part.active }" :style="{ backgroundColor: part.color }">{{
                part.text
              }}</mark
              ><template v-else>{{ part.text }}</template>
            </template>
          </p>
        </section>
      </div>
      <a-empty v-else description="暂无可选正文。扫描件可在 OCR 后重新导入。" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { GlobalWorkerOptions, getDocument, TextLayer, type RenderTask } from 'pdfjs-dist/legacy/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'
import { annotationApi, type Evidence, type Region, type Segment, type SourceFile } from './api'

GlobalWorkerOptions.workerSrc = workerUrl

const props = defineProps<{
  sampleId: string
  files: SourceFile[]
  segments: Segment[]
  marks: (Evidence & { color?: string })[]
  active: Evidence | null
  editable: boolean
}>()

const emit = defineEmits<{ selected: [evidence: Evidence, x: number, y: number]; clearSelection: [] }>()
const fileId = ref('')
const mode = ref<'pdf' | 'text'>('text')
const page = ref(1)
const zoom = ref(1)
const pageCount = ref(0)
const loading = ref(false)
const error = ref('')
const canvas = ref<HTMLCanvasElement>()
const pageRoot = ref<HTMLDivElement>()
const textLayer = ref<HTMLDivElement>()
const viewport = ref<HTMLDivElement>()
const documentState = shallowRef<Awaited<ReturnType<typeof getDocument>['promise']>>()
let loadSequence = 0
let renderSequence = 0
let controller: AbortController | undefined
let loadingTask: ReturnType<typeof getDocument> | undefined
let canvasTask: RenderTask | undefined
let layerTask: TextLayer | undefined

const activeFile = computed(() => props.files.find((file) => file.id === fileId.value))
const isPdf = computed(() => activeFile.value?.name.toLowerCase().endsWith('.pdf') ?? false)
const visibleSegments = computed(() => props.segments.filter((item) => item.fileId === fileId.value))
const fileMarks = computed(() => props.marks.filter((mark) => mark.fileId === fileId.value))
const fileEvidence = computed(() => (props.active?.fileId === fileId.value ? props.active : null))

function samePosition(a: Evidence, b: Evidence | null) {
  return (
    b !== null &&
    a.fileId === b.fileId &&
    (a.page ?? a.segmentId) === (b.page ?? b.segmentId) &&
    a.start === b.start &&
    a.end === b.end &&
    a.quote === b.quote
  )
}

const visibleRectangles = computed(() => {
  const marks: (Evidence & { color?: string })[] = [...fileMarks.value]
  if (fileEvidence.value && !marks.some((mark) => samePosition(mark, fileEvidence.value)))
    marks.push(fileEvidence.value)
  return marks.flatMap((mark, i) =>
    mark.page === page.value
      ? (mark.rects ?? []).map((rect, j) => ({
          ...rect,
          color: mark.color,
          key: i + ':' + j,
          active: samePosition(mark, fileEvidence.value),
        }))
      : [],
  )
})

function rectangleStyle(rect: Region & { color?: string }): CSSProperties {
  return {
    left: rect.x * 100 + '%',
    top: rect.y * 100 + '%',
    width: rect.w * 100 + '%',
    height: rect.h * 100 + '%',
    backgroundColor: rect.color,
  }
}

function segmentParts(segment: Segment) {
  const marks: (Evidence & { color?: string })[] = [...fileMarks.value]
  if (fileEvidence.value) marks.push(fileEvidence.value)
  const spans = marks.filter(
    (mark) => mark.segmentId === segment.id && mark.start != null && mark.end != null && !mark.rects?.length,
  )
  const boundaries = [...new Set([0, segment.text.length, ...spans.flatMap((mark) => [mark.start!, mark.end!])])]
    .filter((offset) => offset >= 0 && offset <= segment.text.length)
    .sort((a, b) => a - b)
  return boundaries.slice(0, -1).map((start, i) => {
    const end = boundaries[i + 1]
    const covering = spans.filter((mark) => mark.start! <= start && mark.end! >= end)
    return {
      start,
      text: segment.text.slice(start, end),
      highlight: Boolean(covering.length),
      color: covering[0]?.color,
      active: covering.some((mark) => samePosition(mark, fileEvidence.value)),
    }
  })
}

function readRange() {
  const selected = window.getSelection()
  if (!selected || selected.isCollapsed || !selected.rangeCount || !viewport.value) return null
  const range = selected.getRangeAt(0)
  if (!viewport.value.contains(range.startContainer) || !viewport.value.contains(range.endContainer)) return null
  return range
}

function rangeText(root: Node, node: Node, offset: number) {
  const before = document.createRange()
  before.selectNodeContents(root)
  before.setEnd(node, offset)
  return before.toString().length
}

function capture(): Evidence | null {
  if (!props.editable) return null
  const range = readRange()
  const text = range?.toString() ?? ''
  const quote = text.trim()
  if (!range || !quote) return null
  const leading = text.length - text.trimStart().length
  if (
    mode.value === 'pdf' &&
    textLayer.value?.contains(range.startContainer) &&
    textLayer.value.contains(range.endContainer) &&
    pageRoot.value
  ) {
    const bounds = pageRoot.value.getBoundingClientRect()
    const rects = Array.from(range.getClientRects())
      .map((rect) => {
        const left = Math.max(rect.left, bounds.left)
        const top = Math.max(rect.top, bounds.top)
        return {
          x: (left - bounds.left) / bounds.width,
          y: (top - bounds.top) / bounds.height,
          w: (Math.min(rect.right, bounds.right) - left) / bounds.width,
          h: (Math.min(rect.bottom, bounds.bottom) - top) / bounds.height,
        }
      })
      .filter((rect) => rect.w > 0 && rect.h > 0)
    if (!rects.length) return null
    const start = rangeText(textLayer.value, range.startContainer, range.startOffset) + leading
    return { fileId: fileId.value, page: page.value, start, end: start + quote.length, quote, rects }
  }
  const node = range.startContainer
  const textNode = (node instanceof HTMLElement ? node : node.parentElement)?.closest<HTMLElement>(
    '[data-segment-text]',
  )
  if (!textNode?.contains(range.endContainer)) return null
  const segment = visibleSegments.value.find((item) => item.id === textNode.dataset.segmentText)
  if (!segment) return null
  const start = rangeText(textNode, node, range.startOffset) + leading
  return { fileId: fileId.value, segmentId: segment.id, page: segment.page, start, end: start + quote.length, quote }
}

function select(event: PointerEvent) {
  if (event.button !== 0) return
  const evidence = capture()
  if (evidence) emit('selected', evidence, event.clientX, event.clientY)
  else emit('clearSelection')
}

function rightSelect(event: MouseEvent) {
  const evidence = capture()
  if (!evidence) return
  event.preventDefault()
  emit('selected', evidence, event.clientX, event.clientY)
}

function stopRendering() {
  renderSequence++
  canvasTask?.cancel()
  layerTask?.cancel()
  canvasTask = undefined
  layerTask = undefined
}

async function showPage() {
  stopRendering()
  await nextTick()
  const document = documentState.value
  const target = canvas.value
  const layer = textLayer.value
  const root = pageRoot.value
  if (!document || !target || !layer || !root || !isPdf.value || mode.value !== 'pdf') return
  const sequence = ++renderSequence
  try {
    const pdfPage = await document.getPage(page.value)
    if (sequence !== renderSequence) return
    const base = pdfPage.getViewport({ scale: 1 })
    const fit = Math.min(1.2, Math.max(0.35, ((viewport.value?.clientWidth ?? 640) - 28) / base.width))
    const view = pdfPage.getViewport({ scale: zoom.value * fit })
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    const transform: [number, number, number, number, number, number] | undefined =
      ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0]
    root.style.width = view.width + 'px'
    root.style.height = view.height + 'px'
    root.style.setProperty('--scale-factor', String(view.scale))
    root.style.setProperty('--total-scale-factor', String(view.scale * pdfPage.userUnit))
    root.style.setProperty('--user-unit', String(pdfPage.userUnit))
    target.width = Math.ceil(view.width * ratio)
    target.height = Math.ceil(view.height * ratio)
    target.style.width = view.width + 'px'
    target.style.height = view.height + 'px'
    layer.replaceChildren()
    canvasTask = pdfPage.render({ canvas: target, viewport: view, transform })
    layerTask = new TextLayer({ textContentSource: pdfPage.streamTextContent(), container: layer, viewport: view })
    await Promise.all([canvasTask.promise, layerTask.render()])
    if (sequence === renderSequence) error.value = ''
  } catch {
    if (sequence === renderSequence) error.value = 'PDF 页面无法显示。可切换提取正文或下载原件。'
  }
}

async function loadPdf() {
  const sequence = ++loadSequence
  controller?.abort()
  stopRendering()
  void loadingTask?.destroy().catch(() => undefined)
  documentState.value = undefined
  pageCount.value = 0
  error.value = ''
  loading.value = false
  if (!activeFile.value || !isPdf.value || mode.value !== 'pdf') return
  const abort = new AbortController()
  controller = abort
  loading.value = true
  try {
    const blob = await annotationApi.file(props.sampleId, fileId.value, abort.signal)
    const data = await blob.arrayBuffer()
    if (sequence !== loadSequence) return
    loadingTask = getDocument({ data, isEvalSupported: false, useSystemFonts: true })
    const document = await loadingTask.promise
    if (sequence !== loadSequence) return
    documentState.value = document
    pageCount.value = document.numPages
    page.value = Math.max(1, Math.min(page.value, pageCount.value))
    await showPage()
  } catch {
    if (sequence === loadSequence) error.value = 'PDF 原版读取失败。可切换提取正文或下载原件。'
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function switchFile(id: string) {
  emit('clearSelection')
  page.value = 1
  zoom.value = 1
  fileId.value = id
  mode.value = props.files
    .find((file) => file.id === id)
    ?.name.toLowerCase()
    .endsWith('.pdf')
    ? 'pdf'
    : 'text'
}

function switchMode(next: 'pdf' | 'text') {
  emit('clearSelection')
  mode.value = next
}

async function download() {
  if (!activeFile.value) return
  const { id, name } = activeFile.value
  try {
    const data = await annotationApi.file(props.sampleId, id)
    const url = URL.createObjectURL(data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = name
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch {
    error.value = '原件下载失败。请刷新权限后重试。'
  }
}

function scrollToActive() {
  const root = viewport.value
  const target = root?.querySelector<HTMLElement>('.active')
  if (root && target) {
    const bounds = target.getBoundingClientRect()
    const view = root.getBoundingClientRect()
    root.scrollTo({ top: root.scrollTop + bounds.top - view.top - view.height / 3 })
  }
}

async function focusEvidence(evidence: Evidence) {
  if (fileId.value !== evidence.fileId) switchFile(evidence.fileId)
  if (evidence.rects?.length && evidence.page) {
    mode.value = 'pdf'
    page.value = evidence.page
  } else if (evidence.segmentId) {
    mode.value = 'text'
  }
  await nextTick()
  if (!loading.value) scrollToActive()
}

watch(
  () => [props.sampleId, props.files[0]?.id] as const,
  ([, first]) => switchFile(first ?? ''),
  { immediate: true },
)
watch(() => [props.sampleId, fileId.value, mode.value], loadPdf, { immediate: true })
watch([page, zoom], async () => {
  emit('clearSelection')
  await showPage()
  scrollToActive()
})
watch(
  () => props.active,
  (value) => {
    if (value) void focusEvidence(value)
  },
)
watch(loading, (value) => {
  if (!value) scrollToActive()
})
onBeforeUnmount(() => {
  loadSequence++
  controller?.abort()
  stopRendering()
  void loadingTask?.destroy().catch(() => undefined)
})
</script>

<style scoped>
.evidence-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: #fff;
}
.viewer-tools {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #e5ebf3;
}
.file-select {
  flex: 1;
  min-width: 140px;
}
.viewer-mode {
  justify-content: space-between;
}
.viewer-message {
  padding: 6px 12px;
  margin: 0;
  color: #8b4717;
}
.viewer-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: #eef2f7;
  padding: 14px;
}
.pdf-page {
  position: relative;
  margin: 0 auto;
  background: white;
  box-shadow: 0 1px 5px #142c4c25;
}
.pdf-page canvas {
  display: block;
}
.pdf-page .textLayer {
  z-index: 2;
}
.pdf-page .textLayer ::selection {
  background: #2a74bb66;
}
.rectangle-layer {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}
.rectangle-layer span {
  position: absolute;
  background: #ffc74572;
  border-bottom: 1px solid #a97818;
}
.rectangle-layer span.active {
  background: #f8c53aa6;
  box-shadow: 0 0 0 2px #2865a5;
}
.segments {
  background: white;
  padding: 10px 14px;
}
.segment {
  padding: 10px 0;
  border-bottom: 1px solid #e5ebf3;
}
.segment:last-child {
  border: none;
}
.segment-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin-bottom: 0;
}
.segment-text mark {
  padding: 0;
  background: #f9e293;
  color: inherit;
}
.segment-text mark.active {
  outline: 2px solid #2865a5;
}
</style>
