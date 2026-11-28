<template>
  <a-modal
    :open="open"
    :title="title"
    :width="width"
    :wrap-class-name="compact ? 'shared-form-dialog shared-form-dialog--compact' : 'shared-form-dialog'"
    :body-style="{ maxHeight: compact ? undefined : 'calc(100dvh - 200px)', overflowY: 'auto', overscrollBehavior: 'contain' }"
    :confirm-loading="busy"
    :ok-button-props="{ disabled: submitDisabled || busy }"
    :cancel-button-props="{ disabled: busy }"
    :closable="!busy"
    :keyboard="!busy"
    :mask-closable="false"
    :ok-text="okText"
    cancel-text="取消"
    @ok="submit"
    @cancel="cancel"
  >
    <a-alert v-if="error" type="error" :message="error" show-icon style="margin-bottom: 16px" />
    <slot />
  </a-modal>
</template>

<script setup lang="ts">
import { Modal } from 'ant-design-vue'
const props = withDefaults(defineProps<{
  open: boolean
  title: string
  width?: number
  busy?: boolean
  compact?: boolean
  dirty?: boolean
  error?: string
  submitDisabled?: boolean
  okText?: string
}>(), { width: 800, busy: false, dirty: false, error: '', submitDisabled: false, okText: '保存' })
const emit = defineEmits<{ 'update:open': [value: boolean]; submit: []; cancel: [] }>()
let confirming = false
function submit() { if (!props.busy && !props.submitDisabled) emit('submit') }
function close() { emit('update:open', false); emit('cancel') }
function cancel() {
  if (props.busy || confirming) return
  if (!props.dirty) { close(); return }
  confirming = true
  Modal.confirm({
    title: '关闭当前窗口？', content: '有未保存的修改，关闭后不会保存到服务器。',
    okText: '关闭', cancelText: '继续编辑',
    onOk: () => { if (!props.busy) close() },
    afterClose: () => { confirming = false },
  })
}
</script>

<style>
.shared-form-dialog .ant-modal { max-width: calc(100vw - 32px); top: 24px; padding-bottom: 24px; }
.shared-form-dialog .ant-modal-body { padding-right: 4px; scrollbar-gutter: stable; }
.shared-form-dialog .ant-modal-footer { margin-top: 16px; padding-top: 12px; border-top: 1px solid #edf0f5; }
@media (max-height: 560px) { .shared-form-dialog .ant-modal { top: 8px; padding-bottom: 8px; } }
.shared-form-dialog--compact .ant-modal-content {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 48px);
}
.shared-form-dialog--compact .ant-modal-body { min-height: 0; }
.shared-form-dialog--compact .ant-modal-header,
.shared-form-dialog--compact .ant-modal-footer { flex: none; }
@media (max-height: 560px) {
  .shared-form-dialog--compact .ant-modal-content { max-height: calc(100dvh - 16px); padding: 10px 16px; }
  .shared-form-dialog--compact .ant-modal-footer { margin-top: 8px; padding-top: 6px; }
}
</style>
