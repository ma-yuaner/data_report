<template>
  <div class="operations-desk">
    <div class="section-heading">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <div class="toolbar">
        <button v-if="actor === 'coordinator'" class="primary" @click="emit('create')">新建 ADM</button
        ><button v-if="suggestedRole && actor !== suggestedRole" @click="emit('role', suggestedRole)">
          切换{{ roleName(suggestedRole) }}
        </button>
      </div>
    </div>
    <template v-if="page === 'notifications'">
      <div class="toolbar">
        <button @click="generateWarnings">生成到期提醒</button><button @click="markAll">全部标已读</button
        ><span>{{ inbox.filter((item) => !item.read).length }} 条未读</span>
      </div>
      <article v-for="item in inbox" :key="item.id" class="inbox-row">
        <div>
          <strong>{{ item.read ? '已读' : '未读' }} · {{ item.text }}</strong>
          <p>接收人：{{ roleName(item.recipient) }} · {{ state.cases.find((c) => c.id === item.caseId)?.admNo }}</p>
          <p v-if="receipts[item.id]">外部回执：{{ receipts[item.id] }}</p>
        </div>
        <div class="toolbar">
          <button @click="emit('notice', item)">打开对应任务</button
          ><button @click="receipt(item.id)">登记收到回执</button>
        </div>
      </article>
      <p v-if="!inbox.length" class="empty">本人暂无通知；生成提醒只针对已设置期限的获权任务。</p>
    </template>
    <template v-else-if="page === 'settings'">
      <p class="callout">这里是ADM专属业务规则和本机演示参数，不是独立的系统设置中心。正式账号及权限复用“系统管理→账号管理”；通知配置/日志优先适配“监控中心→通知管理”；导出使用全局导出任务。当前不连接这些正式能力。</p>
      <p>配置必要性：分派条件、具体错误类型与外部差异代码属于ADM业务规则；账号、公共渠道和汇率主数据不在ADM里重复建设。以下人员与汇率仅用于演示，正式来源需要对接确认。</p>
      <fieldset :disabled="actor !== 'coordinator'">
        <h2>任务分派与提醒</h2>
        <FormGrid>
          <label>新建默认组长<AccountSelect v-model="rules.lead" :options="people" /></label>
          <label>平台A负责人<AccountSelect v-model="rules.platformA" :options="people" /></label
          ><label>平台B负责人<AccountSelect v-model="rules.platformB" :options="people" /></label>
          <label>到期前预警小时<a-input-number v-model:value="rules.warningHours" :min="1" :max="168" /></label>
          <label
            >正式任务模拟渠道<a-select
              v-model:value="rules.channel"
              :options="['企业微信', '邮件', '站内'].map((value) => ({ value }))"
          /></label>
        </FormGrid>
        <h2>具体错误类型与差异代码</h2>
        <div v-for="(item, index) in rules.types" :key="index" class="config-row">
          <a-input v-model:value="item.name" placeholder="具体类型" /><a-input
            v-model:value="item.code"
            placeholder="外部代码；未提供可留空"
          />
        </div>
        <button @click="rules.types.push({ name: '', code: '' })">添加类型</button>
        <h2>供应商默认值</h2>
        <div v-for="(item, index) in rules.suppliers" :key="index" class="config-row">
          <a-input v-model:value="item.name" placeholder="供应商" /><a-select
            v-model:value="item.currency"
            :options="currencies"
          /><a-input v-model:value="item.rate" placeholder="参考汇率" />
        </div>
        <button @click="rules.suppliers.push({ name: '', currency: 'CNY', rate: '' })">添加供应商</button>
        <h2>本地参考汇率（1原币＝多少人民币）</h2>
        <div v-for="item in rules.rates" :key="item.currency" class="config-row">
          <span>{{ item.currency }}</span
          ><a-input v-model:value="item.rate" />
        </div>
        <p class="muted">此处为手工参考值，保存时记录演练时间；不能作为财务结算。</p>
        <button class="primary" @click="saveRules">保存本机规则</button>
      </fieldset>
    </template>
    <template v-else-if="page === 'exchange'">
      <div class="case-tabs">
        <button
          v-for="tab in ['统一CSV导入', '历史档案试导']"
          :key="tab"
          :class="{ active: exchangeTab === tab }"
          @click="changeExchangeTab(tab)"
        >
          {{ tab }}
        </button>
      </div>
      <template v-if="exchangeTab === '统一CSV导入'">
        <p>同供应商、同ADM号的多行合为一张主单，每行一个订单。先预览全部错误，再统一确认。</p>
        <div class="toolbar">
          <button @click="download('ADM统一模板.csv', templateCsv(), 'text/csv')">下载统一模板</button
          ><button
            @click="fillImportExample"
          >
            填入演示样例</button
          ><label class="file-button">选择CSV<input type="file" accept=".csv,text/csv" @change="loadCsv" /></label>
        </div>
        <label>CSV正文<a-textarea v-model:value="csv" :rows="8" @change="plan = null" /></label>
        <FormGrid
          ><label
            >导入方式<a-select
              v-model:value="importMode"
              :options="[
                { value: 'new', label: '仅新增，重复报错' },
                { value: 'update', label: '更新已有基础信息（保留办理结果）' },
              ]"
              @change="plan = null" /></label
          ><label
            ><a-checkbox v-model:checked="overwrite" @change="plan = null"
              >更新时覆盖已有备注（默认保留）</a-checkbox
            ></label
          ></FormGrid
        >
        <div class="toolbar">
          <button :disabled="actor !== 'coordinator'" @click="previewImport">预览校验</button
          ><button
            class="primary"
            :disabled="!plan || !!plan.errors.length || actor !== 'coordinator'"
            @click="confirmImport"
          >
            确认导入 {{ plan?.cases.length || 0 }} 张ADM
          </button>
        </div>
        <div v-if="plan" class="callout">
          <p>{{ plan.rows }} 行，{{ plan.cases.length }} 张通过，{{ plan.errors.length }} 项错误。确认前不改变台账。</p>
          <p v-for="error in plan.errors" :key="error" class="danger-text">{{ error }}</p>
          <p v-for="item in plan.cases" :key="item.id">
            {{ item.admNo }} · {{ item.supplier }} · {{ item.lines.length }} 个订单 · {{ item.amount }}
            {{ item.currency }}
          </p>
        </div>
      </template>
      <template v-else>
        <p>
          使用原型约定的JSON档案数组试导；导入后只读，不生成待办，不继承旧锁和财务确认。真实旧系统字段映射及附件迁移仍需正式开发。
        </p>
        <div class="toolbar">
          <button
            @click="fillHistoryExample"
          >
            填入历史样例</button
          ><label class="file-button">选择JSON<input type="file" accept=".json" @change="loadHistory" /></label>
        </div>
        <a-textarea v-model:value="historyText" :rows="8" @change="historyPlan = []" />
        <div class="toolbar">
          <button @click="previewHistory">预览历史档案</button
          ><button class="primary" :disabled="!historyPlan.length || actor !== 'coordinator'" @click="importHistory">
            确认试导为只读档案
          </button>
        </div>
        <p v-for="item in historyPlan" :key="item.id">
          {{ item.admNo }} · {{ item.lines.length }} 个子项 · {{ item.amount }}
        </p>
      </template>
    </template>
    <template v-else>
      <div class="desk-filters">
        <label>搜索<a-input v-model:value="query" placeholder="ADM / 订单 / 票号 / PNR / 内容 / 备注" /></label
        ><label
          >阶段<a-select
            v-model:value="status"
            :options="[
              { value: '', label: '全部阶段' },
              ...Object.entries(stageNames).map(([value, label]) => ({ value, label })),
            ]" /></label
        ><label
          >平台<a-select
            v-model:value="platform"
            :options="[{ value: '', label: '全部平台' }, { value: '平台A' }, { value: '平台B' }]" /></label
        ><label>日期（下发日）<DateField v-model="issuedFrom" /></label
        ><label>截止<DateField v-model="issuedTo" /></label><button @click="resetFilters">清空</button>
      </div>
      <div class="metrics">
        <article>
          <strong>{{ filtered.length }}</strong
          ><span>当前范围主单</span>
        </article>
        <article>
          <strong>{{ lineRows.length }}</strong
          ><span>当前范围明细</span>
        </article>
        <article>
          <strong>{{
            lineRows.filter((row) => row.line.dueAt && row.line.dueAt < state.clock && row.line.stage !== 'DONE').length
          }}</strong
          ><span>超过明细期限</span>
        </article>
      </div>
      <template v-if="page === 'report'">
        <h2>工作量与积压（当前快照）</h2>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>人员</th>
                <th>未完任务</th>
                <th>超期任务</th>
                <th>等待跟进</th>
                <th>恢复编码</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in workload" :key="item.id">
                <td>{{ roleName(item.id) }}</td>
                <td>{{ item.tasks.length }}</td>
                <td>{{ item.tasks.filter((task) => task.overdue).length }}</td>
                <td>{{ item.tasks.filter((task) => task.kind === '跟进').length }}</td>
                <td>{{ item.tasks.filter((task) => task.kind === '恢复编码').length }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>原币金额：{{ currencyTotals }}。按未完任务数排序，仅用于督办；不生成正式绩效分数。</p>
        <button @click="buildDaily">生成可读日报</button>
        <div v-if="daily" class="callout">
          <pre>{{ daily }}</pre>
          <button @click="download('ADM日报.txt', daily)">下载日报</button>
        </div>
      </template>
      <div class="toolbar">
        <span>已选 {{ selected.length }} 张</span><button @click="exportSelected(false)">导出台账CSV</button
        ><button @click="exportSelected(true)">导出差异交接CSV</button
        ><button v-if="actor === 'coordinator'" @click="emit('navigate', 'exchange')">导入 / 历史试导</button>
      </div>
      <details v-if="actor === 'coordinator'">
        <summary>批量分派与办理锁</summary>
        <FormGrid
          ><label>目标承办<AccountSelect v-model="batchOwner" :options="people" /></label
          ><label>操作依据<a-input v-model:value="batchReason" /></label
        ></FormGrid>
        <div class="toolbar">
          <button @click="runBatch('assign')">批量分派所选明细</button
          ><button @click="runBatch('unlock')">批量解锁</button>
        </div>
        <p v-for="result in batchResults" :key="result">{{ result }}</p>
      </details>
      <div class="table-scroll desk-table">
        <table>
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  aria-label="选择当前结果"
                  :checked="!!filtered.length && filtered.every((item) => selected.includes(item.id))"
                  @change="selectAll(($event.target as HTMLInputElement).checked)"
                />
              </th>
              <th>ADM / 供应方</th>
              <th>订单 / 票号</th>
              <th>平台 / 业务</th>
              <th>阶段 / 负责人</th>
              <th>金额 / 币种</th>
              <th>
                {{
                  page === 'financeQueue'
                    ? '应收 / 已收 / 剩余'
                    : page === 'recovery'
                      ? '恢复编码 / 期限'
                      : '内容与备注'
                }}
              </th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in lineRows" :key="`${row.item.id}:${row.line.id}`">
              <td>
                <input
                  type="checkbox"
                  :checked="selected.includes(row.item.id)"
                  aria-label="选择此ADM"
                  @change="toggleSelect(row.item.id)"
                />
              </td>
              <td>
                <strong>{{ row.item.admNo }}</strong
                ><small
                  >{{ row.item.preliminary ? '预罚核实' : row.item.historyOnly ? '历史只读' : caseStatus(row.item) }} ·
                  {{ row.item.supplier }}</small
                >
              </td>
              <td>
                {{ row.line.orderNo || '未关联订单'
                }}<small>{{ row.line.ticketNo || '无票号' }} · {{ row.line.pnr }}</small>
              </td>
              <td>
                {{ row.line.platform }}<small>{{ row.line.business }} · {{ row.line.site }}</small>
              </td>
              <td>
                {{ stageNames[row.line.stage]
                }}<small>{{ roleName(row.line.owner) }}{{ row.line.lockedBy ? ' · 已锁' : '' }}</small>
              </td>
              <td class="money">{{ row.line.amount }} {{ row.item.currency || 'CNY' }}</td>
              <td>
                <template v-if="page === 'financeQueue'"
                  >{{ row.line.expectedRefund || row.line.amount }} / {{ row.line.settledAmount || '0.00' }} /
                  {{ remaining(row.line) }}</template
                ><template v-else-if="page === 'recovery'"
                  >{{ row.line.recoveryCode || '待补'
                  }}<small
                    >{{ row.line.recoveryResult || '未完成' }} · {{ row.line.recoveryDue || '未设期限' }}</small
                  ></template
                ><template v-else
                  ><span class="clamp-text">{{ row.item.description }}</span
                  ><small class="clamp-text">{{
                    row.line.remark || (actor === 'coordinator' ? row.item.remark : '') || '无备注'
                  }}</small></template
                >
              </td>
              <td>
                <button class="primary" @click="emit('open', row.item.id, row.line.id, nodeFor(row.line))">
                  {{ row.item.historyOnly ? '查看档案' : '打开办理' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!lineRows.length" class="empty">当前人员和筛选条件下没有记录。可调整筛选或切换对应岗位。</p>
    </template>
    <p v-if="feedback" class="callout" role="status">{{ feedback }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import FormGrid from '../../src/components/FormGrid.vue'
import AccountSelect from '../../src/components/AccountSelect.vue'
import DateField from '../../src/components/DateField.vue'
import {
  roles,
  roleName,
  visibleLines,
  tasks,
  stageNames,
  stageNode,
  cents,
  cash,
  id,
  type SimState,
  type Case,
  type Line,
} from './model'
import {
  defaultRules,
  workspaceSeed,
  templateCsv,
  previewCsv,
  applyCsv,
  exportCases,
  batchAction,
  recordWorkspace,
} from './workspace'
const props = defineProps<{ state: SimState; actor: string; page: string }>()
const emit = defineEmits<{
  update: [state: SimState]
  open: [caseId: string, lineId: string, node?: string]
  create: []
  role: [actor: string]
  notice: [item: SimState['notices'][number]]
  navigate: [page: string]
}>()
const titles: Record<string, string> = {
  ledger: 'ADM台账',
  recovery: '恢复编码',
  appeals: '申诉跟进',
  reviewQueue: '审核工作台',
  financeQueue: '回款工作台',
  exchange: '导入导出与历史接管',
  notifications: '通知与接收回执',
  settings: 'ADM业务规则与演示参数',
  report: '统计与日报',
  history: '历史档案',
}
const title = computed(() => titles[props.page] || 'ADM工作区')
const description = computed(
  () =>
    (
      ({
        ledger: '围绕同一张ADM连续办理，主单、订单、证据和处理记录集中查看。',
        recovery: '集中跟踪编码恢复，打开原单填写结果，完成后继续办理。',
        financeQueue: '业务结案后仍保留回款待办，支持部分到账和多次核对。',
        reviewQueue: '核对同单处理意见与证据，通过或退回原承办。',
        appeals: '按对象和轮次保留申诉，继续跟进未终结事项。',
      }) as Record<string, string>
    )[props.page] || '本地前端原型，记录在同一工作区保存，可随时继续办理。',
)
const suggestedRole = computed(
  () =>
    (
      ({
        reviewQueue: 'reviewer',
        financeQueue: 'finance',
        settings: 'coordinator',
        exchange: 'coordinator',
        history: 'coordinator',
      }) as Record<string, string>
    )[props.page],
)
const query = ref(''),
  status = ref(''),
  platform = ref(''),
  issuedFrom = ref(''),
  issuedTo = ref(''),
  selected = ref<string[]>([]),
  feedback = ref('')
const people = roles.filter((role) => ['lead', 'handlerA', 'handlerB'].includes(role.id)),
  currencies = ['CNY', 'HKD', 'USD', 'EUR', 'JPY'].map((value) => ({ value }))
const rules = ref(defaultRules()),
  batchOwner = ref('handlerA'),
  batchReason = ref(''),
  batchResults = ref<string[]>([])
watch(
  () => props.state.rules,
  (value) => {
    rules.value = JSON.parse(JSON.stringify(value || defaultRules()))
  },
  { immediate: true },
)
watch(
  () => props.page,
  () => {
    resetFilters()
    selected.value = []
    feedback.value = ''
  },
)
const scope = (item: Case) => visibleLines(item, props.actor)
const lineMatches = (item: Case, line: Line) => {
  if (status.value && line.stage !== status.value) return false
  if (platform.value && line.platform !== platform.value) return false
  if (
    query.value &&
    !JSON.stringify([
      item.admNo,
      item.supplier,
      item.description,
      props.actor === 'coordinator' ? item.remark : '',
      line,
    ])
      .toLowerCase()
      .includes(query.value.toLowerCase())
  )
    return false
  if (props.page === 'recovery') return line.recoveryRequired
  if (props.page === 'appeals') return line.stage === 'APPEAL' || line.appeals.length > 0
  if (props.page === 'reviewQueue') return line.stage === 'REVIEW'
  if (props.page === 'financeQueue') return line.financeRequired && line.stage === 'DONE'
  return true
}
const filtered = computed(() =>
  props.state.cases.filter(
    (item) =>
      (props.page === 'history' ? item.historyOnly : !item.historyOnly) &&
      (!issuedFrom.value || (!!item.issuedOn && item.issuedOn >= issuedFrom.value)) &&
      (!issuedTo.value || (!!item.issuedOn && item.issuedOn <= issuedTo.value)) &&
      scope(item).some((line) => lineMatches(item, line)),
  ),
)
const lineRows = computed(() =>
  filtered.value.flatMap((item) =>
    scope(item)
      .filter((line) => lineMatches(item, line))
      .map((line) => ({ item, line })),
  ),
)
const nodeFor = (line: Line) =>
  props.page === 'recovery' ? 'recovery' : props.page === 'financeQueue' ? 'finance' : stageNode[line.stage]
const caseStatus = (item: Case) =>
  item.paused ? '已挂起' : { ACTIVE: '办理中', CLOSED: '已结案', VOID: '已作废', DRAFT: '草稿' }[item.status]
const remaining = (line: Line) =>
  cash(Math.max(0, cents(line.expectedRefund || line.amount) - cents(line.settledAmount || '0')))
const inbox = computed(() =>
  props.state.notices
    .filter((item) => item.recipient === props.actor)
    .slice()
    .reverse(),
)
const receipts = ref<Record<string, string>>({})
function resetFilters() {
  query.value = ''
  status.value = ''
  platform.value = ''
  issuedFrom.value = ''
  issuedTo.value = ''
}
function toggleSelect(key: string) {
  selected.value = selected.value.includes(key) ? selected.value.filter((id) => id !== key) : [...selected.value, key]
}
function selectAll(yes: boolean) {
  selected.value = yes ? filtered.value.map((item) => item.id) : []
}
function download(name: string, text: string, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob(['\uFEFF', text], { type: `${type};charset=utf-8` }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function exportSelected(difference: boolean) {
  const list = filtered.value.filter((item) => !selected.value.length || selected.value.includes(item.id))
  download(
    difference ? 'ADM差异交接.csv' : 'ADM台账.csv',
    exportCases(
      list,
      props.actor,
      (item) => scope(item).filter((line) => lineMatches(item, line)),
      difference,
      props.state.rules?.types,
    ),
    'text/csv',
  )
  feedback.value = `已导出${list.length}张当前范围ADM；差异导出不表示外部系统已登记。`
}
function runBatch(action: string) {
  try {
    if (!selected.value.length) throw Error('请先勾选ADM')
    const result = batchAction(props.state, props.actor, selected.value, action, batchOwner.value, batchReason.value)
    emit('update', result.state)
    batchResults.value = result.results
  } catch (e) {
    feedback.value = (e as Error).message
  }
}
function saveRules() {
  try {
    if (props.actor !== 'coordinator') throw Error('仅协调人可保存规则')
    if (
      !rules.value.types.length ||
      rules.value.types.some((item) => !item.name.trim()) ||
      new Set(rules.value.types.map((item) => item.name.trim())).size !== rules.value.types.length
    )
      throw Error('错误类型不能为空或重复')
    for (const item of [...rules.value.rates, ...rules.value.suppliers])
      if (item.rate && (!/^\d{1,5}(\.\d{1,6})?$/.test(item.rate) || Number(item.rate) <= 0))
        throw Error('参考汇率应为正数、最多6位小数')
    const next: SimState = JSON.parse(JSON.stringify(props.state))
    next.rules = JSON.parse(JSON.stringify(rules.value))
    recordWorkspace(next, props.actor, '', 'settings', '本机规则保存；不重派历史任务')
    emit('update', next)
    feedback.value = '已保存本机规则。新建与后续匹配生效。'
  } catch (e) {
    feedback.value = (e as Error).message
  }
}
function markAll() {
  const next: SimState = JSON.parse(JSON.stringify(props.state))
  next.notices.filter((item) => item.recipient === props.actor).forEach((item) => (item.read = true))
  emit('update', next)
}
function receipt(key: string) {
  const value = prompt('填写外部“收到”回执的时间、渠道及核对说明；此动作不代替接单。')
  if (!value?.trim()) return
  const next: SimState = JSON.parse(JSON.stringify(props.state))
  const note = next.notices.find((item) => item.id === key && item.recipient === props.actor)
  if (!note) return
  recordWorkspace(next, props.actor, note.caseId, 'receipt', value, note.lineId)
  note.text += `；回执：${value}`
  emit('update', next)
}
function generateWarnings() {
  const next: SimState = JSON.parse(JSON.stringify(props.state))
  let count = 0
  const range = new Date(`${next.clock}:00+08:00`).getTime() + (next.rules?.warningHours || 24) * 3600000
  for (const task of tasks(next).filter(
    (task) => task.owner === props.actor && task.dueAt && new Date(`${task.dueAt}:00+08:00`).getTime() <= range,
  )) {
    const text = `[${next.rules?.channel || '站内'}本地提醒] ${task.title} · 截止${task.dueAt}`
    if (
      !next.notices.some(
        (item) =>
          item.recipient === props.actor &&
          item.caseId === task.caseId &&
          item.lineId === task.lineId &&
          item.text === text,
      )
    ) {
      next.notices.push({
        id: id(),
        recipient: props.actor,
        caseId: task.caseId,
        lineId: task.lineId,
        text,
        read: false,
      })
      count++
    }
  }
  emit('update', next)
  feedback.value = `生成${count}条本地提醒，未对外发送。`
}
const exchangeTab = ref('统一CSV导入'),
  csv = ref(''),
  importMode = ref('new'),
  overwrite = ref(false),
  plan = ref<ReturnType<typeof previewCsv> | null>(null)
function changeExchangeTab(value: string) { exchangeTab.value=value; plan.value=null }
function fillImportExample() { csv.value=templateCsv(); plan.value=null }
function fillHistoryExample() {
  historyText.value=JSON.stringify([{...workspaceSeed().cases[0],id:'legacy-sample-1',admNo:'HISTORY-DEMO-001',source:'历史合成样例'}],null,2)
  historyPlan.value=[]
}
async function loadCsv(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) {
    if (file.size > 1024 * 1024) {
      feedback.value = 'CSV最多1MB'
      return
    }
    csv.value = await file.text()
    plan.value = null
  }
}
function previewImport() {
  try {
    plan.value = previewCsv(csv.value, props.state, importMode.value)
    feedback.value = '预览已更新，未写入台账。'
  } catch (e) {
    plan.value = null
    feedback.value = (e as Error).message
  }
}
function confirmImport() {
  try {
    if (!plan.value || plan.value.errors.length) throw Error('请先完成预览')
    const next = applyCsv(props.state, props.actor, csv.value, importMode.value, overwrite.value)
    emit('update', next)
    plan.value = null
    feedback.value = '已导入本机台账，新建项生成组长接收任务。'
  } catch (e) {
    feedback.value = (e as Error).message
  }
}
const historyText = ref(''),
  historyPlan = ref<Case[]>([])
async function loadHistory(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) {
    if (file.size > 1024 * 1024) {
      feedback.value = 'JSON最多1MB'
      return
    }
    historyText.value = await file.text()
    historyPlan.value = []
  }
}
function previewHistory() {
  try {
    const value = JSON.parse(historyText.value.replace(/^\uFEFF/, ''))
    if (!Array.isArray(value) || !value.length || value.length > 100) throw Error('需要1–100条原型约定的历史档案数组')
    for (const item of value) {
      if (!item?.id || !item.admNo || !item.supplier || !Array.isArray(item.lines) || !item.lines.length)
        throw Error('历史记录须有id、ADM号、供应商及订单明细')
      cents(item.amount)
      for (const line of item.lines) {
        cents(line.amount)
        if (
          !line.id ||
          !stageNames[line.stage as keyof typeof stageNames] ||
          !Array.isArray(line.evidence) ||
          !Array.isArray(line.appeals) ||
          !Array.isArray(line.collaborations)
        )
          throw Error('历史明细格式不完整')
      }
    }
    if (new Set(value.map((item) => item.id)).size !== value.length) throw Error('历史源id重复')
    historyPlan.value = value
    feedback.value = '历史预览完成，尚未写入。'
  } catch (e) {
    historyPlan.value = []
    feedback.value = (e as Error).message
  }
}
function importHistory() {
  try {
    if (props.actor !== 'coordinator') throw Error('仅协调人可导入历史')
    previewHistory()
    if (!historyPlan.value.length) return
    const next: SimState = JSON.parse(JSON.stringify(props.state))
    let count = 0
    for (const source of historyPlan.value) {
      const key = `history-${source.id}`
      if (next.cases.some((item) => item.id === key)) continue
      const item: Case = {
        ...source,
        id: key,
        status: ['ACTIVE', 'CLOSED', 'VOID', 'DRAFT'].includes(source.status) ? source.status : 'DRAFT',
        historyOnly: true,
        historySource: JSON.parse(JSON.stringify(source)),
        paused: false,
        files: [],
        closedSnapshots: [],
        remediation: { owner: '', status: '历史只读', result: '' },
      }
      item.lines = item.lines.map((line) => ({
        ...line,
        lockedBy: '',
        transfer: undefined,
        financeReference: '',
        payments: [],
        settledAmount: '',
        evidence: [],
        collaborations: [],
      }))
      next.cases.push(item)
      recordWorkspace(next, props.actor, key, 'history_import', '本地历史只读试导；未迁移原件和真实财务')
      count++
    }
    emit('update', next)
    historyPlan.value = []
    feedback.value = `已试导${count}张，重复源ID跳过。请到历史档案查看。`
  } catch (e) {
    feedback.value = (e as Error).message
  }
}
const workload = computed(() => {
  const ids = new Set(filtered.value.map((item) => item.id))
  return roles
    .filter((role) => props.actor === 'coordinator' || props.actor === 'lead' || role.id === props.actor)
    .map((role) => ({
      id: role.id,
      tasks: tasks(props.state).filter(
        (task) =>
          task.owner === role.id &&
          ids.has(task.caseId) &&
          (!task.lineId || lineRows.value.some((row) => row.line.id === task.lineId && row.item.id === task.caseId)),
      ),
    }))
    .sort((a, b) => b.tasks.length - a.tasks.length)
})
const currencyTotals = computed(() => {
  const totals: Record<string, number> = {}
  for (const row of lineRows.value) {
    const currency = row.item.currency || 'CNY'
    totals[currency] = (totals[currency] || 0) + cents(row.line.amount)
  }
  return (
    Object.entries(totals)
      .map(([currency, value]) => `${cash(value)} ${currency}`)
      .join('；') || '无数据'
  )
})
const daily = ref('')
function buildDaily() {
  const ids = new Set(filtered.value.map((item) => item.id))
  const events = props.state.events.filter(
    (event) => ids.has(event.caseId) && event.at.slice(0, 10) === props.state.clock.slice(0, 10),
  )
  daily.value = `ADM日报（本地快照）\n截至：${props.state.clock}\n统计范围：${roleName(props.actor)}，${filtered.value.length}张主单 / ${lineRows.value.length}个明细\n原币：${currencyTotals.value}\n当日新建/导入动作：${events.filter((event) => ['publish', 'import'].includes(event.action)).length}\n当日处理动作：${events.length}\n当前待回款明细：${lineRows.value.filter((row) => row.line.stage === 'DONE' && row.line.financeRequired && !row.line.financeReference).length}\n${workload.value.map((item) => `${roleName(item.id)}：未完${item.tasks.length}，超期${item.tasks.filter((task) => task.overdue).length}`).join('\n')}\n口径：任务不是订单；等待未扣时，缺期限不视为达标；无正式绩效或真实群发。`
}
</script>
