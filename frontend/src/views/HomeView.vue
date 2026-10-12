<template>
  <div class="page-wrap workspace-home">
    <section class="workspace-hero">
      <div class="workspace-hero-copy">
        <span class="workspace-eyebrow">ENTERPRISE DATA CENTER</span>
        <h1>{{ greeting }}，{{ displayName }}</h1>
        <p>{{ todayText }}。先选择要处理的工作，系统不会在首页自动查询经营数据。</p>
        <div class="workspace-hero-tags">
          <span><CheckCircleFilled /> 数据服务已就绪</span>
          <span><ClockCircleOutlined /> 闲置 4 小时自动退出</span>
          <span><SafetyCertificateOutlined /> {{ roleText }}</span>
        </div>
      </div>
      <div class="workspace-hero-visual" aria-hidden="true">
        <div class="workspace-orbit orbit-one" />
        <div class="workspace-orbit orbit-two" />
        <div class="workspace-core"><BarChartOutlined /></div>
        <span class="workspace-node node-one"><DatabaseOutlined /></span>
        <span class="workspace-node node-two"><SafetyCertificateOutlined /></span>
        <span class="workspace-node node-three"><ThunderboltOutlined /></span>
      </div>
    </section>

    <section class="workspace-section">
      <div class="workspace-section-title">
        <div><span>QUICK ACCESS</span><h2>从哪里开始</h2></div>
        <p>按工作目标进入模块，只有打开分析页后才查询对应数据。</p>
      </div>
      <div class="workspace-entry-grid">
        <button v-for="entry in quickEntries" :key="entry.to" type="button" class="workspace-entry" @click="router.push(entry.to)">
          <span class="workspace-entry-icon" :style="{ color: entry.color, background: entry.background }"><component :is="entry.icon" /></span>
          <span class="workspace-entry-copy"><small>{{ entry.eyebrow }}</small><strong>{{ entry.title }}</strong><em>{{ entry.description }}</em></span>
          <ArrowRightOutlined class="workspace-entry-arrow" />
        </button>
      </div>
    </section>

    <div class="workspace-bottom-grid">
      <section class="workspace-card workspace-flow-card">
        <div class="workspace-card-title"><div><span>WORKFLOW</span><h2>推荐分析路径</h2></div><CompassOutlined /></div>
        <div class="workspace-flow">
          <div><b>01</b><span><strong>看全局</strong><small>经营总览确认出退改增整体利润</small></span></div>
          <i />
          <div><b>02</b><span><strong>找差异</strong><small>综合分析按平台、航司、产品定位问题</small></span></div>
          <i />
          <div><b>03</b><span><strong>查订单</strong><small>进入风控分析下钻到具体订单明细</small></span></div>
        </div>
      </section>

      <section class="workspace-card workspace-principle-card">
        <div class="workspace-card-title"><div><span>DATA PRINCIPLE</span><h2>当前数据口径</h2></div><SafetyCertificateOutlined /></div>
        <ul>
          <li><span>经营分析</span><strong>MySQL ADS 实际同步数据</strong></li>
          <li><span>加工来源</span><strong>Hive 出退改增业务宽表</strong></li>
          <li><span>利润口径</span><strong>业务估算，不替代财务结算</strong></li>
        </ul>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ApartmentOutlined, ArrowRightOutlined, BarChartOutlined, CheckCircleFilled,
  CompassOutlined, DashboardOutlined, DatabaseOutlined, SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const hour = new Date().getHours()
const greeting = hour < 11 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好'
const displayName = computed(() => authStore.user?.displayName || authStore.user?.username || '同事')
const roleText = computed(() => authStore.user?.isAdmin ? '数据管理员' : '数据使用者')
const todayText = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
}).format(new Date())

const quickEntries = [
  { to: '/overview', eyebrow: 'OVERVIEW', title: '经营总览', description: '查看今日出、退、改、增利润全貌', icon: DashboardOutlined, color: '#2f6edb', background: '#edf4ff' },
  { to: '/analysis/comprehensive', eyebrow: 'ANALYSIS', title: '综合分析', description: '按平台、航司、产品和政策员逐层下钻', icon: ApartmentOutlined, color: '#7257c5', background: '#f2efff' },
  { to: '/risk-analysis', eyebrow: 'RISK CONTROL', title: '风控分析', description: '复核亏损结构并定位具体问题订单', icon: SafetyCertificateOutlined, color: '#cc5a5f', background: '#fff0f0' },
  { to: '/smart-analysis/placement/policies', eyebrow: 'SMART PLACEMENT', title: '智能投放', description: '进入投放机会、审核和认领工作流', icon: ThunderboltOutlined, color: '#c97925', background: '#fff5e8' },
  { to: '/data-assets', eyebrow: 'DATA ASSETS', title: '数据资产', description: '查看数据表、字段覆盖和资产状态', icon: DatabaseOutlined, color: '#19866a', background: '#eaf8f3' },
]

onMounted(() => {
  window.setTimeout(() => {
    void Promise.allSettled([
      import('@/views/OverviewView.vue'),
      import('@/views/ComprehensiveAnalysisLiveView.vue'),
      import('@/views/RiskMonthlyAnalysisView.vue'),
    ])
  }, 800)
})
</script>
