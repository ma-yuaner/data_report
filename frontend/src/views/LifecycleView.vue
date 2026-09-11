<template>
  <div class="page-wrap">
    <PageHeader eyebrow="AIR TICKET LIFECYCLE" title="机票全链路" description="沿售前、出票、售后、结算和增值还原利润与效率发生的位置" />
    <DataStateBar label="框架已就绪" message="不同业务阶段的数据源和关键主键仍待盘点" freshness="按环节展示" metric-state="会议陈述" />
    <FilterBar />

    <a-tabs v-model:active-key="activeStage" class="business-tabs lifecycle-tabs">
      <a-tab-pane v-for="stage in stages" :key="stage.key" :tab="stage.tab">
        <div class="stage-hero">
          <div class="stage-icon"><component :is="stage.icon" /></div>
          <div><div class="stage-label">{{ stage.label }}</div><h2>{{ stage.title }}</h2><p>{{ stage.description }}</p></div>
          <a-tag color="processing">{{ stage.state }}</a-tag>
        </div>
        <div class="dashboard-grid three-col">
          <a-card v-for="question in stage.questions" :key="question.title" class="question-card" :bordered="false">
            <div class="question-index">{{ question.index }}</div><h3>{{ question.title }}</h3><p>{{ question.description }}</p>
          </a-card>
        </div>
        <a-card class="panel-card" :bordered="false" title="页面预留区域">
          <div class="layout-skeleton"><div class="skeleton-wide"></div><div></div><div></div><div class="skeleton-full"></div></div>
          <p class="skeleton-note">真实数据接入后放置核心指标、趋势结构、异常排行和业务明细。</p>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { AuditOutlined, CreditCardOutlined, GiftOutlined, SendOutlined, TagsOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import DataStateBar from '@/components/DataStateBar.vue'
import FilterBar from '@/components/FilterBar.vue'

const activeStage = ref('presale')
const stages = [
  { key: 'presale', tab: '售前·政策', label: 'PRESALE', title: '政策获取与投放', icon: TagsOutlined, state: '数据待盘点', description: '连接政策、平台、航司、PCC、返点、任务和让利，判断投放是否合理。', questions: [
    { index: '01', title: '投了什么', description: '政策覆盖哪些平台、航司、航线和舱位？' }, { index: '02', title: '为什么这样投', description: '预期返点、任务和让利空间如何测算？' }, { index: '03', title: '结果怎么样', description: '带来多少收单、出票、利润和风险？' },
  ]},
  { key: 'ticketing', tab: '售中·出票', label: 'FULFILLMENT', title: '收单、比价与出票', icon: SendOutlined, state: '可接入ADM示例', description: '还原订单到出票的履约过程，识别供应选择、价格变化和超时问题。', questions: [
    { index: '01', title: '能否及时出', description: '出票成功率、耗时和失败原因是什么？' }, { index: '02', title: '是否充分比价', description: '当时可用供应与最终供应有何差异？' }, { index: '03', title: '亏损归属哪里', description: '政策、价格变化、系统和人工执行如何拆分？' },
  ]},
  { key: 'aftersales', tab: '售后·退改', label: 'AFTER SALES', title: '退改、航变与Open', icon: AuditOutlined, state: '规则待确认', description: '围绕客户申请、供应处理、退款和规则凭证还原售后收益与风险。', questions: [
    { index: '01', title: '发生了什么', description: '自愿、非自愿、航变、Open如何分类？' }, { index: '02', title: '资金去了哪里', description: '客户退款、供应退款、费用和垫资如何变化？' }, { index: '03', title: '风险是否可控', description: '授权、规则、投诉和ADM证据是否完整？' },
  ]},
  { key: 'settlement', tab: '结算·资金', label: 'SETTLEMENT', title: '结算与最终利润', icon: CreditCardOutlined, state: '财务口径待确认', description: '连接实收实付、返点确认、退款到账、汇率、罚损和资金周期。', questions: [
    { index: '01', title: '利润是否确认', description: '预期、业务估算和财务结算差异多大？' }, { index: '02', title: '现金是否回来', description: '垫资、账期和退款到账是否异常？' }, { index: '03', title: '差异由谁解释', description: '后返、汇率、冲销和处罚如何归因？' },
  ]},
  { key: 'ancillary', tab: '增值服务', label: 'ANCILLARY', title: '增值产品经营', icon: GiftOutlined, state: '来源待盘点', description: '分析行李、选座、餐食、保险等产品的销售、成本、退款和净收入。', questions: [
    { index: '01', title: '卖了什么', description: '各平台、航司和航线的增值结构如何？' }, { index: '02', title: '真正赚多少', description: '销售额扣除采购和退款后的净收入是多少？' }, { index: '03', title: '能否持续增长', description: '渗透率、投诉和规则依赖是否健康？' },
  ]},
]
</script>

