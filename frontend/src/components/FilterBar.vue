<template>
  <div class="filter-bar">
    <a-space wrap :size="10">
      <a-select v-model:value="period" class="filter-select" aria-label="统计周期" :options="periodOptions" />
      <a-select v-model:value="profitStage" class="filter-select wide" aria-label="利润阶段" :options="profitOptions" />
      <a-select v-model:value="platform" class="filter-select" aria-label="销售平台" :options="platformOptions" />
      <a-select v-model:value="airline" class="filter-select" aria-label="航司" :options="airlineOptions" />
      <a-button type="primary"><SearchOutlined />查询</a-button>
    </a-space>
    <span class="filter-tip">供应商、人员、PCC等在各页面高级筛选</span>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { SearchOutlined } from '@ant-design/icons-vue'

const period = ref('30d')
const profitStage = ref('business')
const platform = ref('all')
const airline = ref('all')
const periodOptions = [{ value: '7d', label: '最近7天' }, { value: '30d', label: '最近30天' }, { value: 'month', label: '本月' }, { value: 'quarter', label: '本季度' }]
const profitOptions = [{ value: 'expected', label: '预期利润' }, { value: 'business', label: '业务估算利润' }, { value: 'settled', label: '已结算利润' }]
const platformOptions = [{ value: 'all', label: '全部平台' }, { value: 'ctrip', label: '携程' }, { value: 'qunar', label: '去哪儿' }, { value: 'fliggy', label: '飞猪' }]
const airlineOptions = [{ value: 'all', label: '全部航司' }, { value: 'domestic', label: '国内航司' }, { value: 'international', label: '国际航司' }]
</script>

