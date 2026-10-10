<template>
  <div class="placement-field" :class="{ 'is-required': required, 'is-submission': state === '提交必填' }">
    <div class="placement-field__heading">
      <span class="placement-field__label">{{ label }}</span>
      <span class="placement-field__state">{{ required ? '必填' : state }}</span>
    </div>
    <div class="placement-field__control">
      <slot />
    </div>
    <p v-if="hint" class="placement-field__hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  label: string
  required?: boolean
  hint?: string
  state?: string
}>(), {
  required: false,
  hint: '',
  state: '选填',
})
</script>

<style scoped>
.placement-field {
  min-width: 0;
  padding: 11px;
  border: 1px solid #e0e6ef;
  border-radius: 9px;
  background: #f8fafc;
  transition: border-color .16s ease, box-shadow .16s ease, background .16s ease;
}
.placement-field:hover {
  border-color: #bfd0e8;
  background: #fbfdff;
}
.placement-field:focus-within {
  border-color: #78a2dc;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(40, 103, 183, .09);
}
.placement-field__heading {
  display: flex;
  min-height: 22px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 7px;
}
.placement-field__label {
  overflow: hidden;
  color: #263750;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.placement-field__state {
  flex: none;
  padding: 2px 7px;
  border: 1px solid #dfe5ee;
  border-radius: 999px;
  color: #8995a7;
  background: #fff;
  font-size: 10px;
  line-height: 1.35;
}
.placement-field.is-required .placement-field__state {
  border-color: #f5c2c7;
  color: #c43f4f;
  background: #fff6f7;
}
.placement-field.is-submission .placement-field__state {
  border-color: #f1d18b;
  color: #a46408;
  background: #fff9e9;
}
.placement-field__control :deep(.ant-input),
.placement-field__control :deep(.ant-input-number),
.placement-field__control :deep(.ant-picker),
.placement-field__control :deep(.ant-select) {
  width: 100%;
}
.placement-field__control :deep(.ant-input),
.placement-field__control :deep(.ant-picker),
.placement-field__control :deep(.ant-input-number),
.placement-field__control :deep(.ant-select-selector) {
  min-height: 35px;
  border-color: #d8e0eb !important;
  border-radius: 7px !important;
  background: #fff !important;
  box-shadow: none !important;
}
.placement-field__control :deep(.ant-input-number-input) { height: 33px; }
.placement-field__control :deep(textarea.ant-input) {
  min-height: auto;
  padding-top: 9px;
  line-height: 1.65;
}
.placement-field__hint {
  min-height: 16px;
  margin: 6px 0 0;
  color: #8b96a8;
  font-size: 10px;
  line-height: 1.55;
}
@media (max-width: 600px) {
  .placement-field { padding: 11px; }
}
</style>
