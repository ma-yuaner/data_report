<template>
  <a-layout class="app-shell" :style="platformVariables(appStore.darkMode)" @keydown.esc="closeMobileMenu">
    <div class="route-progress" :class="{ 'is-active': appStore.navigating }" />
    <button v-if="mobileMenuOpen" type="button" class="sidebar-mobile-mask" aria-label="关闭主菜单遮罩" @click="closeMobileMenu" @wheel.prevent @touchmove.prevent />
    <a-layout-sider
      v-model:collapsed="appStore.collapsed"
      :trigger="null"
      collapsible
      breakpoint="lg"
      :collapsed-width="64"
      @breakpoint="sidebarBroken = $event"
      class="app-sidebar"
      :width="232"
    >
      <button type="button" class="app-brand" :class="{ 'is-collapsed': appStore.collapsed }" aria-label="数据中台工作台" @click="router.push('/home')">
        <img class="brand-mark" :src="platformIcon" alt="" />
        <span v-if="!appStore.collapsed" class="brand-copy">
          <strong>数据中台</strong>
          <span>乐游五洲</span>
        </span>
      </button>

      <a-button v-if="mobileMenuOpen" ref="mobileClose" type="text" class="sidebar-mobile-close" aria-label="收起主菜单" @click="closeMobileMenu"><MenuFoldOutlined /></a-button>
      <div class="sidebar-search" @keydown.enter.capture="guardSearchComposition">
        <a-button v-if="appStore.collapsed" type="text" aria-label="搜索菜单" @click="focusMenuSearch">
          <template #icon><SearchOutlined /></template>
        </a-button>
        <a-select
          v-else
          ref="menuSearch"
          :value="emptySearchSelection"
          :options="searchOptions"
          :filter-option="filterMenuSearch"
          :virtual="false"
          show-search
          placeholder="搜索菜单"
          aria-label="搜索菜单"
          not-found-content="没有匹配的菜单"
          @select="navigateToMenu"
        >
          <template #suffixIcon><SearchOutlined /></template>
          <template #option="{ label, breadcrumb }">
            <div>{{ label }}</div>
            <div v-if="breadcrumb" class="sidebar-search-breadcrumb">{{ breadcrumb }}</div>
          </template>
        </a-select>
      </div>
      <div class="sidebar-menu-scroll" tabindex="0" role="navigation" aria-label="主菜单">
        <a-config-provider :theme="navigationTheme">
          <a-menu
            v-model:openKeys="openKeys"
            :items="menuItems"
            theme="dark"
            mode="inline"
            :selected-keys="selectedKeys"
            @click="handleMenuClick"
          />
        </a-config-provider>
      </div>

      <div v-if="!appStore.collapsed" class="sidebar-note">
        <SafetyCertificateOutlined />
        <div><strong>经营数据中心</strong><span>业务估算利润口径</span></div>
      </div>
    </a-layout-sider>

    <a-layout class="app-main" :inert="mobileMenuOpen || undefined">
      <a-layout-header class="app-header">
        <div class="header-left">
          <a-button ref="menuToggle" type="text" class="header-icon" :aria-label="appStore.collapsed ? '展开菜单' : '收起菜单'" :aria-expanded="!appStore.collapsed" @click="appStore.toggleCollapsed">
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
          <a-tag class="header-context">{{ headerTag }}</a-tag>
          <a-badge v-if="canExport" :count="exportStore.activeCount" :show-zero="false" size="small">
            <a-button type="text" class="export-entry" @click="exportStore.drawerOpen = true"
              ><DownloadOutlined />导出任务</a-button
            >
          </a-badge>
          <a-dropdown placement="bottomRight">
            <button type="button" class="user-entry" aria-label="打开账号菜单" aria-haspopup="menu">
              <a-avatar size="small">{{ userInitial }}</a-avatar>
              <span>{{ authStore.user?.displayName ?? authStore.user?.username }}</span>
            </button>
            <template #overlay>
              <a-menu @click="handleUserMenu">
                <a-menu-item v-if="authStore.canDeleteAccounts" key="admin"><TeamOutlined />账号管理</a-menu-item>
                <a-menu-item key="password"><LockOutlined />修改密码</a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout"><LogoutOutlined />退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <a-layout-content class="app-content">
        <router-view v-slot="{ Component, route: viewRoute }">
          <component :is="Component" :key="viewRoute.meta.admDetail ? viewRoute.fullPath : undefined" />
        </router-view>
      </a-layout-content>
    </a-layout>
    <ComprehensiveExportDrawer v-if="canExport" />
    <div v-if="loggingOut" class="logout-mask"><a-spin size="large" tip="正在安全退出..." /></div>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  CustomerServiceOutlined,
  DatabaseOutlined,
  HomeOutlined,
  LineChartOutlined,
  DeploymentUnitOutlined,
  SearchOutlined,
  DownloadOutlined,
  LockOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MonitorOutlined,
  RadarChartOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons-vue'
import type { MenuProps } from 'ant-design-vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import ComprehensiveExportDrawer from '@/components/ComprehensiveExportDrawer.vue'
import platformIcon from '@/assets/brand/data-platform.svg'
import { platformVariables, platformNavigationTheme } from '@/theme/platform'
import { sidebarNodes, visibleSidebar, sidebarDestinations, matchesSidebarQuery } from './sidebarNavigation'
import type { SidebarNode } from './sidebarNavigation'

const navigationTheme = platformNavigationTheme()

const appStore = useAppStore()
const sidebarBroken = ref(false)
const mobileMenuOpen = computed(() => sidebarBroken.value && !appStore.collapsed)
const menuToggle = ref<{ $el: HTMLButtonElement }>()
const mobileClose = ref<{ $el: HTMLButtonElement }>()
function closeMobileMenu() { if (sidebarBroken.value) appStore.collapsed = true }
watch(mobileMenuOpen, (open, wasOpen) => {
  if (open) mobileClose.value?.$el.focus()
  else if (wasOpen) menuToggle.value?.$el.focus()
}, { flush: 'post' })
const authStore = useAuthStore()
const exportStore = useComprehensiveExportStore()
const route = useRoute()
const router = useRouter()
const loggingOut = ref(false)
const selectedKeys = computed(() => [
  (route.path === '/adm/cases' || route.path.startsWith('/adm/cases/'))
    ? '/adm'
    : route.path === '/analysis/profit'
      ? '/analysis/issue'
      : route.path,
])
const userInitial = computed(() => (authStore.user?.displayName || authStore.user?.username || '数').slice(0, 1))
const headerTag = computed(() =>
  route.path === '/home'
    ? '数据工作台'
    : route.path.startsWith('/hr-mail')
      ? 'HR报表邮件'
      : route.path.startsWith('/adm')
        ? 'ADM 管理中心'
        : route.path.startsWith('/business-configuration')
          ? '业务目标管理'
          : route.path.startsWith('/resource-governance')
            ? '资源调用治理'
            : route.path.startsWith('/monitoring')
              ? '统一监控治理'
              : '业务估算利润',
)
const exportMenuCodes = new Set([
  'hr.mail',
  'adm.center',
  'gds_route.diagnosis',
  'governance.gds',
  'governance.ota',
  'smart.overview',
  'smart.dimensions',
  'smart.details',
  'smart.placement.missed',
])
const canExport = computed(
  () =>
    authStore.canExportPlacementPolicies ||
    Boolean(authStore.user?.permissions?.includes('analysis.comprehensive.export')) ||
    Boolean(authStore.user?.menuCodes?.some((code) => exportMenuCodes.has(code))),
)
watch(
  [canExport, () => exportStore.drawerOpen],
  ([allowed, open], [wasAllowed, wasOpen]) => {
    if (allowed && (!wasAllowed || (open && !wasOpen))) void exportStore.refresh()
  },
  { immediate: true },
)
watch(
  () => canExport.value && exportStore.activeCount > 0,
  (shouldPoll) => {
    if (shouldPoll) exportStore.startPolling()
    else exportStore.stopPolling()
  },
  { immediate: true },
)
onBeforeUnmount(() => exportStore.stopPolling())
const sidebarIcons = {
  '/home': HomeOutlined,
  business: LineChartOutlined,
  resources: DeploymentUnitOutlined,
  aftersales: CustomerServiceOutlined,
  'risk-adm': SafetyCertificateOutlined,
  data: DatabaseOutlined,
  operations: RadarChartOutlined,
  platform: MonitorOutlined,
}
const visibleNodes = computed(() => visibleSidebar(sidebarNodes, authStore.user, authStore.canDeleteAccounts))
function toMenuItems(nodes: SidebarNode[]): NonNullable<MenuProps['items']> {
  return nodes.map(({ key, label, children }) => {
    const icon = sidebarIcons[key as keyof typeof sidebarIcons]
    return {
      key,
      label,
      icon: icon ? () => h(icon) : undefined,
      children: children ? toMenuItems(children) : undefined,
    }
  })
}
const menuItems = computed(() => toMenuItems(visibleNodes.value))
const destinations = computed(() => sidebarDestinations(visibleNodes.value))
const searchOptions = computed(() => destinations.value.map(({ key, label, groups, keywords }) => ({
  value: key,
  label,
  breadcrumb: groups.join(' › '),
  keywords,
})))
const openKeys = ref<string[]>([])
function revealSelectedMenu() {
  const current = destinations.value.find(item => item.key === selectedKeys.value[0])
  openKeys.value = current?.groupKeys ?? []
}
watch([selectedKeys, destinations, () => appStore.collapsed], () => {
  if (!appStore.collapsed) revealSelectedMenu()
}, { immediate: true })

const menuSearch = ref<{ focus: () => void }>()
const emptySearchSelection: string[] = []
async function focusMenuSearch() {
  appStore.collapsed = false
  await nextTick()
  menuSearch.value?.focus()
}
function guardSearchComposition(event: KeyboardEvent) {
  if (event.isComposing || event.keyCode === 229) event.stopPropagation()
}
function filterMenuSearch(query: string, option?: { keywords?: string[] }) {
  return matchesSidebarQuery(query, option?.keywords ?? [])
}
async function navigateToMenu(key: unknown) {
  if (!destinations.value.some(item => item.key === key) || typeof key !== 'string') return
  closeMobileMenu()
  await router.push(key)
  if (!appStore.collapsed) revealSelectedMenu()
}
const handleMenuClick: MenuProps['onClick'] = ({ key }) => { void navigateToMenu(key) }

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
