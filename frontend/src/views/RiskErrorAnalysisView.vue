<template>
  <div class="page-wrap risk-error-page">
    <PageHeader eyebrow="RISK ERROR ANALYSIS" title="差错分析" description="按部门、标准原因和订单证据定位差错问题">
      <a-tag color="gold">数据字段待补齐</a-tag>
    </PageHeader>
    <a-alert type="warning" show-icon message="当前不生成差错数字"
      description="现有出票核对表已移除“计入差错、正确原因、备注【原始】”，退票和改签表也没有统一差错标记。没有明确字段时无法可靠判断一笔订单是否属于差错。" />
    <div class="readiness-grid">
      <a-card v-for="item in readiness" :key="item.field" :bordered="false" class="readiness-card">
        <div class="readiness-head"><strong>{{ item.label }}</strong><a-tag :color="item.ready ? 'green' : 'orange'">{{ item.ready ? '已具备' : '待补齐' }}</a-tag></div>
        <code>{{ item.field }}</code><p>{{ item.purpose }}</p>
      </a-card>
    </div>
    <a-card :bordered="false" class="flow-card" title="字段补齐后启用的分析路径">
      <div class="future-flow"><span>差错总量与损失</span><i>→</i><span>部门与标准原因</span><i>→</i><span>平台 / 航司交叉</span><i>→</i><span>具体订单证据</span></div>
      <p>页面入口和布局已建立；后续只需在核对明细或独立差错事实表补充标准字段，再接入真实查询。不会从“备注【整理】”自由文本自动猜测差错结论。</p>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '@/components/PageHeader.vue'

const readiness = [
  { label: '业务类型', field: 'business_type', ready: true, purpose: '区分出票、退票、改签，现有三张核对表可直接确定。' },
  { label: '业务部门', field: 'org_cname', ready: true, purpose: '用于部门对比与订单下钻，三张核对表均已存在。' },
  { label: '是否计入差错', field: 'error_flag', ready: false, purpose: '明确差错分子，不能由利润正负或备注内容替代。' },
  { label: '标准差错原因', field: 'error_reason', ready: false, purpose: '承接Excel中的原因分析，需统一字典后才能长期比较。' },
]
</script>

<style scoped>
.risk-error-page > .ant-alert { margin-bottom: 16px; border-radius: 10px; }
.readiness-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 14px; }
.readiness-card { border: 1px solid #e6eaf0; }
.readiness-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.readiness-card code { display: block; margin: 16px 0 10px; color: #3d6ba8; }
.readiness-card p, .flow-card p { margin: 0; color: #748195; font-size: 12px; line-height: 1.7; }
.flow-card { border: 1px solid #e6eaf0; }
.future-flow { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; }
.future-flow span { padding: 12px 15px; border-radius: 8px; color: #315d96; background: #eef5ff; font-size: 12px; }
.future-flow i { color: #98a5b6; font-style: normal; }
@media (max-width: 1000px) { .readiness-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .readiness-grid { grid-template-columns: 1fr; } }
</style>
