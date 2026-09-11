<template>
  <a-layout class="app-shell">
    <a-layout-sider
      v-model:collapsed="appStore.collapsed"
      :trigger="null"
      collapsible
      class="app-sidebar"
      :width="224"
    >
      <div class="app-brand" :class="{ 'is-collapsed': appStore.collapsed }">
        <div class="brand-mark"><BarChartOutlined /></div>
        <div v-if="!appStore.collapsed" class="brand-copy">
          <strong>企业数据中心</strong>
          <span>Data Insight Portal</span>
        </div>
      </div>

      <a-menu theme="dark" mode="inline" :selected-keys="selectedKeys" :open-keys="openKeys" @click="handleMenuClick">
        <a-menu-item key="/overview"><template #icon><DashboardOutlined /></template>经营总览</a-menu-item>
        <a-sub-menu key="analysis">
          <template #icon><LineChartOutlined /></template>
          <template #title>业务分析</template>
          <a-menu-item key="/analysis/profit">利润分析</a-menu-item>
          <a-menu-item key="/analysis/lifecycle">机票全链路</a-menu-item>
        </a-sub-menu>
        <a-menu-item key="/issues"><template #icon><AlertOutlined /></template>异常工作台</a-menu-item>
        <a-menu-item key="/assets"><template #icon><DatabaseOutlined /></template>数据资产</a-menu-item>
      </a-menu>

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
          <a-input class="global-search" placeholder="搜索订单、票号或指标" allow-clear>
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-button type="text" class="header-icon" aria-label="切换主题" @click="appStore.toggleTheme">
            <BulbOutlined />
          </a-button>
          <a-badge dot><BellOutlined class="header-bell" /></a-badge>
          <a-dropdown>
            <div class="user-entry"><a-avatar size="small">数</a-avatar><span>数据管理员</span><DownOutlined /></div>
            <template #overlay>
              <a-menu><a-menu-item>个人设置</a-menu-item><a-menu-item>系统管理</a-menu-item><a-menu-divider /><a-menu-item>退出登录</a-menu-item></a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <a-layout-content class="app-content"><router-view /></a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertOutlined, BarChartOutlined, BellOutlined, BulbOutlined, DashboardOutlined,
  DatabaseOutlined, DownOutlined, LineChartOutlined, MenuFoldOutlined,
  MenuUnfoldOutlined, SafetyCertificateOutlined, SearchOutlined,
} from '@ant-design/icons-vue'
import type { MenuProps } from 'ant-design-vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const route = useRoute()
const router = useRouter()
const selectedKeys = computed(() => [route.path])
const openKeys = computed(() => route.path.startsWith('/analysis') ? ['analysis'] : [])

const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
  if (typeof key === 'string' && key.startsWith('/')) router.push(key)
}
</script>
