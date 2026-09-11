<template>
  <div class="data-state-bar">
    <div class="data-state-main"><InfoCircleOutlined /><strong>{{ label }}</strong><span>{{ message }}</span></div>
    <div class="data-state-items"><span>数据：{{ freshness }}</span><span>口径：{{ metricState }}</span></div>
  </div>
</template>

<script setup lang="ts">
import { InfoCircleOutlined } from '@ant-design/icons-vue'

defineProps<{ label: string; message: string; freshness: string; metricState: string }>()
</script>

