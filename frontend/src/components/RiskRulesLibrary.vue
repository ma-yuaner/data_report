<template>
  <section class="rules-layout">
    <div class="rule-directory"><div class="directory-heading"><h2>规章制度</h2><a-button v-if="canManageTypes" type="primary" @click="create">登记规则</a-button></div><a-input v-model:value="query" placeholder="搜索规则名称或适用范围" allow-clear /><a-spin :spinning="loading"><button v-for="rule in filtered" :key="rule.id" class="rule-entry" :class="{ selected: active?.id === rule.id }" @click="active = rule"><strong>{{ rule.name }}</strong><span>{{ rule.policyVersion }} · {{ rule.start }} 起生效</span></button><a-empty v-if="!loading && !filtered.length" description="暂无匹配规则" /></a-spin></div>
    <article v-if="active" class="rule-document"><header><span class="muted">规章制度 / 规则版本 {{ active.policyVersion }}</span><h1>{{ active.name }}</h1><p>适用日期：{{ active.start }} 至 {{ active.end }}</p><p>适用范围：{{ active.scope }}</p></header><div class="document-content">{{ active.basis }}</div><footer>以已登记版本为执行依据；历史版本保留，修订请登记新版本。</footer></article>
    <article v-else class="rule-document"><a-empty description="选择左侧规则查看正文" /></article>
  </section>
  <a-alert v-if="error" type="error" show-icon :message="error" />
  <FormDialog :open="open" title="登记规章制度版本" :busy="busy" :dirty="true" :error="saveError" @submit="save" @cancel="open = false">
    <label>规则名称<a-input v-model:value="draft.name" :maxlength="100" /></label><label>版本<a-input v-model:value="draft.policyVersion" :maxlength="60" placeholder="例如 V1" /></label><div class="two"><label>生效日起<DateField v-model="draft.start" /></label><label>生效日止<DateField v-model="draft.end" /></label></div><label>适用范围<a-textarea v-model:value="draft.scope" :maxlength="1000" :rows="2" /></label><label>规则正文<a-textarea v-model:value="draft.basis" :maxlength="20000" :rows="14" show-count placeholder="写清适用场景、执行规则、特殊情况和依据；修订登记新版本" /></label>
  </FormDialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Alert as AAlert, Button as AButton, Empty as AEmpty, Input as AInput, Spin as ASpin, message } from 'ant-design-vue'
import FormDialog from '@/components/FormDialog.vue'
import DateField from '@/components/DateField.vue'
import { riskFollowup, reviewKey, type ReviewPolicy } from '@/api/riskFollowup'
import { useRiskPermissions } from '@/composables/useRiskPermissions'
const ATextarea = AInput.TextArea
const { canManageTypes } = useRiskPermissions()
const loading = ref(false), busy = ref(false), open = ref(false), error = ref(''), saveError = ref(''), query = ref('')
const rules = ref<ReviewPolicy[]>([]), active = ref<ReviewPolicy>()
const draft = reactive({ name: '', policyVersion: '', start: '', end: '', scope: '', basis: '' })
const filtered = computed(() => rules.value.filter(r => `${r.name} ${r.scope}`.includes(query.value.trim())))
let alive = true, requestId = ''
onBeforeUnmount(() => { alive = false })
onMounted(load)
async function load() { loading.value = true; error.value = ''; try { const value = await riskFollowup.policies(); if (alive) { rules.value = value; active.value = value.find(r => r.id === active.value?.id) || value[0] } } catch (e) { if (alive) error.value = e instanceof Error ? e.message : '规则读取失败' } finally { if (alive) loading.value = false } }
function create() { Object.assign(draft, { name: '', policyVersion: '', start: '', end: '', scope: '', basis: '' }); requestId = reviewKey(); saveError.value = ''; open.value = true }
async function save() { if (busy.value) return; busy.value = true; saveError.value = ''; try { const rule = await riskFollowup.createPolicy({ ...draft, ruleDocument: true, requestId }); active.value = rule; open.value = false; await load(); message.success('规则版本已登记') } catch (e) { saveError.value = e instanceof Error ? e.message : '规则保存失败，内容已保留' } finally { busy.value = false } }
</script>
<style scoped>
.rules-layout{display:grid;grid-template-columns:minmax(240px,300px) minmax(0,1fr);gap:24px;align-items:start}.rule-directory{padding:20px;background:white;border:1px solid #e4e9ef;border-radius:8px}.directory-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.directory-heading h2{font-size:18px;margin:0}.rule-entry{display:grid;gap:6px;width:100%;padding:16px 10px;border:0;border-bottom:1px solid #edf0f4;text-align:left;background:white;cursor:pointer;font:inherit;overflow-wrap:anywhere}.rule-entry span{font-size:12px;color:#738298}.rule-entry.selected{background:#eef5ff;border-left:3px solid #2c68d7}.rule-document{min-height:560px;padding:40px 48px;background:white;border:1px solid #e4e9ef;max-width:900px;overflow-wrap:anywhere}.rule-document header{padding-bottom:24px;border-bottom:1px solid #e4e9ef}.rule-document h1{font-size:26px;margin:18px 0}.document-content{white-space:pre-wrap;line-height:1.9;padding:28px 0;font-size:15px}.rule-document footer,.muted{color:#738298;font-size:12px}label{display:grid;gap:8px;margin:16px 0}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:900px){.rules-layout{grid-template-columns:1fr}.rule-document{padding:24px}.two{grid-template-columns:1fr}}
</style>
