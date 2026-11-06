<template>
  <section class="review-panel">
    <div class="review-heading"><h3>人工核实记录</h3><a-tag v-if="context" :color="context.stale || context.review?.conclusion === 'unknown' ? 'orange' : context.review?.conclusion === 'problem' ? 'red' : 'blue'">{{ reviewStatus(context) }}</a-tag></div>
    <a-alert v-if="error" type="error" show-icon :message="error" /><a-button v-if="error" :loading="busy" @click="load">重新读取人工记录</a-button>
    <a-alert v-if="context?.stale" type="warning" show-icon message="证据已变化，原人工结论待重新核实" />
    <template v-if="context?.review"><p><a-tag :color="context.stale ? 'orange' : 'blue'">{{ conclusions[context.review.conclusion] }}{{ context.stale ? '（历史结论）' : '' }}</a-tag>{{ context.review.reason }}</p><p><a-tag v-if="context.review.firstSeen">首次出现</a-tag><a-tag v-if="context.review.special">特殊案例</a-tag>{{ context.review.specialReason }}</p><p class="muted">{{ formatDateTimeDisplay(context.review.at) }} · 操作账号 {{ context.review.actor }}</p><router-link v-if="context.review.caseId" :to="`/risk-followup/cases?case=${context.review.caseId}`">进入关联案例跟进</router-link></template>
    <p v-else-if="context" class="muted">尚无人工核实结论。可根据当前证据完成人工判断。</p>
    <details v-if="context?.events?.length"><summary>查看人工核实历史</summary><p v-for="(event, i) in context.events" :key="i">{{ formatDateTimeDisplay(event.at) }} · {{ conclusions[event.after.conclusion || ''] }} · {{ event.note }} · 账号 {{ event.actor }}</p><p v-if="context.eventsTruncated">仅展示最近100条，历史未删除</p></details>
    <div class="review-action"><a-button v-if="canReview" type="primary" size="large" :loading="busy" :disabled="!context" @click="open = true">人工核实</a-button><span v-else class="muted">当前账号没有人工核实权限</span></div>
    <RiskReviewForm :open="open" :orders="[{ orderId, issueDate }]" @close="open = false" @saved="reload" />
  </section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Alert as AAlert, Button as AButton, Tag as ATag } from 'ant-design-vue'
import { riskFollowup, conclusions, reviewStatus, type ReviewContext } from '@/api/riskFollowup'
import { useRiskPermissions } from '@/composables/useRiskPermissions'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
import RiskReviewForm from './RiskReviewForm.vue'
const { canReview } = useRiskPermissions()
const props = defineProps<{ orderId: string; issueDate: string }>()
const emit = defineEmits<{ changed: []; 'busy-change': [boolean] }>()
const context = ref<ReviewContext>(), error = ref(''), open = ref(false), busy = ref(false)
let alive = true
watch(open, value => emit('busy-change', value))
onBeforeUnmount(() => { alive = false })
onMounted(load)
async function load() { busy.value = true; error.value = ''; try { const value = await riskFollowup.order(props.orderId, props.issueDate); if (alive) context.value = value } catch (e) { if (alive) error.value = e instanceof Error ? e.message : '人工记录读取失败' } finally { if (alive) busy.value = false } }
async function reload() { await load(); emit('changed') }
</script>
<style scoped>.review-panel{border:1px solid #dce6f5;border-radius:6px;padding:18px;background:#fafcff}.review-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.review-heading h3{margin:0}.review-action{display:flex;justify-content:center;border-top:1px solid #e7edf5;margin-top:16px;padding-top:20px}.review-action .ant-btn{min-width:160px}.review-panel p{overflow-wrap:anywhere;white-space:pre-wrap}.muted{font-size:12px;color:#738298}</style>
