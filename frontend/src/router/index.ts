import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录', public: true } },
    { path: '/change-password', name: 'change-password', component: () => import('@/views/ChangePasswordView.vue'), meta: { title: '修改密码' } },
    {
      path: '/',
      component: AppLayout,
      redirect: '/overview',
      children: [
        { path: 'overview', name: 'overview', component: () => import('@/views/OverviewView.vue'), meta: { title: '经营总览', section: '经营总览' } },
        { path: 'analysis/comprehensive', name: 'comprehensive-analysis', component: () => import('@/views/ComprehensiveAnalysisLiveView.vue'), meta: { title: '综合分析', section: '业务分析' } },
        { path: 'analysis/issue', alias: '/analysis/profit', name: 'issue-profit', component: () => import('@/views/ProfitView.vue'), meta: { title: '出票分析', section: '业务分析' } },
        { path: 'analysis/refund', name: 'refund-profit', component: () => import('@/views/BusinessProfitView.vue'), props: { businessType: 'refund' }, meta: { title: '退票分析', section: '业务分析' } },
        { path: 'analysis/change', name: 'change-profit', component: () => import('@/views/BusinessProfitView.vue'), props: { businessType: 'change' }, meta: { title: '改签分析', section: '业务分析' } },
        { path: 'analysis/ancillary', name: 'ancillary-profit', component: () => import('@/views/BusinessProfitView.vue'), props: { businessType: 'ancillary' }, meta: { title: '增值分析', section: '业务分析' } },
        { path: 'risk-analysis', name: 'risk-analysis', component: () => import('@/views/RiskMonthlyAnalysisView.vue'), meta: { title: '风控总览', section: '风控分析' } },
        { path: 'risk-analysis/issue', name: 'risk-issue-profit', component: () => import('@/views/RiskBusinessAnalysisView.vue'), props: { businessType: 'issue' }, meta: { title: '出票利润分析', section: '风控分析' } },
        { path: 'risk-analysis/refund', name: 'risk-refund-profit', component: () => import('@/views/RiskBusinessAnalysisView.vue'), props: { businessType: 'refund' }, meta: { title: '退票利润分析', section: '风控分析' } },
        { path: 'risk-analysis/change', name: 'risk-change-profit', component: () => import('@/views/RiskBusinessAnalysisView.vue'), props: { businessType: 'change' }, meta: { title: '改签利润分析', section: '风控分析' } },
        { path: 'risk-analysis/errors', name: 'risk-errors', component: () => import('@/views/RiskErrorAnalysisView.vue'), meta: { title: '差错分析', section: '风控分析' } },
        { path: 'risk-analysis/orders', name: 'risk-orders', component: () => import('@/views/RiskBusinessAnalysisView.vue'), props: { ordersOnly: true }, meta: { title: '订单明细', section: '风控分析' } },
        { path: 'risk-analysis/upload', name: 'risk-upload', component: () => import('@/views/RiskUploadView.vue'), meta: { title: '数据上传', section: '风控分析' } },
        { path: 'smart-analysis', name: 'smart-analysis', component: () => import('@/views/SmartAnalysisView.vue'), meta: { title: '智能分析', section: '智能分析' } },
        { path: 'smart-analysis/placement/policies', name: 'smart-placement-policies', component: () => import('@/views/SmartPlacementPolicyView.vue'), meta: { title: '投放政策', section: '智能分析' } },
        { path: 'smart-analysis/placement/orders', name: 'smart-placement-orders', component: () => import('@/views/SmartPlacementOrdersView.vue'), meta: { title: '收单情况', section: '智能分析' } },
        { path: 'problems', name: 'problems', component: () => import('@/views/ProblemsView.vue'), meta: { title: '问题中心', section: '问题中心' } },
        { path: 'data-assets', name: 'assets', component: () => import('@/views/AssetsView.vue'), meta: { title: '数据资产', section: '数据资产' } },
        { path: 'admin/behavior', name: 'admin-behavior', component: () => import('@/views/UserBehaviorMonitorView.vue'), meta: { title: '用户行为监控', section: '系统管理', requiresAdmin: true } },
        { path: 'admin/users', name: 'admin-users', component: () => import('@/views/AdminUsersView.vue'), meta: { title: '账号管理', section: '系统管理', requiresAdmin: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { title: '页面不存在' } },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const authStore = useAuthStore()
  if (!authStore.initialized) {
    try { await authStore.fetchMe() }
    catch { return { name: 'login', query: { redirect: to.fullPath } } }
  }
  if (!authStore.user) return { name: 'login', query: { redirect: to.fullPath } }
  if (authStore.user.mustChangePassword && to.name !== 'change-password') {
    return { name: 'change-password', query: { first: '1' } }
  }
  if (to.meta.requiresAdmin && !authStore.user.isAdmin) return '/overview'
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '页面不存在')} · 企业数据中心`
})

export default router
