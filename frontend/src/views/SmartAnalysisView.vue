<template>
  <div class="page-wrap">
    <PageHeader
      eyebrow="INTELLIGENT ANALYTICS"
      title="智能分析"
      description="基于已确认的数据资产和指标口径，逐步建设智能问数、经营诊断与主动预警能力"
    />
    <DataStateBar
      label="框架已就绪"
      message="当前为功能规划页，尚未接入智能模型、分析规则或生产数据"
      freshness="暂无运行时间"
      metric-state="能力待接入"
    />

    <div class="smart-capability-grid">
      <a-card v-for="item in capabilities" :key="item.title" class="smart-capability-card" :bordered="false">
        <div class="smart-capability-head">
          <span><RobotOutlined /></span>
          <a-tag>待建设</a-tag>
        </div>
        <h2>{{ item.title }}</h2>
        <p>{{ item.description }}</p>
      </a-card>
    </div>

    <a-card class="panel-card smart-workspace" :bordered="false" title="智能分析工作区">
      <a-empty description="等待业务问题、指标口径和数据权限确认后接入">
        <template #image>
          <RobotOutlined class="smart-placeholder-icon" />
        </template>
      </a-empty>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { RobotOutlined } from '@ant-design/icons-vue'
import DataStateBar from '@/components/DataStateBar.vue'
import PageHeader from '@/components/PageHeader.vue'

const capabilities = [
  { title: '智能问数', description: '使用自然语言查询经过确认的指标，并保留数据范围、时间口径与来源说明。' },
  { title: '经营诊断', description: '围绕利润变化逐层下钻平台、航司、供应商和业务明细，形成可核对证据。' },
  { title: '主动预警', description: '在规则、阈值和负责人确认后，识别异常变化并进入问题处理流程。' },
]
</script>

<style scoped>
.smart-capability-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 14px; }
.smart-capability-card { border: 1px solid #e7ebf1 !important; box-shadow: 0 5px 18px rgba(28,45,72,.035); }
.smart-capability-head { display: flex; align-items: center; justify-content: space-between; }
.smart-capability-head > span { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 10px; color: #3178f6; background: #edf4ff; font-size: 20px; }
.smart-capability-card h2 { margin: 17px 0 8px; color: #273348; font-size: 15px; }
.smart-capability-card p { min-height: 42px; margin: 0; color: #748195; font-size: 12px; line-height: 1.7; }
.smart-workspace { min-height: 320px; }
.smart-workspace :deep(.ant-card-body) { padding-top: 52px; }
.smart-placeholder-icon { color: #7d97bd; font-size: 58px; }

@media (max-width: 820px) {
  .smart-capability-grid { grid-template-columns: 1fr; }
}
</style>
