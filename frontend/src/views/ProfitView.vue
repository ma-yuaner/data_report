<template>
  <div class="page-wrap">
    <PageHeader eyebrow="PROFIT ANALYSIS" title="利润分析" description="区分预期、业务估算和已结算利润，解释利润从哪里来、亏损由什么造成" />
    <DataStateBar label="口径待确认" message="财务利润桥和金额正负号确认后再接入真实指标" freshness="尚未接入" metric-state="草稿" />
    <FilterBar />

    <a-tabs v-model:active-key="activeTab" class="business-tabs">
      <a-tab-pane key="overview" tab="利润全景">
        <div class="kpi-grid three">
          <a-card class="placeholder-metric" :bordered="false"><span>预期利润</span><strong>待接入</strong><small>政策与投放阶段</small></a-card>
          <a-card class="placeholder-metric" :bordered="false"><span>业务估算利润</span><strong>待接入</strong><small>ERP已知业务事件</small></a-card>
          <a-card class="placeholder-metric" :bordered="false"><span>已结算利润</span><strong>待接入</strong><small>财务确认结果</small></a-card>
        </div>
        <a-card class="panel-card" :bordered="false" title="利润确认链路">
          <div class="profit-stages">
            <div><span>01</span><strong>政策测算</strong><small>前返、后返、任务、让利</small></div><ArrowRightOutlined />
            <div><span>02</span><strong>出票重估</strong><small>采购、佣金、支付、供应</small></div><ArrowRightOutlined />
            <div><span>03</span><strong>售后变化</strong><small>退改、增值、退款、垫资</small></div><ArrowRightOutlined />
            <div><span>04</span><strong>财务结算</strong><small>后返确认、ADM、汇率、冲销</small></div>
          </div>
        </a-card>
      </a-tab-pane>
      <a-tab-pane key="drivers" tab="利润归因">
        <EmptyState title="等待利润项目映射" description="收入、采购、佣金、支付、返点、增值、售后和ADM字段确认后生成利润桥。" />
      </a-tab-pane>
      <a-tab-pane key="variance" tab="预期与结算差异">
        <EmptyState title="等待三套利润口径" description="接入后返、退款、结算、汇率和处罚数据后定位差异原因。" />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ArrowRightOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import FilterBar from '@/components/FilterBar.vue'
import EmptyState from '@/components/EmptyState.vue'

const activeTab = ref('overview')
</script>

