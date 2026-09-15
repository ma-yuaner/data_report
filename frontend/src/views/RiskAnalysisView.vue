<template>
  <div class="page-wrap">
    <PageHeader
      eyebrow="RISK CONTROL"
      title="风控分析"
      description="集中承载 ADM、平台罚单、投诉及高风险售后等风险分析页面"
    />
    <DataStateBar
      label="框架预留"
      message="当前仅建立一级入口，风险指标、业务规则和数据源尚未接入"
      freshness="暂无数据更新时间"
      metric-state="口径待确认"
    />

    <a-card class="panel-card" :bordered="false" title="风控页面建设区">
      <a-empty description="暂无已确认的风控指标">
        <template #image>
          <SafetyCertificateOutlined class="risk-placeholder-icon" />
        </template>
        <p class="risk-placeholder-copy">
          后续根据已确认的风险类型、识别规则和处置流程，在这里逐步增加页面；未接入数据不会展示为 0。
        </p>
      </a-empty>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { SafetyCertificateOutlined } from '@ant-design/icons-vue'
import DataStateBar from '@/components/DataStateBar.vue'
import PageHeader from '@/components/PageHeader.vue'
</script>

<style scoped>
.panel-card { min-height: 390px; }
.panel-card :deep(.ant-card-body) { padding-top: 72px; }
.risk-placeholder-icon { color: #7d97bd; font-size: 58px; }
.risk-placeholder-copy { max-width: 620px; margin: 12px auto 0; color: #7b8798; line-height: 1.7; }
</style>
