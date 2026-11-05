<template>
  <section class="problem-tags">
    <h3>问题分类与标签（管理员共享）</h3>
    <p>独立记录人工发现的问题，不修改ERP原亏损原因，不覆盖自动核实结论。</p>
    <a-alert v-if="error" type="error" show-icon :message="error" />
    <a-alert v-if="saved" type="success" show-icon :message="saved" />
    <label><span>问题类型（最多10项）</span><a-select v-model:value="selected" mode="multiple" :options="types.map(item => ({ value: item.id, label: item.name }))" :disabled="working" placeholder="选择问题类型" /></label>
    <div class="type-create"><a-input v-model:value="newName" :maxlength="60" :disabled="working" aria-label="新增问题类型名称" placeholder="新增问题类型名称" /><a-button :loading="working" :disabled="!newName.trim()" @click="createType"><PlusOutlined />新增类型</a-button></div>
    <label><span>备注原因</span><a-textarea v-model:value="reason" :rows="3" :maxlength="2000" :disabled="working" placeholder="填写问题依据或具体差异，保存后对管理员共享" /></label>
    <a-space><a-button type="primary" :loading="working" :disabled="!selected.length || !reason.trim()" @click="save">保存问题标签</a-button><a-button :disabled="working" @click="load">刷新共享记录</a-button></a-space>
    <div v-for="tag in tags" :key="tag.id" class="saved-tag"><a-tag color="red">{{ tag.type_name }}</a-tag><span>{{ tag.reason }}</span><small>登记人ID {{ tag.created_by }} · {{ formatDateTimeDisplay(tag.created_at) }}</small></div>
    <p v-if="loaded && !tags.length">暂无已保存的问题标签。</p>
  </section>
</template>
<script setup lang="ts">
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { riskProblems, type RiskProblemTag, type RiskProblemType } from '@/api/riskVerification'
const props = defineProps<{ orderId: string }>()
const emit = defineEmits<{ 'busy-change': [boolean] }>()
const types = ref<RiskProblemType[]>([]), tags = ref<RiskProblemTag[]>([])
const selected = ref<string[]>([]), newName = ref(''), reason = ref(''), working = ref(false), loaded = ref(false), error = ref(''), saved = ref('')
let alive = true
const hasUnsavedDrafts = computed(() => Boolean(selected.value.length || newName.value.trim() || reason.value.trim()))
defineExpose({ hasUnsavedDrafts })
watch(working, value => emit('busy-change', value))
onBeforeUnmount(() => { alive = false })
onMounted(load)
async function load() {
  if (working.value) return
  working.value = true; error.value = ''
  try { const [items, records] = await Promise.all([riskProblems.types(), riskProblems.tags(props.orderId)]); if (alive) { types.value = items; tags.value = records; loaded.value = true } }
  catch (failure) { if (alive) error.value = failure instanceof Error ? failure.message : '共享标签读取失败' }
  finally { if (alive) working.value = false }
}
async function createType() {
  if (working.value || !newName.value.trim()) return
  working.value = true; error.value = ''; saved.value = ''
  try {
    const item = await riskProblems.createType(newName.value)
    if (!alive) return
    if (!types.value.some(existing => existing.id === item.id)) types.value.push(item)
    if (!selected.value.includes(item.id)) selected.value.push(item.id)
    newName.value = ''; saved.value = '类型已新增（管理员共享），请填写备注并保存问题标签'
  } catch (failure) { if (alive) error.value = failure instanceof Error ? failure.message : '类型新增失败' }
  finally { if (alive) working.value = false }
}
async function save() {
  if (working.value || !selected.value.length || !reason.value.trim()) return
  working.value = true; error.value = ''; saved.value = ''
  try { const records = await riskProblems.saveTags(props.orderId, selected.value, reason.value); if (alive) { tags.value = records; selected.value = []; reason.value = ''; loaded.value = true; saved.value = '问题标签已保存（管理员共享）' } }
  catch (failure) { if (alive) error.value = failure instanceof Error ? failure.message : '标签保存失败，输入已保留' }
  finally { if (alive) working.value = false }
}
</script>
<style scoped>
.problem-tags, label { display: grid; gap: 12px; min-width: 0; }
.problem-tags { padding: 16px; border: 1px solid #e4e9ef; border-radius: 8px; }
.type-create { display: flex; gap: 8px; }.type-create > .ant-input { min-width: 0; flex: 1; }
.saved-tag { padding-block: 8px; border-top: 1px solid #edf0f4; overflow-wrap: anywhere; }
.saved-tag small { display: block; color: #69768a; margin-top: 8px; }
@media(max-width:600px) { .type-create { flex-wrap: wrap; } }
</style>
