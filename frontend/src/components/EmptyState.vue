<template>
  <a-card class="empty-state" :bordered="false"><DatabaseOutlined /><h3>{{ title }}</h3><p>{{ description }}</p><a-button disabled>等待数据接入</a-button></a-card>
</template>

<script setup lang="ts">
import { DatabaseOutlined } from '@ant-design/icons-vue'
defineProps<{ title: string; description: string }>()
</script>

