<template>
  <a-drawer :open="open" title="出票盈亏配置取证" :width="'min(1180px, 100vw)'" @close="$emit('close')">
    <div class="config-panel">
      <div class="config-heading"><div><h2>有效出票盈亏规则</h2><p>先核对适用条件，再按权重选取；历史订单使用出票当时的规则。</p></div><a-tag color="green">仅启用 · 当前有效</a-tag></div>
      <form class="config-filter" @submit.prevent="load">
        <label>平台编码<a-input v-model:value="platform" placeholder="全部平台，可输入 QUNAR" :disabled="loading" allow-clear /></label>
        <a-button type="primary" html-type="submit" :loading="loading">读取配置</a-button>
      </form>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-alert type="info" show-icon message="匹配顺序：权重高的优先；同权重按更新时间、规则ID降序" description="平台留空读取全部；指定平台时包含通用规则。列表是当前配置候选，订单实际命中及历史依据请查看逐票核实详情。" />
      <div class="config-summary"><span>{{ loaded ? `共 ${items.length} 条有效配置` : '尚未读取配置' }}</span><span v-if="loaded">{{ loadedPlatform || '全部平台' }} · {{ loadedAt }}</span></div>
      <a-table :columns="columns" :data-source="items" row-key="id" :loading="loading" size="middle" :scroll="{ x: 1050 }" :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (total: number) => `共 ${total} 条` }" :locale="{ emptyText: loaded ? '该范围没有当前有效的出票盈亏配置' : '请读取配置' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'priority'"><strong>{{ record.weight ?? '无法计算' }}</strong><small class="secondary">{{ record.priorityPosition ? `候选顺序 ${record.priorityPosition}` : '排序依据不足' }}</small></template>
          <template v-else-if="column.key === 'name'"><strong>{{ record.rule_name || '未命名规则' }}</strong><small class="secondary">ID {{ record.id }} · v{{ record.version ?? '未知' }}</small></template>
          <template v-else-if="column.key === 'type'"><a-tag :color="record.rule_type === 'RB01003002' ? 'orange' : 'blue'">{{ typeLabel(record.rule_type) }}</a-tag><small class="secondary">{{ record.rule_type }}</small></template>
          <template v-else-if="column.key === 'scope'"><span>{{ record.ota_code || '通用平台' }}</span><small class="secondary">站点：{{ record.ota_site_code || '不限' }}</small><small class="secondary">航司：{{ record.airline || '不限' }}</small></template>
          <template v-else-if="column.key === 'threshold'"><span v-if="record.rule_type === 'RB01003002'">{{ [1, 2, 3, 4].map(n => `${n}段 ${threshold(record.segmentThresholds?.values, n)}`).join(' / ') }}</span><span v-else>盈利配置，展开查看原值</span></template>
          <template v-else-if="column.key === 'validity'"><span>{{ formatDateTimeDisplay(record.start_time) }}</span><small class="secondary">至 {{ formatDateTimeDisplay(record.end_time) }}</small></template>
        </template>
        <template #expandedRowRender="{ record }">
          <div class="rule-detail">
            <h3>适用条件</h3>
            <dl v-if="record.conditions?.length" class="conditions"><div v-for="condition in record.conditions" :key="condition.field"><dt>{{ condition.label }}</dt><dd>{{ condition.value }}</dd></div></dl>
            <p v-else>{{ record.priorityStatus === 'ready' ? '没有配置附加条件，仍须符合规则类型和有效状态。' : '配置内容无法完整解析，不能确认适用条件。' }}</p>
            <p>权重 {{ record.weight ?? '未知' }} · 计分字段：{{ record.weightFields?.join('、') || '无' }}</p>
            <p>配置更新时间：{{ formatDateTimeDisplay(record.update_time) }}</p>
            <p>配置说明：{{ record.rule_notes || '未填写' }}</p>
            <a-alert v-if="record.contentTruncated || record.priorityStatus !== 'ready'" type="warning" show-icon message="配置内容不完整或不可解析，不能据此确认命中或阈值" />
            <details><summary>查看原始扩展配置</summary><pre>{{ pretty(record.ext_json) }}</pre></details>
          </div>
        </template>
      </a-table>
      <p v-if="notice" class="notice">{{ notice }}</p>
    </div>
  </a-drawer>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, Drawer as ADrawer, Input as AInput, Table as ATable, Tag as ATag } from 'ant-design-vue'
import { riskProblems, type RiskConfigCandidate } from '@/api/riskVerification'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
const props = defineProps<{ open: boolean }>()
defineEmits<{ close: [] }>()
const platform = ref(''), loadedPlatform = ref(''), loadedAt = ref('')
const loading = ref(false), loaded = ref(false), error = ref(''), notice = ref('')
const items = ref<RiskConfigCandidate[]>([])
let alive = true
onBeforeUnmount(() => { alive = false })
watch(() => props.open, value => { if (value && !loaded.value) void load() })
const columns = [
  { title: '权重 / 顺序', key: 'priority', width: 100 }, { title: '规则', key: 'name', width: 200 },
  { title: '规则类型', key: 'type', width: 150 }, { title: '平台 / 航司', key: 'scope', width: 150 },
  { title: '单票亏损阈值（元）', key: 'threshold', width: 260 }, { title: '有效期', key: 'validity', width: 180 },
]
const typeLabel = (type: string) => type === 'RB01003002' ? '出票亏损阈值' : type === 'RB01003001' ? '出票盈利阈值' : '其他盈亏规则'
const threshold = (values: Record<string, string> | undefined, n: number) => values?.[String(n)] ?? '未识别'
function pretty(raw: string | null) { try { return JSON.stringify(JSON.parse(raw || '{}'), null, 2) } catch { return raw || '未配置' } }
async function load() {
  if (loading.value) return
  const requested = platform.value.trim()
  loading.value = true; error.value = ''; items.value = []; loaded.value = false; notice.value = ''
  try {
    const result = await riskProblems.configs(requested, '出票盈亏配置')
    if (!alive) return
    items.value = result.items; notice.value = result.notice; loaded.value = true
    loadedPlatform.value = requested; loadedAt.value = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
  } catch (failure) { if (alive) error.value = failure instanceof Error ? failure.message : '配置读取失败，请重试' }
  finally { if (alive) loading.value = false }
}
</script>
<style scoped>
.config-panel { display: grid; gap: 16px; min-width: 0; }
.config-heading { display: flex; justify-content: space-between; align-items: start; gap: 12px; }
h2, h3, p { margin: 0; }
h2 { font-size: 18px; } h3 { font-size: 14px; }
.config-heading p, .notice, .secondary { color: #69768a; font-size: 12px; }
.config-heading p { margin-top: 8px; line-height: 1.6; }
.config-filter { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }
.config-filter label { display: grid; gap: 6px; width: 280px; max-width: 100%; }
.config-summary { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.secondary { display: block; margin-top: 4px; }
.rule-detail { display: grid; gap: 12px; padding: 8px; overflow-wrap: anywhere; }
.conditions { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin: 0; gap: 12px; }
.conditions div { padding: 8px 12px; border-left: 2px solid #dce3ed; }
dt { font-size: 12px; color: #69768a; } dd { margin: 4px 0 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 320px; overflow: auto; background: #f5f7fa; padding: 12px; }
summary { cursor: pointer; } .notice { line-height: 1.7; }
@media (max-width: 600px) { .config-heading { flex-direction: column; } .config-filter label { width: 100%; } }
</style>
