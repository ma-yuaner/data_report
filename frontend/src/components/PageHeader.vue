<template>
  <div class="page-header">
    <div>
      <div class="page-eyebrow">{{ eyebrow }}</div>
      <h1>{{ title }}</h1>
      <p>{{ description }}</p>
    </div>
    <div class="page-header-extra"><slot /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ eyebrow: string; title: string; description: string }>()
</script>

