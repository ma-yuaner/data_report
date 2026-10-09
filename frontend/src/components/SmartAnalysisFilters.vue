<template>
  <section class="smart-filter-panel">
    <div class="smart-filter-heading">
      <div><strong>统计范围</strong><span>三个日期范围与业务条件同时生效，结束日期包含当天</span></div>
      <div class="smart-quick-ranges">
        <a-button size="small" @click="preset('today')">今日</a-button>
        <a-button size="small" @click="preset('yesterday')">昨日</a-button>
        <a-button size="small" @click="preset('week')">近7天</a-button>
      </div>
    </div>

    <div class="smart-date-grid">
      <label><span>出票日期</span><div><a-date-picker v-model:value="store.draft.startDate" value-format="YYYY-MM-DD" :locale="dateLocale" :allow-clear="false" /><i>至</i><a-date-picker v-model:value="store.draft.endDate" value-format="YYYY-MM-DD" :locale="dateLocale" :allow-clear="false" /></div></label>
      <label><span>首段起飞日期</span><div><a-date-picker v-model:value="store.draft.firstDepStart" value-format="YYYY-MM-DD" :locale="dateLocale" /><i>至</i><a-date-picker v-model:value="store.draft.firstDepEnd" value-format="YYYY-MM-DD" :locale="dateLocale" /></div></label>
      <label><span>进单日期</span><div><a-date-picker v-model:value="store.draft.orderStart" value-format="YYYY-MM-DD" :locale="dateLocale" /><i>至</i><a-date-picker v-model:value="store.draft.orderEnd" value-format="YYYY-MM-DD" :locale="dateLocale" /></div></label>
    </div>

    <div class="smart-filter-grid">
      <label v-for="item in primaryFilters" :key="item.key"><span>{{ item.label }}</span><a-select v-model:value="store.draft[item.key]" allow-clear show-search :filter-option="false" :options="options[item.key] || []" :placeholder="`全部${item.label}`" :loading="optionLoading === item.key" @search="onSearch.bind(null, item.key)" @dropdownVisibleChange="onDropdown.bind(null, item.key)" /></label>
    </div>

    <details class="smart-advanced-filter">
      <summary>更多筛选条件</summary>
      <div class="smart-filter-grid">
        <label v-for="item in advancedFilters" :key="item.key"><span>{{ item.label }}</span><a-select v-model:value="store.draft[item.key]" allow-clear show-search :filter-option="false" :options="options[item.key] || []" :placeholder="`全部${item.label}`" :loading="optionLoading === item.key" @search="onSearch.bind(null, item.key)" @dropdownVisibleChange="onDropdown.bind(null, item.key)" /></label>
      </div>
    </details>

    <div class="smart-filter-actions">
      <a-segmented v-model:value="store.smartType" :options="smartTypes" @change="query" />
      <span v-if="error" class="smart-filter-error">{{ error }}</span>
      <div><a-button @click="reset">重置</a-button><a-button type="primary" :loading="loading" @click="query"><SearchOutlined />查询</a-button></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { DatePicker as ADatePicker } from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { SearchOutlined } from '@ant-design/icons-vue'
import { smartAnalysisApi, type SmartFilters } from '@/api/smartAnalysis'
import { useSmartAnalysisStore } from '@/stores/smartAnalysis'

defineProps<{ loading?: boolean }>()
const emit = defineEmits<{ query: []; reset: [] }>()
const store = useSmartAnalysisStore()
const error = ref('')
const optionLoading = ref('')
const options = reactive<Partial<Record<keyof SmartFilters, { value: string; label: string }[]>>>({})
const primaryFilters: { key: keyof SmartFilters; label: string }[] = [
  { key: 'airline', label: '航司' }, { key: 'platform', label: 'OTA平台' },
  { key: 'site', label: 'OTA站点' }, { key: 'policy', label: '政策员' },
]
const advancedFilters: { key: keyof SmartFilters; label: string }[] = [
  { key: 'depAirport', label: '出发机场' }, { key: 'arrAirport', label: '到达机场' },
  { key: 'depCountry', label: '出发国家' }, { key: 'arrCountry', label: '到达国家' },
  { key: 'department', label: '部门' }, { key: 'ageType', label: '乘客类型' },
  { key: 'profitBand', label: '利润区间' },
]
const smartTypes = [
  { label: '智能整体', value: 'all' }, { label: '智能降舱', value: 'down' },
  { label: '智能废票', value: 'void' },
]

async function loadOptions(field: keyof SmartFilters, search = '') {
  if (['startDate', 'endDate', 'firstDepStart', 'firstDepEnd', 'orderStart', 'orderEnd'].includes(field)) return
  optionLoading.value = field
  try {
    const result = await smartAnalysisApi.filterOptions({ ...store.draft }, field, search)
    options[field] = result.options
  } catch {
    options[field] = []
  } finally {
    if (optionLoading.value === field) optionLoading.value = ''
  }
}
function onSearch(field: keyof SmartFilters, value: string) { void loadOptions(field, value) }
function onDropdown(field: keyof SmartFilters, open: boolean) { if (open) void loadOptions(field) }

function validate() {
  if (!store.draft.startDate || !store.draft.endDate) return '请选择出票开始和结束日期。'
  if (store.draft.startDate > store.draft.endDate) return '出票开始日期不能晚于结束日期。'
  if (store.draft.firstDepStart && store.draft.firstDepEnd && store.draft.firstDepStart > store.draft.firstDepEnd) return '首段起飞开始日期不能晚于结束日期。'
  if (store.draft.orderStart && store.draft.orderEnd && store.draft.orderStart > store.draft.orderEnd) return '进单开始日期不能晚于结束日期。'
  return ''
}

function query() {
  error.value = validate()
  if (error.value) return
  store.apply()
  emit('query')
}
function reset() { error.value = ''; store.reset(); emit('reset') }
function preset(kind: 'today' | 'yesterday' | 'week') { store.setPreset(kind); query() }
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
.smart-advanced-filter { margin-top: 13px; padding-top: 12px; border-top: 1px solid #edf0f4; }
.smart-advanced-filter summary { width: max-content; cursor: pointer; color: #4776bd; font-size: 12px; }
.smart-filter-actions { margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf0f4; }
.smart-filter-error { flex: 1; color: #c34f5d; font-size: 12px; }
@media (max-width: 1100px) { .smart-date-grid { grid-template-columns: 1fr; } .smart-filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .smart-filter-heading, .smart-filter-actions { align-items: stretch; flex-direction: column; } .smart-filter-grid { grid-template-columns: 1fr; } }
</style>
