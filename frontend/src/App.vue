<template>
  <a-config-provider :theme="themeConfig">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { theme } from 'ant-design-vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const themeConfig = computed(() => ({
  algorithm: appStore.darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
  token: {
    colorPrimary: '#3178f6',
    borderRadius: 8,
    fontFamily: 'Inter, "Microsoft YaHei", system-ui, sans-serif',
  },
}))
</script>

