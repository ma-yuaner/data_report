<template>
  <a-modal :open="open" title="分组录入订单明细" width="min(1080px, 96vw)" :footer="null"
    :closable="!saving" :keyboard="!saving" :mask-closable="false" wrap-class-name="v05-modal adm-form-modal"
    @cancel="emit('close')">
    <p class="context">{{ detail.case.admNo }} · 主单总金额 {{ detail.case.currency }} {{ detail.case.originalAmount }}</p>
    <p>每行填一条订单，从 Excel 粘贴三列：PNR、原币金额、票号。票号可留空。平台、航司和负责组长按组填写。</p>
    <a-alert v-if="optionsError" type="warning" show-icon :message="optionsError" class="block">
      <template #action><a-button size="small" @click="loadOta">重试</a-button></template>
    </a-alert>
    <a-form layout="vertical" :disabled="saving">
      <div v-for="(group, index) in groups" :key="group.id" class="v05-form-grid adm-grouped-form">
        <h3>第 {{ index + 1 }} 组 · {{ groupRows(group).length }} 条</h3>
        <label>平台<a-select v-model:value="group.otaCode" show-search allow-clear option-filter-prop="label"
          :options="otaOptions" :loading="loadingOta" placeholder="留空表示未选择平台" /></label>
        <label>航司<a-input v-model:value="group.airlineName" :maxlength="100" /></label>
        <label>负责组长<a-select v-model:value="group.leaderId" show-search option-filter-prop="label"
          :options="leaderOptions" /></label>
        <div><a-button v-if="groups.length > 1" @click="groups.splice(index, 1)">移除本组</a-button></div>
        <label v-if="recoveredPnrs.length" class="wide">已恢复 PNR
          <a-space-compact block>
            <a-select v-model:value="group.selectedPnrs" mode="multiple" show-search :max-tag-count="3"
              :options="availablePnrs" placeholder="选择本组 PNR" />
            <a-button :disabled="!group.selectedPnrs.length" @click="addSelectedPnrs(group)">加入本组</a-button>
          </a-space-compact>
        </label>
        <label class="wide">订单明细<a-textarea v-model:value="group.rows" :rows="5"
          placeholder="PNR、原币金额、票号三列，使用 Tab 分隔" /></label>
      </div>
      <a-button class="block" @click="addGroup">添加一组</a-button>
      <template v-if="existing.length">
        <h3>现有明细金额</h3>
        <div class="amount-adjustments">
          <label v-for="line in existing" :key="line.id">{{ line.pnr || line.lineInternalNo }}
            <a-input v-model:value="amounts[line.id]" :readonly="!canChangeAmount(line)"
              :addon-before="detail.case.currency" />
          </label>
        </div>
        <a-form-item label="新增及金额调整说明" required><a-textarea v-model:value="reason" :rows="2" /></a-form-item>
      </template>
    </a-form>
    <p>新增 {{ additions.length }} 条 · {{ detail.case.currency }} 合计 {{ centsText(total) }}</p>
    <a-alert v-if="error" type="error" show-icon :message="error" class="block" />
    <div class="v05-modal-actions">
      <a-button :disabled="saving" @click="emit('close')">取消</a-button>
      <a-button type="primary" :loading="saving" @click="save">保存 {{ additions.length }} 条明细</a-button>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { admApi, admPersonOptions, amountInCents, centsText, errorText, type AdmCaseDetail, type AdmConfig, type AdmLine, type Option } from './api'

const props = defineProps<{ open: boolean; detail: AdmCaseDetail; config: AdmConfig | null; actorId: number }>()
const emit = defineEmits<{ close: []; saved: [detail: AdmCaseDetail] }>()
interface Group {
  id: number
  otaCode?: string
  airlineName: string
  leaderId: number
  rows: string
  selectedPnrs: string[]
}
let nextGroupId = 0
const groups = ref<Group[]>([])
const amounts = ref<Record<number, string>>({})
const reason = ref('')
const error = ref('')
const saving = ref(false)
const ota = ref<Option[]>([])
const loadingOta = ref(false)
const optionsError = ref('')
const existing = computed(() => props.detail.lines.filter(line => line.lineStatus !== 'VOIDED'))
const leaderOptions = computed(() => admPersonOptions(props.config?.people.leader || [], true))
const otaOptions = computed(() => ota.value.map(item => ({ value: item.code, label: `${item.name}（${item.code}）` })))
const recoveredPnrs = computed(() => [...new Set(String(props.detail.case.recoveryLocators || '').split(',')
  .map(locator => locator.trim().split('-').at(-1) || '').filter(Boolean))])
const availablePnrs = computed(() => {
  const included = new Set([
    ...additions.value.map(line => line.pnr.toUpperCase()),
    ...existing.value.map(line => String(line.pnr || '').toUpperCase()),
  ])
  return recoveredPnrs.value.filter(pnr => !included.has(pnr.toUpperCase())).map(pnr => ({ value: pnr, label: pnr }))
})
const canChangeAmount = (line: AdmLine) =>
  Number(line.leaderId) === props.actorId && line.lineStatus === 'PENDING_OPERATOR' && !line.operatorId

function addGroup() {
  groups.value.push({
    id: ++nextGroupId, leaderId: props.actorId, airlineName: props.detail.case.airlineName || '', rows: '', selectedPnrs: [],
  })
}
function groupRows(group: Group) {
  return group.rows.split(/\r?\n/).filter(row => row.trim()).map(row => row.split('\t').map(cell => cell.trim()))
}
function addSelectedPnrs(group: Group) {
  const allowed = new Set(availablePnrs.value.map(item => item.value))
  group.rows = [group.rows.trimEnd(), ...group.selectedPnrs.filter(pnr => allowed.has(pnr))]
    .filter(Boolean).join('\n')
  group.selectedPnrs = []
}
const additions = computed(() => groups.value.flatMap(group => groupRows(group).map(cells => ({
  cells, pnr: cells[0], originalAmount: cells[1] || '', ticketNo: cells[2] || '',
  otaCode: group.otaCode, airlineName: group.airlineName, leaderId: group.leaderId,
}))))
const total = computed(() => additions.value.reduce((sum, row) => sum + (amountInCents(row.originalAmount) ?? 0n), 0n)
  + existing.value.reduce((sum, line) => sum + (amountInCents(amounts.value[line.id]) ?? 0n), 0n))
async function loadOta() {
  if (loadingOta.value) return
  optionsError.value = ''
  loadingOta.value = true
  try {
    ota.value = await admApi.options('ota', '', 200)
  } catch (e) {
    optionsError.value = `平台读取失败：${errorText(e)}`
  } finally {
    loadingOta.value = false
  }
}
watch(() => props.open, (open) => {
  if (!open) return
  groups.value = []
  addGroup()
  amounts.value = Object.fromEntries(existing.value.map(line => [line.id, String(line.originalAmount)]))
  reason.value = ''
  error.value = ''
  if (!ota.value.length) void loadOta()
})
async function save() {
  if (saving.value) return
  error.value = ''
  if (!additions.value.length || additions.value.length > 200) {
    error.value = '每次可录入 1 至 200 条订单明细'
    return
  }
  const invalid = additions.value.findIndex(row => !row.pnr || !row.leaderId || row.cells.length > 3 ||
    (amountInCents(row.originalAmount) ?? 0n) <= 0n)
  if (invalid >= 0) {
    error.value = `第 ${invalid + 1} 条明细需要 PNR、有效原币金额和负责组长。请使用 Tab 分隔列。`
    return
  }
  if (existing.value.some(line => (amountInCents(amounts.value[line.id]) ?? 0n) <= 0n) ||
      total.value !== amountInCents(props.detail.case.originalAmount)) {
    error.value = '全部有效明细金额必须大于零，合计须等于主单总金额。'
    return
  }
  if (existing.value.length && !reason.value.trim()) {
    error.value = '请填写新增及金额调整说明'
    return
  }
  saving.value = true
  try {
    const detail = await admApi.addLine(props.detail.case.id, {
      caseVersion: props.detail.case.versionNo,
      lines: additions.value.map(({ cells, ...line }) => line),
      existingAmounts: existing.value.map(line => ({ lineId: line.id, originalAmount: amounts.value[line.id] })),
      reason: reason.value,
    })
    void message.success(`已保存 ${additions.value.length} 条订单明细`)
    emit('saved', detail)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    saving.value = false
  }
}
</script>
