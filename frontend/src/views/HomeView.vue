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
      <svg class="workspace-hero-visual" viewBox="0 0 240 160" aria-hidden="true" focusable="false">
        <ellipse cx="125" cy="83" rx="105" ry="44" transform="rotate(-17 125 83)" fill="var(--platform-hover)" />
        <g fill="none" stroke="var(--platform-accent)" stroke-width="1.2">
          <ellipse cx="121" cy="80" rx="106" ry="41" transform="rotate(-17 121 80)" />
          <path d="M25 100Q126 12 221 54" stroke-dasharray="3 4" opacity=".45" />
          <rect x="139" y="62" width="43" height="41" rx="8" />
        </g>
        <g fill="var(--platform-accent)">
          <path d="M92 45l13 7 25-11c5-2 8 2 3 5l-22 15-4 17-6 3-1-17-14 1-4-4 12-6-8-7z" />
          <rect x="149" y="84" width="5" height="11" rx="1" /><rect x="158" y="76" width="5" height="19" rx="1" /><rect x="167" y="69" width="5" height="26" rx="1" />
          <circle cx="20" cy="105" r="3" /><circle cx="202" cy="36" r="3" />
        </g>
      </svg>
    </section>

    <section class="workspace-section">
      <div class="workspace-section-title">
        <div><span>QUICK ACCESS</span><h2>从哪里开始</h2></div>
        <p>按工作目标进入模块，只有打开分析页后才查询对应数据。</p>
      </div>
      <a-empty v-if="!quickEntries.length" description="暂无可用快捷入口" />
      <div v-else class="workspace-entry-grid">
        <button v-for="entry in quickEntries" :key="entry.to" type="button" class="workspace-entry" @click="router.push(entry.to)">
          <span class="workspace-entry-icon"><component :is="entry.icon" /></span>
          <span class="workspace-entry-copy"><small>{{ entry.eyebrow }}</small><strong>{{ entry.title }}</strong><em>{{ entry.description }}</em></span>
          <ArrowRightOutlined class="workspace-entry-arrow" />
        </button>
      </div>
    </section>

    <div v-if="showWorkflow || showDataPrinciples" class="workspace-bottom-grid"
      :style="showWorkflow && showDataPrinciples ? undefined : { gridTemplateColumns: '1fr' }">
      <section v-if="showWorkflow" class="workspace-card workspace-flow-card">
        <div class="workspace-card-title"><div><span>WORKFLOW</span><h2>推荐分析路径</h2></div><CompassOutlined /></div>
        <div class="workspace-flow">
          <div><b>01</b><span><strong>看全局</strong><small>经营总览确认出退改增整体利润</small></span></div>
          <i />
          <div><b>02</b><span><strong>找差异</strong><small>综合分析按平台、航司、产品定位问题</small></span></div>
          <i />
          <div><b>03</b><span><strong>查订单</strong><small>进入风控分析下钻到具体订单明细</small></span></div>
        </div>
      </section>

      <section v-if="showDataPrinciples" class="workspace-card workspace-principle-card">
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
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ApartmentOutlined, ArrowRightOutlined, CheckCircleFilled, ClockCircleOutlined,
  CompassOutlined, DashboardOutlined, DatabaseOutlined, DeploymentUnitOutlined, SafetyCertificateOutlined,
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

const entries = [
  { to: '/adm/cases?scope=mine', eyebrow: 'ADM', title: 'ADM 控制台', description: '查看并处理分配给我的 ADM 任务', icon: CompassOutlined },
  { to: '/resource-governance/gds', eyebrow: 'GDS GOVERNANCE', title: 'GDS资源治理', description: '分析GDS、PCC查询量、航段数与查定比', icon: DeploymentUnitOutlined },
  { to: '/resource-governance/ota', eyebrow: 'OTA QUALITY', title: 'OTA渠道质量', description: '分析平台查询、验价与生单接口成功率', icon: DeploymentUnitOutlined },
  { to: '/overview', eyebrow: 'OVERVIEW', title: '经营总览', description: '查看今日出、退、改、增利润全貌', icon: DashboardOutlined },
  { to: '/analysis/comprehensive', eyebrow: 'ANALYSIS', title: '综合分析', description: '按平台、航司、产品和政策员逐层下钻', icon: ApartmentOutlined },
  { to: '/risk-analysis', eyebrow: 'RISK CONTROL', title: '风控分析', description: '复核亏损结构并定位具体问题订单', icon: SafetyCertificateOutlined },
  { to: '/smart-analysis/placement/policies', eyebrow: 'SMART PLACEMENT', title: '智能投放', description: '进入投放机会、审核和认领工作流', icon: ThunderboltOutlined },
  { to: '/data-assets', eyebrow: 'DATA ASSETS', title: '数据资产', description: '查看数据表、字段覆盖和资产状态', icon: DatabaseOutlined },
]

function canOpen(path: string) {
  const user = authStore.user
  const { meta } = router.resolve(path)
  return Boolean(user && (user.isAdmin || (
    meta.menuCode && user.menuCodes?.includes(String(meta.menuCode))
    && (!meta.permission || user.permissions?.includes(String(meta.permission)))
  )))
}

const quickEntries = computed(() => entries.filter(entry => canOpen(entry.to)))
const showWorkflow = computed(() => ['/overview', '/analysis/comprehensive', '/risk-analysis'].every(canOpen))
const showDataPrinciples = computed(() => canOpen('/overview') || canOpen('/analysis/comprehensive'))
</script>
