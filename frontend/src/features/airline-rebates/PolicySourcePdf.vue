<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { GlobalWorkerOptions, getDocument, TextLayer, type RenderTask } from 'pdfjs-dist/legacy/build/pdf.mjs'
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'

GlobalWorkerOptions.workerSrc = workerUrl

const props = defineProps<{ url: string; sourcePage?: string; sourceText?: string | null }>()
const viewport = ref<HTMLElement>()
const root = ref<HTMLElement>()
const canvas = ref<HTMLCanvasElement>()
const textLayer = ref<HTMLElement>()
const page = ref(1)
const total = ref(0)
const busy = ref(true)
const error = ref('')
const positioned = ref(false)
type Highlight = { left: string; top: string; width: string; height: string }
const highlights = ref<Highlight[]>([])
let loading: ReturnType<typeof getDocument> | undefined
let canvasTask: RenderTask | undefined
let layerTask: TextLayer | undefined
let sequence = 0

const normalize = (value: string) => value.normalize('NFKC').replace(/\s/gu, '')

function highlightSource(container: HTMLElement, divs: HTMLElement[]) {
  const needle = normalize(props.sourceText ?? '')
  if (needle.length < 4) return []
  const parts: { start: number; end: number; node: Text; offsets: number[] }[] = []
  let text = ''
  for (const div of divs) {
    const node = div.firstChild
    if (!(node instanceof Text)) continue
    const start = text.length
    const offsets: number[] = []
    for (let index = 0; index < node.length; index++) {
      const character = normalize(node.data[index])
      if (character) {
        text += character
        for (let count = 0; count < character.length; count++) offsets.push(index)
      }
    }
    if (offsets.length) parts.push({ start, end: text.length, node, offsets })
  }
  const start = text.indexOf(needle)
  if (start < 0 || text.indexOf(needle, start + 1) !== -1) return []
  const end = start + needle.length
  const origin = container.getBoundingClientRect()
  return parts.flatMap(part => {
    if (part.end <= start || part.start >= end) return []
    const range = document.createRange()
    range.setStart(part.node, part.offsets[Math.max(0, start - part.start)])
    range.setEnd(part.node, part.offsets[Math.min(part.offsets.length, end - part.start) - 1] + 1)
    return Array.from(range.getClientRects()).filter(rect => rect.width > 0 && rect.height > 0).map(rect => ({
      left: rect.left - origin.left + 'px', top: rect.top - origin.top + 'px',
      width: rect.width + 'px', height: rect.height + 'px',
    }))
  })
}

async function renderPage(next: number) {
  const current = ++sequence
  canvasTask?.cancel()
  layerTask?.cancel()
  positioned.value = false
  highlights.value = []
  busy.value = true
  error.value = ''
  try {
    const pdf = await loading?.promise
    if (!pdf || current !== sequence) return
    total.value = pdf.numPages
    page.value = Math.max(1, Math.min(next, pdf.numPages))
    const pdfPage = await pdf.getPage(page.value)
    await nextTick()
    if (current !== sequence || !root.value || !canvas.value || !textLayer.value) return
    const target = canvas.value
    const layer = textLayer.value
    const container = root.value
    const base = pdfPage.getViewport({ scale: 1 })
    const view = pdfPage.getViewport({ scale: Math.min(1.1, Math.max(0.3, ((viewport.value?.clientWidth ?? 480) - 24) / base.width)) })
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    container.style.width = view.width + 'px'
    container.style.height = view.height + 'px'
    container.style.setProperty('--scale-factor', String(view.scale))
    container.style.setProperty('--total-scale-factor', String(view.scale * pdfPage.userUnit))
    container.style.setProperty('--user-unit', String(pdfPage.userUnit))
    target.width = Math.ceil(view.width * ratio)
    target.height = Math.ceil(view.height * ratio)
    target.style.width = view.width + 'px'
    target.style.height = view.height + 'px'
    layer.replaceChildren()
    canvasTask = pdfPage.render({ canvas: target, viewport: view, transform: [ratio, 0, 0, ratio, 0, 0] })
    layerTask = new TextLayer({ textContentSource: pdfPage.streamTextContent(), container: layer, viewport: view })
    await Promise.all([canvasTask.promise, layerTask.render()])
    if (current !== sequence) return
    highlights.value = highlightSource(container, layerTask.textDivs)
    positioned.value = highlights.value.length > 0
    if (viewport.value) viewport.value.scrollTop = Math.max(0, parseFloat(highlights.value[0]?.top ?? '0') - 80)
  } catch {
    if (current === sequence) error.value = 'PDF 原页无法加载，请下载原件核对。'
  } finally {
    if (current === sequence) busy.value = false
  }
}

function release() {
  sequence++
  canvasTask?.cancel()
  layerTask?.cancel()
  void loading?.destroy().catch(() => undefined)
}

watch(() => [props.url, props.sourcePage, props.sourceText], () => {
  release()
  total.value = 0
  loading = getDocument({ url: props.url, withCredentials: true, isEvalSupported: false })
  void renderPage(Number(props.sourcePage?.match(/\d+/)?.[0]) || 1)
}, { immediate: true })
onBeforeUnmount(release)
</script>

<template>
  <section class="policy-pdf">
    <a-space wrap>
      <strong>合同原页</strong>
      <a-button size="small" :disabled="busy || page <= 1" @click="renderPage(page - 1)">上一页</a-button>
      <span v-if="total">第 {{ page }} / {{ total }} 页</span>
      <a-button size="small" :disabled="busy || !total || page >= total" @click="renderPage(page + 1)">下一页</a-button>
      <a :href="url">下载原件</a>
    </a-space>
    <a-alert v-if="error" :message="error" type="warning" show-icon />
    <a-alert v-else-if="!busy && !positioned" message="原文位置待核实，可翻页查看合同原件。" type="warning" show-icon />
    <a-spin :spinning="busy">
      <div ref="viewport" class="pdf-viewport">
        <div ref="root" class="pdf-page">
          <canvas ref="canvas" aria-label="政策合同 PDF 原页" />
          <div ref="textLayer" class="textLayer" />
          <div v-for="(box, index) in highlights" :key="index" class="pdf-highlight" :style="box" />
        </div>
      </div>
    </a-spin>
  </section>
</template>

<style scoped>
.policy-pdf{display:grid;gap:10px;min-width:0}
.pdf-viewport{height:570px;overflow:auto;background:#edf2f7;padding:12px}
.pdf-page{position:relative;margin:auto;background:white}
.pdf-highlight{position:absolute;z-index:3;background:#ffc92855;outline:1px solid #ae7600;pointer-events:none}
</style>
