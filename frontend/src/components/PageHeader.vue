<template>
  <div class="page-header">
    <div class="page-header-copy">
      <div v-if="eyebrow" class="page-eyebrow">{{ eyebrow }}</div>
      <h1>{{ title }}</h1>
      <p>{{ description }}</p>
    </div>
    <div v-if="$slots.default" class="page-header-extra"><slot /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ eyebrow: string; title: string; description: string }>()
</script>

