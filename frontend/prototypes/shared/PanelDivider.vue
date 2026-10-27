<template>
  <div class="separator" role="separator" tabindex="0" :aria-label="label"
    aria-orientation="vertical" :aria-valuenow="modelValue" :aria-valuemin="min" :aria-valuemax="max"
    @pointerdown="startResize" @keydown.left.prevent="update(modelValue - 2)"
    @keydown.right.prevent="update(modelValue + 2)" @keydown.home.prevent="update(min)"
    @keydown.end.prevent="update(max)" />
</template>

<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
const props = withDefaults(defineProps<{
  modelValue: number
  min?: number
  max?: number
  label?: string
}>(), { min: 40, max: 70, label: '调整模拟系统和PRD宽度' })
const emit = defineEmits<{ 'update:modelValue': [value: number] }>()
const update = (value: number) => emit('update:modelValue', Math.max(props.min, Math.min(props.max, value)))
let stopResize: (() => void) | undefined
function startResize(event: PointerEvent) {
  if (event.button !== 0) return
  stopResize?.()
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  const move = (ev: PointerEvent) => {
    if (ev.pointerId !== event.pointerId) return
    const box = target.parentElement?.getBoundingClientRect()
    if (box && box.width > 0) update(((ev.clientX - box.left) / box.width) * 100)
  }
  const end = () => {
    target.removeEventListener('pointermove', move)
    target.removeEventListener('pointerup', end)
    target.removeEventListener('pointercancel', end)
    target.removeEventListener('lostpointercapture', end)
    window.removeEventListener('blur', end)
    if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId)
    stopResize = undefined
  }
  target.addEventListener('pointermove', move)
  target.addEventListener('pointerup', end)
  target.addEventListener('pointercancel', end)
  target.addEventListener('lostpointercapture', end)
  window.addEventListener('blur', end)
  stopResize = end
}
onBeforeUnmount(() => stopResize?.())
</script>
