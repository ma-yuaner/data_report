<template>
  <a-spin :spinning="busy">
    <div class="auto-detail">
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-alert v-if="reason !== 'RLA013'" type="info" show-icon message="该类型规则尚未接入" description="后续为此类型补充专属证据和规则，不套用佣金亏损公式。" />
      <a-alert v-else-if="!result" type="info" show-icon message="尚未形成自动结果" description="系统正在核实或等待当前批次完成。关闭详情后可查看进度。" />
      <template v-if="result && reason === 'RLA013'">
        <a-alert :type="outdated ? 'warning' : result.status === 'supported' ? 'success' : result.status === 'problem' || result.status === 'failed' ? 'error' : 'warning'" show-icon :message="outdated ? '源版本已改变，此结果仅供历史参考' : result.summary" />
        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="平台">{{ result.platform || '证据缺失' }}</a-descriptions-item>
          <a-descriptions-item label="日志止损值">{{ result.stopLoss ?? '证据缺失' }} 元</a-descriptions-item>
          <a-descriptions-item label="核实时间">{{ result.checkedAt }}</a-descriptions-item>
          <a-descriptions-item label="规则版本">{{ result.ruleVersion }}</a-descriptions-item>
          <a-descriptions-item label="核实依据" :span="2">出票利润＋销售佣金 ≥ －日志止损值；去哪儿且有正佣金；金额为CNY。</a-descriptions-item>
        </a-descriptions>
        <a-table :data-source="result.tickets" :columns="columns" row-key="id" :pagination="false" :scroll="{ x: 860 }" size="small">
          <template #bodyCell="{ column, record }">
            <a-tag v-if="column.key === 'status'" :color="record.status === 'supported' ? 'green' : record.status === 'problem' ? 'red' : 'orange'">{{ labels[record.status] || record.status }}</a-tag>
          </template>
        </a-table>
        <a-alert v-if="result.missing?.length" type="warning" show-icon :message="`待补证据：${result.missing.join('；')}`" />
        <p class="muted">来源：出票明细的出票利润与销售佣金；止损值取该订单金额自洽且一致的日志，不按日志条数配票。{{ result.logReferences?.length || 0 }} 条日志引用留痕。</p>
        <section v-if="!outdated">
          <h3>人工抽查（可选）</h3>
          <a-radio-group v-model:value="sampleOutcome"><a-radio value="confirmed">确认无误</a-radio><a-radio value="disputed">发现问题</a-radio></a-radio-group>
          <a-textarea v-model:value="sampleReason" :rows="3" :maxlength="2000" placeholder="抽查说明，例如证据与原单一致，或发现的具体差异" />
          <a-button type="primary" :loading="busy" :disabled="!sampleReason.trim()" @click="saveSample">保存抽查</a-button>
          <p>抽查独立留痕，不覆盖自动计算结果。{{ saved }}</p>
          <p v-for="item in result.samples || []" :key="item.id">{{ item.at }} · {{ item.outcome === 'confirmed' ? '确认无误' : '发现问题' }} · {{ item.reason }}</p>
        </section>
      </template>
    </div>
  </a-spin>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, Descriptions as ADescriptions, DescriptionsItem as ADescriptionsItem, Input as AInput, Radio as ARadio, RadioGroup as ARadioGroup, Spin as ASpin, Table as ATable, Tag as ATag } from 'ant-design-vue'
import { riskAutomatic, type AutoRiskResult } from '@/api/riskVerification'
const ATextarea = AInput.TextArea
const props = defineProps<{ orderId: string; reason: string; sourceUpdatedAt: string | null }>()
const emit = defineEmits<{ changed: []; 'busy-change': [boolean] }>()
const result = ref<AutoRiskResult | null>(null)
const busy = ref(false)
const error = ref('')
const saved = ref('')
const sampleOutcome = ref('confirmed')
const sampleReason = ref('')
const labels: Record<string, string> = { supported: '核实通过', problem: '有问题', insufficient: '证据不足', failed: '执行失败', rule_pending: '规则未接入' }
const columns = [{ title: '出票明细ID', dataIndex: 'id', width: 150 }, { title: '出票利润', dataIndex: 'profit', width: 100 }, { title: '销售佣金', dataIndex: 'commission', width: 100 }, { title: '调整后利润', dataIndex: 'adjustedProfit', width: 110 }, { title: '结果', key: 'status', width: 110 }, { title: '计算及原因', dataIndex: 'explanation', width: 300 }]
const normalize = (value: string | null) => value?.replace(' ', 'T') || null
const outdated = computed(() => Boolean(result.value && (normalize(result.value.sourceUpdatedAt) !== normalize(props.sourceUpdatedAt) || result.value.reasonCode !== props.reason)))
const hasUnsavedDrafts = computed(() => Boolean(sampleReason.value.trim()))
defineExpose({ hasUnsavedDrafts, reload: load })
watch(busy, value => emit('busy-change', value))
onMounted(load)
async function load() {
  busy.value = true; error.value = ''; result.value = null
  try { result.value = await riskAutomatic.result(props.orderId) }
  catch (failure) { error.value = failure instanceof Error ? failure.message : '核实结果读取失败' }
  finally { busy.value = false }
}
async function saveSample() {
  if (busy.value || !result.value || outdated.value) return
  busy.value = true; error.value = ''
  try {
    await riskAutomatic.sample(props.orderId, result.value.id, sampleOutcome.value, sampleReason.value)
    sampleReason.value = ''; saved.value = '已保存'; emit('changed'); result.value = await riskAutomatic.result(props.orderId)
  } catch (failure) { error.value = failure instanceof Error ? failure.message : '抽查保存失败' }
  finally { busy.value = false }
}
</script>
<style scoped>
.auto-detail, section { display: grid; gap: 16px; }
.muted { color: #69768a; font-size: 13px; }
h3 { margin-bottom: 0; }
</style>
