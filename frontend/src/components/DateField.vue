<template>
  <a-date-picker
    v-model:value="value"
    :locale="locale"
    :value-format="withTime ? 'YYYY-MM-DDTHH:mm' : 'YYYY-MM-DD'"
    :format="withTime ? 'YYYY-MM-DD HH:mm' : 'YYYY-MM-DD'"
    :show-time="withTime ? { format: 'HH:mm' } : false"
    :allow-clear="allowClear"
    :disabled="disabled"
    :placeholder="placeholder || (withTime ? '选择日期与时间' : '选择日期')"
    class="shared-date-field"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { DatePicker as ADatePicker } from 'ant-design-vue'
import locale from 'ant-design-vue/es/date-picker/locale/zh_CN'
const model = defineModel<string | null | undefined>()
withDefaults(defineProps<{ withTime?: boolean; allowClear?: boolean; disabled?: boolean; placeholder?: string }>(), {
  withTime: false, allowClear: true, disabled: false, placeholder: '',
})
// Calendar strings remain business wall time. Never convert via browser timezone/UTC.
const value = computed({ get: () => model.value || undefined, set: (value: string | null | undefined) => { model.value = value || '' } })
</script>

<style scoped>
.shared-date-field { width: 100%; min-width: 0; }
</style>
