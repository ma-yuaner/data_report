<template>
  <div class="page-wrap">
    <PageHeader eyebrow="DATA ASSETS" title="数据资产" description="公开数据部已有、建设中、缺失和待确认的数据能力">
      <a-button><BookOutlined />查看业务知识库</a-button>
    </PageHeader>
    <DataStateBar label="资产盘点草稿" message="覆盖度为MVP演示，用于确认页面结构" freshness="首次盘点" metric-state="待业务确认" />

    <a-tabs v-model:active-key="activeTab" class="business-tabs">
      <a-tab-pane key="coverage" tab="数据覆盖">
        <div class="asset-summary">
          <div><DatabaseOutlined /><span><strong>{{ coverage.length }}</strong>业务领域</span></div>
          <div><CheckCircleOutlined /><span><strong>{{ readyCount }}</strong>可接入</span></div>
          <div><WarningOutlined /><span><strong>{{ pendingCount }}</strong>待补齐/确认</span></div>
        </div>
        <div class="coverage-grid">
          <a-card v-for="item in coverage" :key="item.domain" class="coverage-card" :bordered="false">
            <div class="coverage-head"><strong>{{ item.domain }}</strong><a-tag :color="stateColor[item.state]">{{ item.label }}</a-tag></div>
            <p>{{ item.canAnswer }}</p>
            <a-progress :percent="item.coverage" :show-info="false" :stroke-color="stateStroke[item.state]" />
            <div class="coverage-foot"><span>当前覆盖度（演示）</span><strong>{{ item.coverage }}%</strong></div>
          </a-card>
        </div>
      </a-tab-pane>
      <a-tab-pane key="metrics" tab="指标口径"><EmptyState title="指标注册中心待建设" description="后续展示指标定义、粒度、时间口径、负责人、状态和使用页面。" /></a-tab-pane>
      <a-tab-pane key="freshness" tab="更新状态"><EmptyState title="数据更新监控待接入" description="后续展示各来源系统更新时间、延迟、质量和责任人。" /></a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { BookOutlined, CheckCircleOutlined, DatabaseOutlined, WarningOutlined } from '@ant-design/icons-vue'
import { getCoverage, type CoverageItem } from '@/api/dashboard'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import EmptyState from '@/components/EmptyState.vue'

const activeTab = ref('coverage')
const coverage = ref<CoverageItem[]>([])
const readyCount = computed(() => coverage.value.filter(item => item.state === 'ready').length)
const pendingCount = computed(() => coverage.value.filter(item => item.state !== 'ready').length)
const stateColor: Record<CoverageItem['state'], string> = { ready: 'success', building: 'processing', partial: 'warning', missing: 'error', pending: 'default' }
const stateStroke: Record<CoverageItem['state'], string> = { ready: '#2eaf78', building: '#3178f6', partial: '#e7a23b', missing: '#e65a5a', pending: '#98a3b3' }

onMounted(async () => {
  try { coverage.value = (await getCoverage()).items }
  catch (error) { message.error(error instanceof Error ? error.message : '资产数据加载失败') }
})
</script>

