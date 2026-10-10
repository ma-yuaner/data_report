<template>
  <a-layout class="app-shell">
    <div class="route-progress" :class="{ 'is-active': appStore.navigating }" />
    <a-layout-sider
      v-model:collapsed="appStore.collapsed"
      :trigger="null"
      collapsible
      class="app-sidebar"
      :width="224"
    >
      <div class="app-brand" :class="{ 'is-collapsed': appStore.collapsed }" role="button" tabindex="0" @click="router.push('/home')" @keydown.enter="router.push('/home')">
        <div class="brand-mark"><BarChartOutlined /></div>
        <div v-if="!appStore.collapsed" class="brand-copy">
          <strong>企业数据中心</strong>
          <span>Data Insight Portal</span>
        </div>
      </div>

      <div class="sidebar-menu-scroll">
        <a-menu v-model:openKeys="openKeys" theme="dark" mode="inline" :selected-keys="selectedKeys" @click="handleMenuClick">
          <a-menu-item key="/home"><template #icon><HomeOutlined /></template>工作台</a-menu-item>
          <a-menu-item key="/overview"><template #icon><DashboardOutlined /></template>经营总览</a-menu-item>
          <a-sub-menu key="analysis">
            <template #icon><LineChartOutlined /></template>
            <template #title>业务分析</template>
            <a-menu-item key="/analysis/comprehensive">综合分析</a-menu-item>
            <a-menu-item key="/analysis/issue">出票分析</a-menu-item>
            <a-menu-item key="/analysis/refund">退票分析</a-menu-item>
            <a-menu-item key="/analysis/change">改签分析</a-menu-item>
            <a-menu-item key="/analysis/ancillary">增值分析</a-menu-item>
          </a-sub-menu>
          <a-sub-menu key="risk">
            <template #icon><SafetyCertificateOutlined /></template>
            <template #title>风控分析</template>
            <a-menu-item key="/risk-analysis">风控总览</a-menu-item>
            <a-menu-item key="/risk-analysis/issue">出票利润分析</a-menu-item>
            <a-menu-item key="/risk-analysis/refund">退票利润分析</a-menu-item>
            <a-menu-item key="/risk-analysis/change">改签利润分析</a-menu-item>
            <a-menu-item key="/risk-analysis/errors">差错分析</a-menu-item>
            <a-menu-item key="/risk-analysis/orders">订单明细</a-menu-item>
            <a-menu-item key="/risk-analysis/upload">数据上传</a-menu-item>
          </a-sub-menu>
          <a-sub-menu key="customer-service">
            <template #icon><CustomerServiceOutlined /></template>
            <template #title>客服分析</template>
            <a-menu-item key="customer-service-refund" disabled>退票分析</a-menu-item>
            <a-menu-item key="customer-service-change" disabled>改签分析</a-menu-item>
            <a-menu-item key="customer-service-flight-change" disabled>清Q/航变分析</a-menu-item>
          </a-sub-menu>
          <a-sub-menu key="smart">
            <template #icon><RobotOutlined /></template>
            <template #title>智能分析</template>
            <a-menu-item key="/smart-analysis">智能分析首页</a-menu-item>
            <a-sub-menu key="smart-placement">
              <template #title>智能投放</template>
              <a-menu-item key="/smart-analysis/placement/policies">投放政策</a-menu-item>
              <a-menu-item key="/smart-analysis/placement/orders">收单情况</a-menu-item>
            </a-sub-menu>
          </a-sub-menu>
          <a-menu-item key="/problems"><template #icon><WarningOutlined /></template>问题中心</a-menu-item>
          <a-menu-item key="/data-assets"><template #icon><DatabaseOutlined /></template>数据资产</a-menu-item>
          <a-sub-menu v-if="authStore.user?.isAdmin" key="system">
            <template #icon><MonitorOutlined /></template>
            <template #title>系统管理</template>
            <a-menu-item key="/admin/behavior">用户行为监控</a-menu-item>
            <a-menu-item key="/admin/users">账号管理</a-menu-item>
          </a-sub-menu>
        </a-menu>
      </div>

      <div v-if="!appStore.collapsed" class="sidebar-note">
        <SafetyCertificateOutlined />
        <div><strong>经营数据中心</strong><span>业务估算利润口径</span></div>
      </div>
    </a-layout-sider>

    <a-layout class="app-main">
      <a-layout-header class="app-header">
        <div class="header-left">
          <a-button type="text" class="header-icon" :aria-label="appStore.collapsed ? '展开菜单' : '收起菜单'" @click="appStore.toggleCollapsed">
            <MenuUnfoldOutlined v-if="appStore.collapsed" />
            <MenuFoldOutlined v-else />
          </a-button>
          <a-breadcrumb>
            <a-breadcrumb-item>数据中心</a-breadcrumb-item>
            <a-breadcrumb-item>{{ route.meta.section }}</a-breadcrumb-item>
            <a-breadcrumb-item v-if="route.meta.title !== route.meta.section">{{ route.meta.title }}</a-breadcrumb-item>
          </a-breadcrumb>
        </div>
        <div class="header-actions">
          <a-tag color="blue">{{ route.path === '/home' ? '数据工作台' : '业务估算利润' }}</a-tag>
          <a-dropdown placement="bottomRight">
            <div class="user-entry">
              <a-avatar size="small">{{ userInitial }}</a-avatar>
              <span>{{ authStore.user?.displayName ?? authStore.user?.username }}</span>
            </div>
            <template #overlay>
              <a-menu @click="handleUserMenu">
                <a-menu-item v-if="authStore.user?.isAdmin" key="admin"><TeamOutlined />账号管理</a-menu-item>
                <a-menu-item key="password"><LockOutlined />修改密码</a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout"><LogoutOutlined />退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <a-layout-content class="app-content"><router-view /></a-layout-content>
    </a-layout>
    <div v-if="loggingOut" class="logout-mask"><a-spin size="large" tip="正在安全退出..." /></div>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BarChartOutlined, CustomerServiceOutlined, DashboardOutlined, DatabaseOutlined, HomeOutlined, LineChartOutlined,
  LockOutlined, LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined, MonitorOutlined, RobotOutlined,
  SafetyCertificateOutlined, TeamOutlined, WarningOutlined,
} from '@ant-design/icons-vue'
import type { MenuProps } from 'ant-design-vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const appStore = useAppStore()
const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const loggingOut = ref(false)
const selectedKeys = computed(() => [route.path === '/analysis/profit' ? '/analysis/issue' : route.path])
const userInitial = computed(() => (authStore.user?.displayName || authStore.user?.username || '数').slice(0, 1))
const openKeys = ref<string[]>([])
watch(() => route.path, path => {
  openKeys.value = path.startsWith('/analysis') ? ['analysis']
    : path.startsWith('/risk-analysis') ? ['risk']
      : path.startsWith('/smart-analysis/placement/') ? ['smart', 'smart-placement']
        : path.startsWith('/smart-analysis') ? ['smart']
        : path.startsWith('/admin/') ? ['system'] : []
}, { immediate: true })

const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
  if (typeof key === 'string' && key.startsWith('/')) router.push(key)
}

const handleUserMenu: MenuProps['onClick'] = async ({ key }) => {
  if (key === 'admin') await router.push('/admin/users')
  if (key === 'password') await router.push('/change-password')
  if (key === 'logout') {
    loggingOut.value = true
    try {
      await authStore.logout()
      await router.replace('/login')
    } finally {
      loggingOut.value = false
    }
  }
}
</script>
