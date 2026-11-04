<template>
  <div class="page-wrap risk-verification">
    <PageHeader eyebrow="RISK VERIFICATION" title="风控核对" description="筛选待核查 → 取证审核 → 人工确认 → 分析与知识沉淀。">
      <a-button @click="router.push('/risk-analysis/orders')">返回订单明细</a-button>
    </PageHeader>
    <a-alert type="info" show-icon message="命中不等于判错，AI意见须人工确认" description="明确规则由程序执行，AI只检索已发布知识并辅助解释。公式未确认时保留证据不足；不写回ERP、不执行交易处理。模型未配置时会明确提示，不返回模拟分析。" />
    <a-alert v-if="serviceStatus" :type="serviceStatus.sourceConfigured ? 'info' : 'warning'" show-icon :message="serviceStatus.sourceConfigured ? 'ERP配置存在，实际读取以查询结果为准' : 'ERP尚未配置，请由部署人核对已有ERP_MYSQL配置'" :description="serviceStatus.ai.enabled && serviceStatus.ai.configured ? `AI已配置：${serviceStatus.ai.model}；配置存在不等于真实调用已验收` : '风控AI未启用或未配置，可先完成取证和人工核对。'" />
    <a-alert v-for="rule in serviceStatus?.rules || []" :key="rule.id" type="warning" show-icon :message="rule.label" :description="`${rule.formula}。${rule.status}`" />
    <section class="scope-panel">
      <h2>找出待核查订单</h2>
      <p>筛选条件：盈亏原因分类有值（原始编码保留）。按订单创建日期查询，单次最多31天。</p>
      <div class="verification-fields">
        <label>开始日期<DateField v-model="startDate" :allow-clear="false" :disabled="loading" /></label>
        <label>结束日期<DateField v-model="endDate" :allow-clear="false" :disabled="loading" /></label>
        <a-button type="primary" :loading="loading" @click="loadCandidates()">查询待核查</a-button>
      </div>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-table v-if="candidates" :data-source="candidates.items" :columns="columns" row-key="id" :pagination="false" :scroll="{ x: 1000, y: 320 }" size="small">
        <template #bodyCell="{ column, record }">
          <a-button v-if="column.key === 'action'" type="link" :disabled="reading" @click="openOrder(String(record.id), 'id')">查看证据</a-button>
        </template>
      </a-table>
      <a-button v-if="candidates?.hasMore" :disabled="loading || criteriaChanged" @click="loadCandidates(candidates?.nextBefore || undefined)">下一批</a-button>
      <p v-if="criteriaChanged" class="muted">日期已改变，请重新查询后再翻批。</p>
      <p v-if="!candidates" class="muted">尚未查询。不会自动读取订单。</p>
    </section>
    <section class="scope-panel">
      <h2>查看指定订单证据</h2>
      <div class="verification-fields">
        <label>标识类型<a-select v-model:value="identifierMode" :disabled="reading" :options="[{label:'自动：数字视为内部ID',value:'auto'},{label:'ERP内部ID',value:'id'},{label:'业务/OTA订单号（含纯数字）',value:'orderNo'}]" /></label>
        <label>ERP内部ID或订单号<a-input v-model:value="identifier" :disabled="reading" placeholder="输入内部ID或明确的业务/OTA订单号" @press-enter="openOrder(identifier)" /></label>
        <a-button :loading="reading" @click="openOrder(identifier)">读取订单</a-button>
      </div>
      <p>基础读取航段、乘客和出票；可选择补充关联单索引、操作日志及状态历史。</p>
      <a-checkbox-group v-model:value="sections" :options="sectionOptions" :disabled="reading" />
      <a-alert v-if="evidenceError" type="error" show-icon :message="evidenceError" />
      <template v-if="evidence">
        <p>{{ evidence.notice }} · 取证时间：{{ evidence.fetchedAt }}</p>
        <a-tag :color="evidence.candidate ? 'orange' : 'default'">{{ evidence.candidate ? '命中待核查条件' : '未命中当前条件' }}</a-tag>
        <p class="muted">分块顺序读取，不承诺同一数据库快照；关联单仅索引。状态编码原样展示，缺失字段不补0。</p>
        <details open><summary>订单基本信息与盈亏原因分类</summary><pre>{{ JSON.stringify(evidence.order, null, 2) }}</pre></details>
        <details v-for="(block, key) in evidence.blocks" :key="key">
          <summary>{{ block.label }} · {{ statusLabel[block.status] }} · {{ block.records.length }}条</summary>
          <p v-if="block.error">{{ block.error }}</p>
          <p v-if="block.status === 'truncated'">当前仅展示前200条，证据不完整，不能据此形成完整审核结论。</p>
          <pre v-if="block.records.length">{{ JSON.stringify(block.records, null, 2) }}</pre>
        </details>
        <a-button type="primary" :disabled="!evidence.candidate || busy" :loading="busy" @click="createCase">以当前订单新建核查记录</a-button>
        <p class="muted">新建时服务端重新取证并保存快照；当前预览不作为最终快照。再次核查创建独立记录，历史结果保留。</p>
      </template>
    </section>
    <section class="scope-panel">
      <div class="verification-fields"><h2>核查记录与审核结论</h2><a-button :disabled="busy" @click="refreshFlow">刷新记录</a-button></div>
      <a-alert v-if="flowError" type="error" show-icon :message="flowError" />
      <a-alert v-if="flowMessage" type="success" show-icon :message="flowMessage" />
      <a-select v-model:value="selectedCaseId" :options="caseOptions" :disabled="busy" placeholder="选择已保存的核查记录" class="case-select" @change="selectCase" />
      <template v-if="currentCase">
        <p>记录 {{ currentCase.id }} · {{ caseState[currentCase.state] || currentCase.state }} · 版本 {{ currentCase.version }}</p>
        <p class="muted">证据指纹：{{ currentCase.evidenceFingerprint }}</p>
        <div class="verification-fields">
          <a-button :disabled="busy" @click="previewAi">查看拟发送AI的内容</a-button>
          <a-button type="primary" :loading="busy" @click="reviewCase">AI审核当前快照</a-button>
          <a-button v-if="currentCase.activeOperation" :disabled="busy" @click="recoverCase">恢复中断操作</a-button>
        </div>
        <details v-if="aiPreview" open><summary>外发预览与检索知识</summary><pre>{{ JSON.stringify(aiPreview, null, 2) }}</pre></details>
        <details v-if="currentCase.reviews.length" open><summary>审核结果与证据引用</summary><pre>{{ JSON.stringify(currentCase.reviews, null, 2) }}</pre></details>
        <div class="verification-fields">
          <label>人工结论<a-select v-model:value="conclusion" :options="conclusionOptions" :disabled="busy" /></label>
        </div>
        <label class="text-field">确认理由与依据<a-textarea v-model:value="confirmationReason" :rows="3" :disabled="busy" placeholder="说明核对依据、公式或仍缺少的证据；不得只照抄AI结论" /></label>
        <div class="verification-fields">
          <a-button :disabled="busy || !confirmationReason.trim()" @click="confirmCase">保存人工确认</a-button>
          <a-button :disabled="busy || !currentCase.confirmation" @click="analyzeCase">基于确认结果分析</a-button>
        </div>
        <details v-if="currentCase.confirmation" open><summary>人工确认留痕</summary><pre>{{ JSON.stringify(currentCase.confirmation, null, 2) }}</pre></details>
        <details v-if="currentCase.analyses.length" open><summary>后续分析</summary><pre>{{ JSON.stringify(currentCase.analyses, null, 2) }}</pre></details>
        <details><summary>本次已保存的完整证据快照</summary><pre>{{ JSON.stringify(currentCase.evidence, null, 2) }}</pre></details>
        <h3>沉淀可复用知识</h3>
        <p class="muted">只填写通用核查方法与适用范围，不粘贴原始订单、姓名、票号或日志；草稿不会参与检索。</p>
        <div class="verification-fields">
          <label>知识标题<a-input v-model:value="knowledgeDraft.title" :disabled="busy" /></label>
          <label>适用范围<a-input v-model:value="knowledgeDraft.scope" :disabled="busy" /></label>
          <label>确认依据或来源<a-input v-model:value="knowledgeDraft.source" :disabled="busy" /></label>
        </div>
        <label class="text-field">知识内容<a-textarea v-model:value="knowledgeDraft.content" :rows="4" :disabled="busy" /></label>
        <a-button :disabled="busy || !currentCase.confirmation" @click="draftKnowledge">保存知识草稿</a-button>
      </template>
    </section>
    <section class="scope-panel">
      <h2>知识库</h2>
      <p>首版按词面检索本人已发布知识，不使用向量库。知识发布不自动成为金额判断公式。</p>
      <p v-if="!knowledge.length" class="muted">暂无知识，先完成一个案例并整理可复用依据。</p>
      <details v-for="item in knowledge" :key="item.id">
        <summary>{{ item.title }} · {{ item.status === 'published' ? '已发布' : '草稿' }} · 版本 {{ item.version }}</summary>
        <p>适用范围：{{ item.scope }}；来源：{{ item.source }}</p><pre>{{ item.content }}</pre>
        <a-popconfirm v-if="item.status === 'draft'" title="确认内容已核实、无原始订单或个人资料，并发布供后续检索？" @confirm="publishKnowledge(item)">
          <a-button :disabled="busy">人工确认并发布</a-button>
        </a-popconfirm>
      </details>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Alert as AAlert, Button as AButton, CheckboxGroup as ACheckboxGroup, Input as AInput, Textarea as ATextarea, Table as ATable, Tag as ATag, Select as ASelect, Popconfirm as APopconfirm } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import DateField from '@/components/DateField.vue'
import { riskCandidates, riskEvidence, riskFlow, type RiskCandidates, type RiskEvidence, type RiskCase, type RiskCaseSummary, type RiskKnowledge, type RiskStatus } from '@/api/riskVerification'

const router = useRouter()
const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
const startDate = ref<string | null | undefined>(today)
const endDate = ref<string | null | undefined>(today)
const queriedDates = ref('')
const criteriaChanged = computed(() => Boolean(candidates.value) && queriedDates.value !== `${startDate.value}/${endDate.value}`)
const candidates = ref<RiskCandidates>()
const evidence = ref<RiskEvidence>()
const identifier = ref('')
const identifierMode = ref<'auto' | 'id' | 'orderNo'>('auto')
const loading = ref(false)
const reading = ref(false)
const busy = ref(false)
const flowError = ref('')
const flowMessage = ref('')
const cases = ref<RiskCaseSummary[]>([])
const serviceStatus = ref<RiskStatus>()
const knowledge = ref<RiskKnowledge[]>([])
const currentCase = ref<RiskCase>()
const selectedCaseId = ref<string>()
const aiPreview = ref<unknown>()
const conclusion = ref('insufficient')
const confirmationReason = ref('')
const knowledgeDraft = ref({ title: '', content: '', scope: '', source: '' })
const caseOptions = computed(() => cases.value.map(item => ({ value: item.id, label: `${item.erpOrderId} · ${caseState[item.state] || item.state} · ${item.createdAt}` })))
const caseState: Record<string, string> = { evidence_ready: '待审核', reviewed: '待人工确认', confirmed: '已人工确认', analyzed: '已分析' }
const conclusionOptions = [{ label: '证据不足，待补充', value: 'insufficient' }, { label: '证据支持原分类', value: 'supported' }, { label: '证据与原分类矛盾', value: 'contradicted' }]
const error = ref('')
const evidenceError = ref('')
const sections = ref(['segments', 'passengers', 'issues'])
const sectionOptions = [
  { label: '航段', value: 'segments' }, { label: '乘客', value: 'passengers' }, { label: '出票', value: 'issues' },
  { label: '改签索引', value: 'changes' }, { label: '退票索引', value: 'refunds' },
  { label: '航变索引', value: 'flightChanges' }, { label: '增值索引', value: 'ancillaries' },
  { label: '操作日志', value: 'operatorLogs' }, { label: '状态历史', value: 'statusHistory' },
]
const statusLabel = { ready: '已读取', empty: '已读无记录', failed: '读取失败', truncated: '已截断', not_requested: '尚未读取', not_integrated: '尚未接入' }
const columns = [
  { title: '内部订单ID', dataIndex: 'id', width: 170 }, { title: '业务订单号', dataIndex: 'order_no', width: 180 },
  { title: 'OTA订单号', dataIndex: 'ota_order_no', width: 180 }, { title: '盈亏原因分类（原始值）', dataIndex: 'profit_reason_type', width: 190 },
  { title: '创建时间', dataIndex: 'create_time', width: 180 }, { title: '操作', key: 'action', width: 100 },
]
let candidateRequest = 0
let evidenceRequest = 0
let alive = true
onBeforeUnmount(() => { alive = false; candidateRequest++; evidenceRequest++ })
onMounted(refreshFlow)
async function refreshFlow() {
  try {
    const [savedCases, savedKnowledge, status] = await Promise.allSettled([riskFlow.list(), riskFlow.knowledge(), riskFlow.status()])
    if (alive) {
      if (status.status === 'fulfilled') serviceStatus.value = status.value
      if (savedCases.status === 'fulfilled') cases.value = savedCases.value
      if (savedKnowledge.status === 'fulfilled') knowledge.value = savedKnowledge.value
      const failed = [savedCases, savedKnowledge, status].find(item => item.status === 'rejected')
      flowError.value = failed?.status === 'rejected' ? (failed.reason instanceof Error ? failed.reason.message : '部分状态读取失败，请核对配置或存储权限') : ''
    }
  } catch (failure) { if (alive) flowError.value = failure instanceof Error ? failure.message : '历史记录读取失败' }
}
async function flowAction(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; flowError.value = ''; flowMessage.value = ''
  try { await action() }
  catch (failure) {
    if (alive) {
      flowError.value = failure instanceof Error ? failure.message : '操作失败，请重试；已有结果保留'
      if (currentCase.value) {
        try { const fresh = await riskFlow.get(currentCase.value.id); if (alive) currentCase.value = fresh } catch { /* Preserve existing view if refresh also fails. */ }
      }
    }
  }
  finally { if (alive) busy.value = false }
}
async function selectCase() {
  if (!selectedCaseId.value) return
  const id = selectedCaseId.value
  await flowAction(async () => {
    currentCase.value = undefined
    resetCaseDrafts()
    const item = await riskFlow.get(id)
    if (alive && selectedCaseId.value === id) { currentCase.value = item; resetCaseDrafts() }
  })
}
async function createCase() {
  if (!evidence.value) return
  const id = evidence.value.erpOrderId
  await flowAction(async () => {
    const item = await riskFlow.create(id, [...sections.value])
    if (alive) { currentCase.value = item; selectedCaseId.value = item.id; resetCaseDrafts(); flowMessage.value = '核查记录已保存，可刷新后继续' }
    await refreshFlow()
  })
}
function resetCaseDrafts() {
  aiPreview.value = undefined
  confirmationReason.value = ''
  conclusion.value = 'insufficient'
  knowledgeDraft.value = { title: '', content: '', scope: '', source: '' }
}
async function previewAi() {
  if (!currentCase.value) return
  await flowAction(async () => { const preview = await riskFlow.preview(currentCase.value!.id); if (alive) aiPreview.value = preview })
}
async function reviewCase() {
  if (!currentCase.value) return
  await flowAction(async () => { const item = await riskFlow.review(currentCase.value!); if (alive) { currentCase.value = item; flowMessage.value = 'AI审核已保存，仍需人工确认' }; await refreshFlow() })
}
async function confirmCase() {
  if (!currentCase.value) return
  await flowAction(async () => { const item = await riskFlow.confirm(currentCase.value!, conclusion.value, confirmationReason.value); if (alive) { currentCase.value = item; flowMessage.value = '人工确认已保存' }; await refreshFlow() })
}
async function analyzeCase() {
  if (!currentCase.value) return
  await flowAction(async () => { const item = await riskFlow.analyze(currentCase.value!); if (alive) { currentCase.value = item; flowMessage.value = '分析结果已保存' }; await refreshFlow() })
}
async function recoverCase() {
  if (!currentCase.value) return
  await flowAction(async () => { const item = await riskFlow.recover(currentCase.value!); if (alive) { currentCase.value = item; flowMessage.value = '中断状态已恢复，未自动重试模型请求' }; await refreshFlow() })
}
async function draftKnowledge() {
  if (!currentCase.value) return
  await flowAction(async () => {
    await riskFlow.draft(currentCase.value!, { ...knowledgeDraft.value })
    const item = await riskFlow.get(currentCase.value!.id)
    if (alive) { currentCase.value = item; flowMessage.value = '知识草稿已保存，尚未发布' }
    await refreshFlow()
  })
}
async function publishKnowledge(item: RiskKnowledge) {
  await flowAction(async () => { await riskFlow.publish(item); if (alive) flowMessage.value = '知识已发布，后续匹配时可被检索'; await refreshFlow() })
}
async function loadCandidates(before?: string) {
  const request = ++candidateRequest
  const first = startDate.value || ''
  const last = endDate.value || ''
  loading.value = true
  error.value = ''
  candidates.value = undefined
  try {
    const result = await riskCandidates(first, last, before)
    if (request === candidateRequest) { candidates.value = result; queriedDates.value = `${first}/${last}` }
  } catch (failure) {
    if (request === candidateRequest) error.value = failure instanceof Error ? failure.message : '读取失败，请重试'
  } finally { if (request === candidateRequest) loading.value = false }
}
async function openOrder(value: string, forcedType?: 'auto' | 'id' | 'orderNo') {
  if (reading.value) return
  const mode = forcedType || identifierMode.value
  if (!(mode === 'id' ? /^[1-9][0-9]{0,18}$/ : /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/).test(value.trim())) { evidenceError.value = '请输入与所选类型一致的ERP内部ID或订单号'; return }
  identifierMode.value = mode
  const request = ++evidenceRequest
  identifier.value = value.trim()
  reading.value = true
  evidenceError.value = ''
  evidence.value = undefined
  try {
    const result = await riskEvidence(identifier.value, [...sections.value], mode)
    if (request === evidenceRequest) evidence.value = result
  } catch (failure) {
    if (request === evidenceRequest) evidenceError.value = failure instanceof Error ? failure.message : '证据读取失败，请重试'
  } finally { if (request === evidenceRequest) reading.value = false }
}
</script>

<style scoped>
.risk-verification { display: grid; gap: 16px; }
.verification-fields { display: flex; align-items: end; flex-wrap: wrap; gap: 16px; margin-bottom: 16px; }
.verification-fields label { display: grid; gap: 8px; min-width: 180px; }
.scope-panel { min-width: 0; padding: 20px; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; }
.scope-panel > .ant-alert { margin: 12px 0; }
h2 { margin-top: 0; font-size: 18px; }
.muted { color: #64748b; }
details { border-top: 1px solid #e2e8f0; padding: 12px 0; }
summary { cursor: pointer; overflow-wrap: anywhere; }
pre { max-height: 360px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; background: #f2f5f9; padding: 12px; }
.case-select { width: 100%; max-width: 720px; }
.text-field { display: grid; gap: 8px; margin: 12px 0; }
</style>
