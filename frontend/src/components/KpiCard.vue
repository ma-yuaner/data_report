<template>
  <a-card class="kpi-card" :bordered="false">
    <div class="kpi-top"><span>{{ item.label }}</span><a-tag v-if="item.tone === 'pending'" color="default">待接入</a-tag><a-tag v-else-if="item.tone === 'risk'" color="error">风险</a-tag></div>
    <div class="kpi-value" :class="`tone-${item.tone}`">{{ item.value }}<small v-if="item.unit">{{ item.unit }}</small></div>
    <div class="kpi-foot" v-if="item.change !== null">
      <span :class="item.change >= 0 ? 'change-up' : 'change-down'">{{ item.change >= 0 ? '↑' : '↓' }} {{ Math.abs(item.change) }}%</span>
      <span>较上周期</span>
    </div>
    <div class="kpi-foot" v-else><span>等待业务与财务口径确认</span></div>
  </a-card>
</template>

<script setup lang="ts">
import type { KpiItem } from '@/api/dashboard'
defineProps<{ item: KpiItem }>()
</script>

