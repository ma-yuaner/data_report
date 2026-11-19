<template>
  <div class="page-wrap parsing-page">
    <PageHeader
      eyebrow="ADM 控制台 / ADM 解析"
      title="ADM 解析"
      description="上传材料、提取字段并保存解析结果，原有台账与业务分析保持不变。"
    >
      <a-button @click="rulesOpen = true">字段与校验规则</a-button
      ><a-button :loading="loading" @click="refresh">刷新</a-button
      ><a-button type="primary" :disabled="!status?.canUpload" @click="openUpload">上传文件</a-button>
    </PageHeader>
    <a-alert
      v-if="status?.localTesting"
      type="info"
      show-icon
      message="本地隔离测试 · 真实文件读写与SQLite持久化；未连接生产业务库。模型接入是否启用以下方配置状态为准。"
    />
    <a-alert
      v-if="status && !status.ai.ready"
      type="warning"
      show-icon
      message="ADM 解析 API 尚未配置或启用"
      description="可以真实上传并保存文件。点击解析会读取原文并保留配置缺失原因；配置API后可重新解析，不会生成模拟业务结果。"
    />
    <a-alert v-if="error" type="error" show-icon :message="error" closable @close="error = ''" />
    <p v-if="notice" class="parsing-feedback" role="status">{{ notice }}</p>
    <div class="parsing-filter">
      <label>解析状态<a-select v-model:value="filter" :options="stateOptions" @change="changeFilter" /></label
      ><span>共 {{ total }} 件材料 · 刷新后保留已选来件</span>
    </div>
    <div class="parsing-workspace">
      <aside class="parsing-pane">
        <h2>解析来件</h2>
        <a-spin :spinning="loading"
          ><button
            v-for="item in items"
            :key="item.id"
            class="parsing-item"
            :aria-pressed="selected?.id === item.id"
            @click="select(item.id)"
          >
            <b>{{ item.title }}</b
            ><span>{{ item.files.length }} 份附件 · {{ formatTime(item.updatedAt) }}</span
            ><a-tag :color="stateColor(item.state)">{{ stateLabel(item.state) }}</a-tag
            ><span v-if="item.error">{{ item.error.message }}</span></button
          ><a-empty v-if="!items.length && !loading" description="暂无来件，请上传文件或调整状态筛选" /></a-spin
        ><a-pagination
          v-if="total"
          v-model:current="page"
          :total="total"
          :page-size="20"
          size="small"
          :show-size-changer="false"
          @change="loadList"
        />
      </aside>
      <section class="parsing-pane">
        <h2>原件与读取内容</h2>
        <div class="parsing-content" v-if="selected">
          <label
            >附件<a-select
              v-model:value="fileId"
              :options="selected.files.map((f) => ({ value: f.id, label: f.name }))"
              style="width: 100%"
          /></label>
          <p>
            <a v-if="fileId" :href="parsingApi.fileUrl(selected.id, fileId)" target="_blank" rel="noopener"
              >查看 / 下载原件</a
            >
          </p>
          <p class="parsing-muted">此处展示实际文件读取的文字；扫描件需先OCR，XLS需先另存为XLSX。</p>
          <div class="parsing-document">
            <section v-for="s in segments" :key="s.id" :id="`segment-${s.id}`" :class="{ located: located === s.id }">
              <b>{{ s.locator }}</b>
              <p>{{ s.text }}</p>
            </section>
            <a-empty
              v-if="!segments.length"
              :description="busy ? '正在读取或等待处理结果；请查看右侧进度' : '暂无读取正文；原件仍可下载'"
            />
          </div>
        </div>
        <a-empty v-else description="选择来件后查看原件" />
      </section>
      <section class="parsing-pane">
        <h2>解析结果</h2>
        <div v-if="selected" class="parsing-content">
          <div class="parsing-tags">
            <a-tag :color="stateColor(selected.state)">{{ stateLabel(selected.state) }}</a-tag
            ><a-tag :color="selected.saveStatus === 'FAILED' ? 'error' : 'success'">{{
              selected.saveStatus === 'FAILED'
                ? '结果保存失败，可重试'
                : ['SUCCEEDED', 'FAILED'].includes(selected.state)
                  ? '处理结果已保存'
                  : '任务记录已保存'
            }}</a-tag
            ><a-tag>第 {{ selected.attempts }} 次解析</a-tag>
          </div>
          <a-alert
            v-if="selected.error"
            type="error"
            show-icon
            :message="selected.error.message"
            :description="selected.error.code"
          />
          <a-alert
            v-if="selected.saveStatus === 'FAILED'"
            type="warning"
            show-icon
            message="解析结果已保留在服务器恢复文件中，尚未完成数据库保存。只重试保存，不重复调用模型。"
          />
          <div class="parsing-actions">
            <a-button
              v-if="selected.saveStatus === 'FAILED'"
              type="primary"
              :loading="acting"
              :disabled="!status?.canUpload"
              @click="retrySave"
              >重试保存</a-button
            ><a-button
              v-else
              type="primary"
              :loading="acting"
              :disabled="!status?.canUpload || busy"
              @click="startParse"
              >{{ selected.attempts ? '重新解析' : '开始解析' }}</a-button
            ><span v-if="busy">后台处理中，每3秒查询；切换页面后停止查询。</span>
          </div>
          <div class="parsing-progress" role="status" aria-live="polite">
            <strong>{{ progressText }}</strong>
            <p v-if="selected.elapsedSeconds !== undefined">
              本次已用 {{ selected.elapsedSeconds }} 秒 · 最近获取状态 {{ lastChecked || '—' }}
            </p>
            <p v-if="busy">
              排队 → 读取原件 → 等待模型 → 校验字段 → 保存结果。每3秒查询；模型未返回时无法提供生成百分比。
            </p>
            <p v-if="selected.stage === 'MODEL' && busy">原文已读取并保存，正在等待模型响应。请勿重复提交。</p>
            <p v-if="selected.state === 'RUNNING' && !selected.stage">
              此任务由旧版启动，未记录具体阶段；可等待结果，暂勿重新解析。
            </p>
          </div>
          <a-tabs v-model:active-key="tab"
            ><a-tab-pane key="fields" tab="提取字段">
              <p v-if="!selected.candidate" class="parsing-muted">
                尚无模型字段结果。原件、读取内容和失败原因仍会保留。
              </p>
              <template v-if="selected.candidate"
                ><button
                  v-for="field in fields"
                  :key="field.key"
                  class="parsing-field"
                  @click="locate(`/adm/${field.key}`)"
                >
                  <span>{{ field.label }}{{ field.required ? ' *' : '' }}</span
                  ><b>{{ selected.candidate.adm?.[field.key] ?? '未提取到' }}</b
                  ><small>来源</small>
                </button>
                <h3>交易明细 {{ displayLines.length }} 条</h3>
                <div class="parsing-table">
                  <table>
                    <thead>
                      <tr>
                        <th>交易 / 编码（按来源区分）</th>
                        <th>票号 / 系统 / PCC</th>
                        <th>金额用途 / 币种 / 佣金</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(entry, i) in displayLines" :key="i">
                        <td>
                          {{ entry.line.transactionNumber ?? entry.line.lineId }} · {{ entry.line.action ?? '—' }}<br />
                          <button
                            v-for="code in pnrFields"
                            :key="code.key"
                            class="parsing-source"
                            @click="locate(`/lines/${entry.index}/${code.key}`)"
                          >
                            {{ code.label }}：{{ showCodes(entry.line[code.key]) }}<br />
                          </button>
                          <div>
                            操作 {{ entry.line.transactionDate ?? '—' }} / 航班 {{ entry.line.flightDate ?? '—' }}
                          </div>
                        </td>
                        <td>
                          {{ entry.line.ticketNumber ?? '未提取到' }}（{{
                            ticketLabel(entry.line.ticketType)
                          }}）<br />{{ entry.line.gds ?? '—' }} /
                          {{ entry.line.pcc ?? '—' }}
                        </td>
                        <td>
                          {{ amountLabel(entry.line.amountPurpose) }}<br />原文 {{ entry.line.amountText ?? '—'
                          }}<br />{{ entry.line.amount ?? '未提取到' }} {{ entry.line.currency }}<br />佣金比例
                          {{ entry.line.commissionRate ?? '—' }}%<br />佣金 {{ entry.line.commissionAmount ?? '—' }}
                          {{ entry.line.commissionCurrency }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>
              <p v-if="selected.classification">
                原因归类建议（待核对）：{{
                  selected.classification.matches.map((m) => `${m.reason} / ${m.department}`).join('；') ||
                  '未匹配，人工核对'
                }}。不自动分配负责人。
              </p>
              <p v-if="selected.candidate?.schemaVersion === 'adm-extraction/1.0'">
                此为旧版结果，PNR来源未区分；重新解析后使用新版字段，历史原样保留。
              </p>
              <h3>校验结果</h3>
              <p v-for="(issue, i) in selected.issues" :key="i" class="parsing-issue">
                <a-tag :color="issue.level === 'error' ? 'error' : 'warning'">{{
                  issue.level === 'error' ? '失败' : '待核对'
                }}</a-tag
                >{{ issue.message }}<small>{{ issue.path }} · {{ issue.code }}</small>
              </p>
              <p v-if="selected.candidate && !selected.issues?.length">
                字段与来源校验通过；解析成功不代表业务核对或申诉完成。
              </p> </a-tab-pane
            ><a-tab-pane key="json" tab="固定 JSON">
              <pre>{{ JSON.stringify(selected.candidate, null, 2) }}</pre></a-tab-pane
            ><a-tab-pane key="history" tab="解析记录"
              ><p>模型 {{ selected.model || '未调用' }} · 规则 {{ selected.promptVersion || status?.schemaVersion }}</p>
              <p v-if="selected.usage">
                输入 {{ selected.usage.prompt_tokens }} / 输出 {{ selected.usage.completion_tokens }} tokens
              </p>
              <p v-else>本次用量未知或尚未调用，不推算费用。</p>
              <div v-for="(run, i) in selected.history" :key="i">
                {{ run.at }} · 第{{ run.attempt }}次 · {{ stateLabel(run.state) }}
                <details>
                  <summary>查看历史候选和校验</summary>
                  <pre>{{ JSON.stringify(run, null, 2) }}</pre>
                </details>
              </div></a-tab-pane
            ></a-tabs
          >
          <a-alert type="info" message="这里只保存解析来件与结果，不自动新建ADM、恢复PNR、分配负责人或修改原有业务。" />
        </div>
        <a-empty v-else description="选择来件后查看解析结果" />
      </section>
    </div>
    <FormDialog
      v-model:open="uploadOpen"
      title="上传 ADM 解析材料"
      :busy="uploading"
      :dirty="files.length > 0"
      :error="uploadError"
      ok-text="上传并保存"
      @submit="upload"
    >
      <label class="parsing-upload"
        >选择文件<input :key="inputKey" type="file" multiple accept=".pdf,.xlsx,.txt,.csv,.docx" @change="choose"
      /></label>
      <p>每件1–10份，单份20MB、合计50MB。支持PDF、XLSX、TXT、CSV、DOCX；同一ADM的材料放在同一来件。</p>
      <ul>
        <li v-for="(f, i) in files" :key="i">{{ f.name }}（{{ Math.ceil(f.size / 1024) }} KB）</li>
      </ul>
      <a-alert type="info" message="上传先保存原件，随后点击开始解析。API配置缺失不会阻止保存材料。" />
    </FormDialog>
    <a-drawer v-model:open="rulesOpen" title="固定 JSON 与成功失败规则" width="min(760px, 95vw)"
      ><p>
        必填：ADM编号、发单方、正式金额、币种，且需引用实际上传原文。未知值用null，金额为非负十进制字符串，允许0，不换汇。
      </p>
      <p>
        缺必填、类型错误、来源不匹配：解析失败；来源冲突、缺可选字段、币种不同、明细合计差异：解析成功但待人工核对。供应商、航司、日期、截止日期、票号、系统、PCC按原件提取，不编造交易历史。
      </p>
      <p>
        API协议：chat-completions。服务端配置ADM_PARSING_AI_ENABLED、ADM_PARSING_AI_URL（完整HTTPS地址）、ADM_PARSING_AI_KEY、ADM_PARSING_AI_MODEL，重启服务后生效；页面不接收或展示密钥。
      </p>
      <p>
        航司PNR和GDS编码分别保留；来源未明编码不用于自动恢复。虚拟票号禁止匹配真实出票。正式金额、单位罚款、票据总额和佣金分开；只有罚单明细参与合计。报表日不能作为截止日。图片和扫描件需先转为可读正文。
      </p>
      <p>文件和记录按上传人隔离；有ADM管理权限可查看全部。单件最多10次显式解析，不自动付费重试。</p>
      <pre>{{ JSON.stringify(status?.template, null, 2) }}</pre>
    </a-drawer>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import FormDialog from '@/components/FormDialog.vue'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
import { parsingApi, type ParseTask, type ParseStatus } from './api'
const status = ref<ParseStatus>(),
  items = ref<ParseTask[]>([]),
  selected = ref<ParseTask>(),
  total = ref(0),
  page = ref(1),
  filter = ref(''),
  error = ref(''),
  notice = ref(''),
  lastChecked = ref(''),
  loading = ref(false),
  acting = ref(false),
  tab = ref('fields'),
  fileId = ref(''),
  located = ref(''),
  rulesOpen = ref(false),
  uploadOpen = ref(false),
  uploading = ref(false),
  uploadError = ref(''),
  files = ref<File[]>([]),
  inputKey = ref(0)
const labels: Record<string, string> = {
  UPLOADED: '已上传',
  QUEUED: '排队中',
  RUNNING: '解析中',
  SUCCEEDED: '解析成功',
  FAILED: '解析失败',
}
const stateOptions = [
  { value: '', label: '全部' },
  ...Object.entries(labels).map(([value, label]) => ({ value, label })),
]
const stateLabel = (s: string) => labels[s] || s
const stateColor = (s: string) =>
  s === 'SUCCEEDED'
    ? 'success'
    : s === 'FAILED'
      ? 'error'
      : ['QUEUED', 'RUNNING'].includes(s)
        ? 'processing'
        : 'default'
const fields = [
  { key: 'number', label: 'ADM编号', required: true },
  { key: 'issuer', label: '发单方', required: true },
  { key: 'supplierName', label: '供应商候选' },
  { key: 'airline', label: '航司' },
  { key: 'issuedDate', label: '开具日期' },
  { key: 'amount', label: '正式金额', required: true },
  { key: 'currency', label: '币种', required: true },
  { key: 'reportingDate', label: '报表日期' },
  { key: 'dueDate', label: '截止日期' },
  { key: 'reason', label: '下发原因' },
]
const pnrFields = [
  { key: 'airlinePnrs', label: '航司PNR' },
  { key: 'gdsPnrs', label: 'GDS编码' },
  { key: 'pnrs', label: '来源未明PNR' },
]
const showCodes = (value: unknown) => (Array.isArray(value) ? value.join(' / ') || '未提取到' : '未提取到')
const ticketLabel = (value: unknown) =>
  ({ real: '真实票号', virtual: '虚拟票号，禁止匹配出票', unknown: '类型待核对' })[String(value)] || '类型待核对'
const amountLabel = (value: unknown) =>
  ({
    admCharge: '罚单明细',
    unitPenalty: '单位罚款',
    ticketTotal: '票据总额',
    other: '其他金额',
    unknown: '用途待核对',
  })[String(value)] || '用途待核对'
const busy = computed(
  () => ['QUEUED', 'RUNNING'].includes(selected.value?.state || '') && selected.value?.saveStatus !== 'FAILED',
)
const progressText = computed(() => {
  const task = selected.value
  if (!task) return ''
  if (task.saveStatus === 'FAILED') return '模型处理已结束，结果待重试保存'
  if (task.state === 'SUCCEEDED') return '解析和结果保存完成，请核对字段'
  if (task.state === 'FAILED') return '处理失败，失败原因已保存'
  return (
    {
      UPLOADED: '原件已保存，等待开始解析',
      QUEUED: '已排队，等待处理',
      READING: '正在校验原件并读取正文',
      MODEL: '正文已保存，正在等待模型响应',
      VALIDATING: '模型已返回，正在校验字段并准备保存',
    }[task.stage || task.state] || '后台处理中'
  )
})
const segments = computed(() => selected.value?.segments?.filter((s) => s.fileId === fileId.value) || [])
const displayLines = computed(() => {
  const lines = selected.value?.candidate?.lines
  return Array.isArray(lines)
    ? lines
        .map((line, index) => ({ line, index }))
        .filter((entry) => !!entry.line && typeof entry.line === 'object' && !Array.isArray(entry.line))
    : []
})
const formatTime = formatDateTimeDisplay
let stopped = false,
  listGeneration = 0,
  generation = 0,
  timer: ReturnType<typeof setTimeout> | undefined,
  requestKey = ''
const message = (e: unknown) => (e instanceof Error ? e.message : '操作失败，请刷新状态后重试')
async function loadList() {
  const token = ++listGeneration
  loading.value = true
  try {
    const result = await parsingApi.list(page.value, filter.value)
    if (!stopped && token === listGeneration) {
      items.value = result.items
      total.value = result.total
    }
  } catch (e) {
    if (token === listGeneration) error.value = message(e)
  } finally {
    if (token === listGeneration) loading.value = false
  }
}
async function changeFilter() {
  page.value = 1
  await loadList()
}
function schedule() {
  if (timer) clearTimeout(timer)
  if (!stopped && busy.value)
    timer = setTimeout(async () => {
      if (!document.hidden && selected.value) await select(selected.value.id, false)
      else schedule()
    }, 3000)
}
async function select(id: string, reset = true) {
  const token = ++generation
  if (reset) {
    selected.value = undefined
    if (timer) clearTimeout(timer)
  }
  try {
    const task = await parsingApi.detail(id)
    if (stopped || token !== generation) return
    selected.value = task
    lastChecked.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    if (reset || !task.files.some((f) => f.id === fileId.value)) {
      fileId.value = task.files[0]?.id || ''
      located.value = ''
      tab.value = 'fields'
    }
    items.value = items.value.map((item) => (item.id === id ? task : item))
    schedule()
  } catch (e) {
    if (token === generation) {
      error.value = message(e)
      if (timer) clearTimeout(timer)
    }
  }
}
async function refresh() {
  error.value = ''
  try {
    status.value = await parsingApi.status()
    await loadList()
    if (selected.value) await select(selected.value.id, false)
    else if (items.value[0]) await select(items.value[0].id)
  } catch (e) {
    error.value = message(e)
  }
}
function openUpload() {
  files.value = []
  uploadError.value = ''
  inputKey.value++
  requestKey = `admparse_${Date.now()}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`
  uploadOpen.value = true
}
function choose(event: Event) {
  files.value = Array.from((event.target as HTMLInputElement).files || [])
}
async function upload() {
  if (uploading.value) return
  if (
    !files.value.length ||
    files.value.length > 10 ||
    files.value.some((f) => !f.size || f.size > 20 * 1024 * 1024 || !/\.(pdf|xlsx|txt|csv|docx)$/i.test(f.name)) ||
    files.value.reduce((sum, f) => sum + f.size, 0) > 50 * 1024 * 1024
  ) {
    uploadError.value = '请选择1–10份支持格式的非空文件，单份20MB、合计50MB以内'
    return
  }
  uploading.value = true
  uploadError.value = ''
  try {
    const task = await parsingApi.upload(files.value, requestKey)
    uploadOpen.value = false
    notice.value = '原件及任务已保存，点击开始解析读取内容。'
    filter.value = ''
    page.value = 1
    await loadList()
    await select(task.id)
  } catch (e) {
    uploadError.value = message(e)
  } finally {
    uploading.value = false
  }
}
async function startParse() {
  if (!selected.value || acting.value || busy.value) return
  acting.value = true
  error.value = ''
  const task = selected.value,
    token = generation
  try {
    const result = await parsingApi.parse(task)
    if (stopped || token !== generation) return
    selected.value = result
    notice.value = '解析请求已提交，当前阶段见下方进度。'
    schedule()
  } catch (e) {
    error.value = message(e)
    if (token === generation && selected.value) await select(selected.value.id, false)
  } finally {
    acting.value = false
  }
}
async function retrySave() {
  if (!selected.value || acting.value) return
  acting.value = true
  const task = selected.value,
    token = generation
  try {
    const result = await parsingApi.retrySave(task)
    if (stopped || token !== generation) return
    selected.value = result
    notice.value = '保存状态已核对，未重新调用模型。'
    await loadList()
  } catch (e) {
    error.value = message(e)
  } finally {
    acting.value = false
  }
}
async function locate(path: string) {
  const evidence = selected.value?.candidate?.evidence
  if (!Array.isArray(evidence)) return
  const e = evidence.find((e) => e.path === path)
  const segment = selected.value?.segments?.find((s) => s.id === e?.segmentId)
  if (!segment) {
    notice.value = '该字段暂无有效来源，请核对原件。'
    return
  }
  fileId.value = segment.fileId
  located.value = segment.id
  await nextTick()
  document.getElementById(`segment-${segment.id}`)?.scrollIntoView({ block: 'nearest', behavior: 'auto' })
}
onMounted(refresh)
onBeforeUnmount(() => {
  stopped = true
  generation++
  if (timer) clearTimeout(timer)
})
</script>
<style scoped>
.parsing-page {
  min-width: 0;
}
.parsing-page > .ant-alert {
  margin-bottom: 16px;
}
.parsing-filter {
  display: flex;
  align-items: end;
  gap: 16px;
  margin: 16px 0;
  color: #58677b;
}
.parsing-filter label {
  display: grid;
  gap: 6px;
  width: 180px;
}
.parsing-workspace {
  display: grid;
  grid-template-columns: 230px minmax(260px, 1fr) minmax(350px, 1.3fr);
  gap: 16px;
  align-items: start;
}
.parsing-pane {
  min-width: 0;
  background: white;
  border: 1px solid #dce3ec;
  border-radius: 6px;
}
.parsing-pane h2 {
  font-size: 16px;
  padding: 16px;
  border-bottom: 1px solid #e8edf3;
  margin: 0;
}
.parsing-content {
  padding: 16px;
}
.parsing-item {
  display: grid;
  gap: 7px;
  width: 100%;
  text-align: left;
  padding: 16px;
  background: white;
  border: 0;
  border-bottom: 1px solid #e8edf3;
  cursor: pointer;
  color: var(--platform-text, #203447);
  overflow-wrap: anywhere;
}
.parsing-item[aria-pressed='true'] {
  background: var(--platform-selected, #eaf3fc);
  box-shadow: inset 3px 0 var(--platform-primary, #2673ad);
}
.parsing-item span,
.parsing-muted {
  font-size: 12px;
  color: #58677b;
}
.parsing-field {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr) 30px;
  gap: 8px;
  width: 100%;
  border: 0;
  border-bottom: 1px solid #e8edf3;
  padding: 10px 0;
  text-align: left;
  background: white;
  cursor: pointer;
}
.parsing-field b {
  overflow-wrap: anywhere;
}
.parsing-field small,
.parsing-source {
  color: #1667ce;
}
.parsing-document {
  max-height: 650px;
  overflow: auto;
  background: var(--platform-hover, #f0f6fc);
  border: 1px solid #e1e6ed;
  padding: 12px;
}
.parsing-document section {
  border-left: 3px solid transparent;
  padding: 8px;
}
.parsing-document .located {
  border-color: #d49400;
  background: #fff3cd;
}
.parsing-document p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.parsing-tags,
.parsing-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 8px 0 16px;
}
.parsing-table {
  overflow: auto;
}
.parsing-table table {
  width: 100%;
  min-width: 440px;
  border-collapse: collapse;
}
.parsing-table td,
.parsing-table th {
  padding: 8px;
  border-bottom: 1px solid #e8edf3;
  text-align: left;
}
.parsing-table td:last-child {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.parsing-source {
  border: 0;
  background: none;
  cursor: pointer;
  text-align: left;
}
.parsing-issue {
  border-bottom: 1px solid #eee;
  padding-bottom: 8px;
}
.parsing-issue small {
  display: block;
  overflow-wrap: anywhere;
  color: #58677b;
}
.parsing-progress {
  padding: 12px;
  border: 1px solid #dce3ec;
  margin-bottom: 16px;
}
.parsing-progress p {
  margin: 8px 0 0;
  overflow-wrap: anywhere;
}
.parsing-feedback {
  padding: 12px;
  background: var(--platform-selected, #eaf3fc);
  color: #1656a0;
}
.parsing-upload {
  display: grid;
  gap: 8px;
  margin: 16px 0;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 550px;
  overflow: auto;
}
button:focus-visible {
  outline: 2px solid var(--platform-primary, #2673ad);
  outline-offset: 2px;
}
h3 {
  font-size: 14px;
  margin-top: 16px;
}
.parsing-pane > .ant-pagination {
  padding: 12px;
}
@media (max-width: 1250px) {
  .parsing-workspace {
    grid-template-columns: 210px minmax(0, 1fr);
  }
  .parsing-pane:last-child {
    grid-column: 1/-1;
  }
}
@media (max-width: 760px) {
  .parsing-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
  .parsing-pane:last-child {
    grid-column: auto;
  }
  .parsing-filter {
    flex-wrap: wrap;
  }
}
</style>
