<template>
  <div class="page-wrap">
    <PageHeader eyebrow="ACTION CENTER" title="异常工作台" description="把经营、履约、风险和数据问题转成可跟进的业务清单">
      <a-button type="primary"><PlusOutlined />新建规则</a-button>
    </PageHeader>
    <DataStateBar label="演示数据" message="当前ADM和异常项用于验证工作台结构" freshness="模拟更新时间" metric-state="规则待确认" />

    <a-card class="panel-card" :bordered="false">
      <div class="issue-toolbar">
        <a-segmented v-model:value="category" :options="['全部问题', '经营异常', '履约异常', '风险异常', '数据异常']" />
        <a-space><a-select value="all" style="width: 120px" :options="[{value:'all',label:'全部状态'},{value:'pending',label:'待处理'},{value:'checking',label:'待确认'}]" /><a-input-search placeholder="搜索对象或问题" /></a-space>
      </div>
      <a-table :columns="columns" :data-source="filteredItems" :loading="loading" row-key="id" :pagination="false" :scroll="{ x: 900 }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'level'"><a-tag :color="record.level === 'P0' ? 'error' : 'warning'">{{ record.level }}</a-tag></template>
          <template v-else-if="column.key === 'object'"><a class="table-object">{{ record.object }}</a></template>
          <template v-else-if="column.key === 'status'"><a-badge :status="record.status === '待处理' ? 'error' : 'warning'" :text="record.status" /></template>
          <template v-else-if="column.key === 'action'"><a-button type="link" size="small">查看证据 <RightOutlined /></a-button></template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, RightOutlined } from '@ant-design/icons-vue'
import { getIssues, type IssueItem } from '@/api/dashboard'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'

const loading = ref(true)
const items = ref<IssueItem[]>([])
const category = ref('全部问题')
const columns = [
  { title: '级别', key: 'level', width: 76 }, { title: '类型', dataIndex: 'category', key: 'category', width: 110 },
  { title: '业务对象', key: 'object', width: 170 }, { title: '问题', dataIndex: 'title', key: 'title', width: 260 },
  { title: '影响', dataIndex: 'impact', key: 'impact', width: 160 }, { title: '负责人', dataIndex: 'owner', key: 'owner', width: 130 },
  { title: '状态', key: 'status', width: 110 }, { title: '操作', key: 'action', fixed: 'right' as const, width: 110 },
]

const categoryMap: Record<string, string[]> = { '经营异常': ['经营异常', '口径异常'], '履约异常': ['履约异常'], '风险异常': ['风险异常'], '数据异常': ['数据异常', '口径异常'] }
const filteredItems = computed(() => category.value === '全部问题' ? items.value : items.value.filter(item => categoryMap[category.value]?.includes(item.category)))

onMounted(async () => {
  try { items.value = (await getIssues()).items }
  catch (error) { message.error(error instanceof Error ? error.message : '异常数据加载失败') }
  finally { loading.value = false }
})
</script>

