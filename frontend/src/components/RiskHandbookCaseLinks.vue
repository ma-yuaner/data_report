<template>
  <div v-if="links.length || error" class="case-rule-links">
    <h3>关联规章制度</h3>
    <p v-if="error">{{ error }}</p>
    <ul v-else>
      <li v-for="item in links" :key="item.policy + '/' + item.section">
        <RouterLink :to="{ name: 'risk-followup-policies', query: { policy: item.policy, section: item.section } }">{{ item.label }}</RouterLink>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { riskFollowup } from '@/api/riskFollowup'
import { handbookOutline } from '@/features/risk/riskHandbook'

const props = defineProps<{ caseId: string }>()
const links = ref<{ policy: string; section: string; label: string }[]>([])
const error = ref('')
watch(() => props.caseId, async (id, _, onCleanup) => {
  let active = true
  onCleanup(() => { active = false })
  links.value = []
  error.value = ''
  try {
    const policies = await riskFollowup.policies()
    if (!active) return
    links.value = policies.flatMap(policy => handbookOutline(policy.handbook?.chapters || [])
      .filter(row => row.node.cases.some(item => item.id === id))
      .map(row => ({ policy: policy.id, section: row.node.id, label: `${policy.policyVersion} · ${row.number} ${row.node.title}` })))
  } catch {
    if (active) error.value = '关联制度读取失败。'
  }
}, { immediate: true })
</script>

<style scoped>
.case-rule-links{margin-top:20px}.case-rule-links h3{margin:0 0 6px}.case-rule-links ul{padding-left:20px}
</style>
