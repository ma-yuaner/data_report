<template>
  <a-modal :open="open" title="从解析结果新建 ADM 台账" :width="920" :footer="null" @cancel="$emit('close')">
    <p>查询已解析、校验通过且尚未登记的来件。选择后核对字段、附件和待核对提示，再补充台账信息。</p>
    <a-input-search v-model:value="search" placeholder="搜索 ADM 号、附件名称、航司" enter-button="查询" :loading="loading" @search="query(1)" />
    <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top:12px" />
    <a-table :data-source="items" :loading="loading" row-key="id" :pagination="false" size="small" :scroll="{ x: 740 }" style="margin-top:12px">
      <a-table-column title="ADM 号" key="number"><template #default="{ record }">{{ record.adm.number }}</template></a-table-column>
      <a-table-column title="来件与附件" key="files"><template #default="{ record }">{{ record.files.map((f: { name: string }) => f.name).join('、') }}</template></a-table-column>
      <a-table-column title="航司" key="airline"><template #default="{ record }">{{ record.airlineMatch?.name || record.adm.airlineCode || '待核对' }}</template></a-table-column>
      <a-table-column title="正式金额" key="amount"><template #default="{ record }">{{ record.adm.amount }} {{ record.adm.currency }}</template></a-table-column>
      <a-table-column title="待核对" key="warnings"><template #default="{ record }">{{ record.warningCount }} 项</template></a-table-column>
      <a-table-column title="操作" key="action"><template #default="{ record }"><a-button type="link" :disabled="loading" @click="choose(record.id)">核对并带入</a-button></template></a-table-column>
      <template #emptyText>没有符合条件的待登记来件；请确认解析已通过并保存。</template>
    </a-table>
    <a-pagination :current="page" :total="total" :page-size="20" :show-size-changer="false" style="margin-top:12px" @change="query" />
  </a-modal>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import { parsingApi, type ParseTask } from '../adm-parsing/api'
import { errorText } from './api'
const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; select: [task: ParseTask] }>()
const search = ref(''), page = ref(1), total = ref(0), loading = ref(false), error = ref('')
const items = ref<Awaited<ReturnType<typeof parsingApi.pending>>['items']>([])
let sequence = 0
async function query(next = 1) {
  const request = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await parsingApi.pending(search.value, next)
    if (request !== sequence || !props.open) return
    items.value = result.items
    total.value = result.total
    page.value = next
  } catch (e) {
    if (request === sequence) { error.value = errorText(e); items.value = []; total.value = 0 }
  } finally { if (request === sequence) loading.value = false }
}
async function choose(id: string) {
  loading.value = true
  error.value = ''
  try {
    const task = await parsingApi.detail(id)
    if (!props.open) return
    if (task.registration || task.state !== 'SUCCEEDED') { await query(page.value); return }
    emit('select', task)
  } catch (e) { error.value = errorText(e) }
  finally { loading.value = false }
}
watch(() => props.open, (open) => { ++sequence; if (open) { search.value = ''; void query(1) } })
</script>
