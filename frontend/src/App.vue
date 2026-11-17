<template>
  <a-config-provider :theme="themeConfig" :locale="zhCN">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import { useAppStore } from '@/stores/app'
import { platformTheme, platformVariables } from '@/theme/platform'

const appStore = useAppStore()
const themeConfig = computed(() => platformTheme(appStore.darkMode))
watchEffect(() => {
  if (typeof document === 'undefined') return
  for (const [name, value] of Object.entries(platformVariables(appStore.darkMode))) {
    document.documentElement.style.setProperty(name, value)
  }
})
</script>

