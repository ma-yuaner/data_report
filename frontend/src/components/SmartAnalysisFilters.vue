<template>
  <section class="smart-filter-panel">
    <div class="smart-filter-heading">
      <div><strong>统计范围</strong><span>{{ page === 'detail' ? '三类日期可任选；填写完整OTA订单号精准查询时自动忽略日期条件' : '三类日期可任选一个或多个；已选范围同时生效，结束日期包含当天' }}</span></div>
      <div class="smart-quick-ranges">
        <a-button size="small" @click="preset('today')">今日</a-button>
        <a-button size="small" @click="preset('yesterday')">昨日</a-button>
        <a-button size="small" @click="preset('week')">近7天</a-button>
      </div>
    </div>

    <div class="smart-date-grid">
      <label><span>出票日期（可选）</span><div><a-date-picker v-model:value="pageState.draft.startDate" value-format="YYYY-MM-DD" :locale="dateLocale" /><i>至</i><a-date-picker v-model:value="pageState.draft.endDate" value-format="YYYY-MM-DD" :locale="dateLocale" /></div></label>
      <label><span>首段起飞日期</span><div><a-date-picker v-model:value="pageState.draft.firstDepStart" value-format="YYYY-MM-DD" :locale="dateLocale" /><i>至</i><a-date-picker v-model:value="pageState.draft.firstDepEnd" value-format="YYYY-MM-DD" :locale="dateLocale" /></div></label>
      <label><span>进单日期</span><div><a-date-picker v-model:value="pageState.draft.orderStart" value-format="YYYY-MM-DD" :locale="dateLocale" /><i>至</i><a-date-picker v-model:value="pageState.draft.orderEnd" value-format="YYYY-MM-DD" :locale="dateLocale" /></div></label>
    </div>

    <div class="smart-filter-grid">
      <label v-if="page === 'detail'"><span>OTA订单号</span><a-input v-model:value="pageState.draft.otaOrderNo" allow-clear placeholder="输入完整OTA订单号精准查询" @press-enter="query" /></label>
      <label v-for="item in visibleFilters" :key="item.key"><span>{{ item.label }}</span><a-select v-model:value="pageState.draft[item.key]" allow-clear show-search :filter-option="false" :options="options[item.key] || []" :placeholder="`全部${item.label}`" :loading="optionLoading === item.key" :not-found-content="optionErrors[item.key] || '暂无可选数据'" @search="onSearch(item.key, $event)" @dropdown-visible-change="onDropdown(item.key, $event)" /></label>
    </div>

    <div class="smart-filter-actions">
      <a-segmented v-model:value="pageState.smartType" :options="smartTypes" @change="query" />
      <span v-if="error" class="smart-filter-error">{{ error }}</span>
      <div><a-button @click="reset">重置</a-button><a-button type="primary" :loading="loading" @click="query"><SearchOutlined />查询</a-button></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { DatePicker as ADatePicker } from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { SearchOutlined } from '@ant-design/icons-vue'
import { smartAnalysisApi, type SmartFilters } from '@/api/smartAnalysis'
import { useSmartAnalysisStore, type SmartPage } from '@/stores/smartAnalysis'
import { normalizeSmartAnalysisFilters, validateSmartAnalysisFilters } from '@/utils/smartAnalysisFilterValidation'

const props = defineProps<{ loading?: boolean; page: SmartPage }>()
const emit = defineEmits<{ query: []; reset: [] }>()
const store = useSmartAnalysisStore()
const pageState = store.pages[props.page]
const error = ref('')
const optionLoading = ref('')
const options = reactive<Partial<Record<keyof SmartFilters, { value: string; label: string }[]>>>({})
const optionErrors = reactive<Partial<Record<keyof SmartFilters, string>>>({})
const visibleFilters: { key: keyof SmartFilters; label: string }[] = [
  { key: 'airline', label: '航司' }, { key: 'platform', label: 'OTA平台' },
  { key: 'site', label: 'OTA站点' }, { key: 'policy', label: '政策员' },
  { key: 'depAirport', label: '出发机场' }, { key: 'arrAirport', label: '到达机场' },
  { key: 'depCountry', label: '出发国家' }, { key: 'arrCountry', label: '到达国家' },
  { key: 'profitBand', label: '利润区间' },
]
const smartTypes = [
  { label: '智能整体', value: 'all' }, { label: '智能降舱', value: 'down' },
  { label: '智能废票', value: 'void' },
]

async function loadOptions(field: keyof SmartFilters, search = '') {
  if (['startDate', 'endDate', 'firstDepStart', 'firstDepEnd', 'orderStart', 'orderEnd', 'otaOrderNo'].includes(field)) return
  optionLoading.value = field
  try {
    const result = await smartAnalysisApi.filterOptions({ ...pageState.draft }, field, search)
    options[field] = result.available ? result.options : []
    optionErrors[field] = result.available ? '' : (result.error || '筛选项加载失败')
  } catch {
    options[field] = []
    optionErrors[field] = '筛选项加载失败'
  } finally {
    if (optionLoading.value === field) optionLoading.value = ''
  }
}
function onSearch(field: keyof SmartFilters, value: string) { void loadOptions(field, value) }
function onDropdown(field: keyof SmartFilters, open: boolean) { if (open) void loadOptions(field) }

function query() {
  Object.assign(pageState.draft, normalizeSmartAnalysisFilters(pageState.draft, props.page))
  error.value = validateSmartAnalysisFilters(pageState.draft, props.page)
  if (error.value) return
  store.apply(props.page)
  emit('query')
}
function reset() { error.value = ''; store.reset(props.page); emit('reset') }
function preset(kind: 'today' | 'yesterday' | 'week') { store.setPreset(props.page, kind); query() }
onMounted(() => { for (const field of ['airline', 'platform'] as (keyof SmartFilters)[]) void loadOptions(field) })
</script>

<style scoped>
.smart-filter-panel { margin-bottom: 16px; padding: 18px; border: 1px solid #e4e9f1; border-radius: 12px; background: #fff; box-shadow: 0 5px 18px rgba(28,45,72,.03); }
.smart-filter-heading, .smart-filter-actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.smart-filter-heading > div:first-child { display: grid; gap: 3px; }
.smart-filter-heading strong { color: #344258; font-size: 14px; }
.smart-filter-heading span { color: #8390a2; font-size: 11px; }
.smart-quick-ranges, .smart-filter-actions > div { display: flex; gap: 8px; }
.smart-date-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 16px; }
.smart-date-grid label, .smart-filter-grid label { display: grid; gap: 6px; color: #66748a; font-size: 11px; }
.smart-date-grid label > div { display: flex; align-items: center; gap: 7px; }
.smart-date-grid :deep(.ant-picker) { min-width: 0; width: 100%; }
.smart-date-grid i { color: #8b97a8; font-style: normal; }
.smart-filter-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.smart-filter-grid :deep(.ant-select) { width: 100%; }
.smart-filter-actions { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf0f4; }
.smart-filter-error { flex: 1; color: #c34f5d; font-size: 12px; }
@media (max-width: 1100px) { .smart-date-grid { grid-template-columns: 1fr; } .smart-filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .smart-filter-heading, .smart-filter-actions { align-items: stretch; flex-direction: column; } .smart-filter-grid { grid-template-columns: 1fr; } }
</style>
