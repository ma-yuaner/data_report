import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录', public: true } },
    { path: '/change-password', name: 'change-password', component: () => import('@/views/ChangePasswordView.vue'), meta: { title: '修改密码' } },
    {
      path: '/',
      component: AppLayout,
      redirect: '/home',
      children: [
        { path: 'home', name: 'home', component: () => import('@/views/HomeView.vue'), meta: { title: '工作台', section: '企业数据中心' } },
        { path: 'resource-governance', redirect: '/resource-governance/gds' },
        { path: 'resource-governance/gds', name: 'gds-resource-governance', component: () => import('@/views/ResourceGovernanceView.vue'), meta: { title: 'GDS资源治理', section: '资源治理', menuCode: 'governance.gds', governanceLayer: 'gds' } },
        { path: 'resource-governance/ota', name: 'ota-channel-quality', component: () => import('@/views/ResourceGovernanceView.vue'), meta: { title: 'OTA渠道质量', section: '资源治理', menuCode: 'governance.ota', governanceLayer: 'ota' } },
        { path: 'overview', name: 'overview', component: () => import('@/views/OverviewView.vue'), meta: { title: '经营总览', section: '经营总览', menuCode: 'overview' } },
        { path: 'analysis/comprehensive', name: 'comprehensive-analysis', component: () => import('@/views/ComprehensiveAnalysisLiveView.vue'), meta: { title: '综合分析', section: '业务分析', menuCode: 'analysis.comprehensive' } },
        { path: 'analysis/issue', alias: '/analysis/profit', name: 'issue-profit', component: () => import('@/views/ProfitView.vue'), meta: { title: '出票分析', section: '业务分析', menuCode: 'analysis.issue' } },
        { path: 'analysis/refund', name: 'refund-profit', component: () => import('@/views/BusinessProfitView.vue'), props: { businessType: 'refund' }, meta: { title: '退票分析', section: '业务分析', menuCode: 'analysis.refund' } },
        { path: 'analysis/change', name: 'change-profit', component: () => import('@/views/BusinessProfitView.vue'), props: { businessType: 'change' }, meta: { title: '改签分析', section: '业务分析', menuCode: 'analysis.change' } },
        { path: 'analysis/ancillary', name: 'ancillary-profit', component: () => import('@/views/BusinessProfitView.vue'), props: { businessType: 'ancillary' }, meta: { title: '增值分析', section: '业务分析', menuCode: 'analysis.ancillary' } },
        { path: 'risk-analysis', name: 'risk-analysis', component: () => import('@/views/RiskMonthlyAnalysisView.vue'), meta: { title: '风控总览', section: '风控分析', menuCode: 'risk.overview' } },
        { path: 'risk-analysis/issue', name: 'risk-issue-profit', component: () => import('@/views/RiskBusinessAnalysisView.vue'), props: { businessType: 'issue' }, meta: { title: '出票利润分析', section: '风控分析', menuCode: 'risk.issue' } },
        { path: 'risk-analysis/refund', name: 'risk-refund-profit', component: () => import('@/views/RiskBusinessAnalysisView.vue'), props: { businessType: 'refund' }, meta: { title: '退票利润分析', section: '风控分析', menuCode: 'risk.refund' } },
        { path: 'risk-analysis/change', name: 'risk-change-profit', component: () => import('@/views/RiskBusinessAnalysisView.vue'), props: { businessType: 'change' }, meta: { title: '改签利润分析', section: '风控分析', menuCode: 'risk.change' } },
        { path: 'risk-analysis/errors', name: 'risk-errors', component: () => import('@/views/RiskErrorAnalysisView.vue'), meta: { title: '差错分析', section: '风控分析', menuCode: 'risk.errors' } },
        { path: 'risk-analysis/orders', name: 'risk-orders', component: () => import('@/views/RiskBusinessAnalysisView.vue'), props: { ordersOnly: true }, meta: { title: '订单明细', section: '风控分析', menuCode: 'risk.orders' } },
        { path: 'risk-analysis/upload', name: 'risk-upload', component: () => import('@/views/RiskUploadView.vue'), meta: { title: '数据上传', section: '风控分析', menuCode: 'risk.upload' } },
        { path: 'smart-analysis', redirect: '/smart-analysis/comprehensive' },
        { path: 'smart-analysis/comprehensive', name: 'smart-comprehensive', component: () => import('@/views/SmartComprehensiveView.vue'), meta: { title: '智能综合分析', section: '智能分析', menuCode: 'smart.comprehensive' } },
        { path: 'smart-analysis/overview', name: 'smart-overview', component: () => import('@/views/SmartOverviewView.vue'), meta: { title: '智能总览', section: '智能分析', menuCode: 'smart.overview' } },
        { path: 'smart-analysis/dimensions', name: 'smart-dimensions', component: () => import('@/views/SmartDimensionView.vue'), meta: { title: '维度分析', section: '智能分析', menuCode: 'smart.dimensions' } },
        { path: 'smart-analysis/details', name: 'smart-details', component: () => import('@/views/SmartDetailView.vue'), meta: { title: '出票明细', section: '智能分析', menuCode: 'smart.details' } },
        { path: 'smart-analysis/placement/policies', name: 'smart-placement-policies', component: () => import('@/views/SmartPlacementPolicyView.vue'), meta: { title: '投放政策', section: '智能分析', menuCode: 'smart.placement.policies' } },
        { path: 'smart-analysis/placement/orders', name: 'smart-placement-orders', component: () => import('@/views/SmartPlacementOrdersView.vue'), meta: { title: '收单情况', section: '智能分析', menuCode: 'smart.placement.orders' } },
        { path: 'monitoring', name: 'monitoring-center', component: () => import('@/views/MonitoringCenterView.vue'), meta: { title: '监控中心', section: '监控中心', menuCode: 'monitor.center' } },
        { path: 'problems', name: 'problems', component: () => import('@/views/ProblemsView.vue'), meta: { title: '问题中心', section: '问题中心', menuCode: 'problems' } },
        { path: 'data-assets', name: 'assets', component: () => import('@/views/AssetsView.vue'), meta: { title: '数据资产', section: '数据资产', menuCode: 'data_assets' } },
        { path: 'admin/behavior', name: 'admin-behavior', component: () => import('@/views/UserBehaviorMonitorView.vue'), meta: { title: '用户行为监控', section: '系统管理', requiresAdmin: true } },
        { path: 'admin/users', name: 'admin-users', component: () => import('@/views/AdminUsersView.vue'), meta: { title: '账号管理', section: '系统管理', requiresAdmin: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { title: '页面不存在' } },
  ],
})

router.beforeEach(async (to) => {
  useAppStore().startNavigation()
  if (to.meta.public) return true
  const authStore = useAuthStore()
  if (!authStore.initialized) {
    try { await authStore.fetchMe() }
    catch { return { name: 'login', query: { redirect: to.fullPath } } }
  } else if (authStore.user) {
    try { await authStore.refreshAccessIfStale() }
    catch { return { name: 'login', query: { redirect: to.fullPath } } }
  }
  if (!authStore.user) return { name: 'login', query: { redirect: to.fullPath } }
  if (authStore.user.mustChangePassword && to.name !== 'change-password') {
    return { name: 'change-password', query: { first: '1' } }
  }
  if (to.meta.requiresAdmin && !authStore.user.isAdmin) return '/home'
  if (to.meta.menuCode && !authStore.user.isAdmin && !authStore.user.menuCodes?.includes(String(to.meta.menuCode))) return '/home'
  return true
})

router.afterEach((to) => {
  useAppStore().finishNavigation()
  document.title = `${String(to.meta.title ?? '页面不存在')} · 企业数据中心`
})

router.onError(() => useAppStore().finishNavigation())

export default router
