<template>
  <a-select
    v-model:value="value"
    :options="choices"
    :disabled="disabled"
    :loading="loading"
    :allow-clear="allowClear"
    :placeholder="placeholder"
    show-search
    option-filter-prop="label"
    class="shared-account-select"
    not-found-content="暂无获授权账号，请联系管理员配置"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
const model = defineModel<string | null | undefined>()
const props = withDefaults(
  defineProps<{
    options: { id: string; name: string }[]
    disabled?: boolean
    loading?: boolean
    allowClear?: boolean
    placeholder?: string
  }>(),
  { disabled: false, loading: false, allowClear: true, placeholder: '选择账号' },
)
// Business callers provide only their authorized directory. This control never fetches all users.
const choices = computed(() => props.options.map((person) => ({ value: String(person.id), label: person.name })))
const value = computed({
  get: () => model.value || undefined,
  set: (value: string | undefined) => {
    model.value = value || ''
  },
})
</script>

<style scoped>
.shared-account-select {
  width: 100%;
  min-width: 0;
}
</style>
