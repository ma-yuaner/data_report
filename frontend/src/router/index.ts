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
        { path: 'analysis/profit', name: 'profit', component: () => import('@/views/ProfitView.vue'), meta: { title: '出票利润分析', section: '业务分析' } },
        { path: 'analysis/lifecycle', name: 'lifecycle', component: () => import('@/views/LifecycleView.vue'), meta: { title: '机票全链路', section: '业务分析' } },
        { path: 'issues', name: 'issues', component: () => import('@/views/IssuesView.vue'), meta: { title: '异常工作台', section: '异常工作台' } },
        { path: 'assets', name: 'assets', component: () => import('@/views/AssetsView.vue'), meta: { title: '数据资产', section: '数据资产' } },
      ],
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
  ],
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '页面不存在')} · 企业数据中心`
})

export default router
