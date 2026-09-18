import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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
        { path: 'risk-analysis', name: 'risk-analysis', component: () => import('@/views/RiskMonthlyAnalysisView.vue'), meta: { title: '风控分析', section: '风控分析' } },
        { path: 'smart-analysis', name: 'smart-analysis', component: () => import('@/views/SmartAnalysisView.vue'), meta: { title: '智能分析', section: '智能分析' } },
        { path: 'problems', name: 'problems', component: () => import('@/views/ProblemsView.vue'), meta: { title: '问题中心', section: '问题中心' } },
        { path: 'data-assets', name: 'assets', component: () => import('@/views/AssetsView.vue'), meta: { title: '数据资产', section: '数据资产' } },
      ],
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
  ],
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '页面不存在')} · 企业数据中心`
})

export default router
