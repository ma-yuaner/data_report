<template>
  <main class="auth-page" :aria-busy="busy">
    <section class="auth-panel" :class="{ 'auth-panel-compact': compact }" aria-labelledby="auth-title">
      <header class="auth-heading">
        <div v-if="$slots.icon" class="auth-brand-mark" aria-hidden="true"><slot name="icon" /></div>
        <span class="auth-eyebrow">{{ eyebrow }}</span>
        <h1 id="auth-title">{{ title }}</h1>
        <p>{{ description }}</p>
      </header>
      <div v-if="$slots.status" class="auth-status"><slot name="status" /></div>
      <slot />
      <footer v-if="$slots.footer" class="auth-security-note"><slot name="footer" /></footer>
    </section>
  </main>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  eyebrow: string
  title: string
  description: string
  busy?: boolean
  compact?: boolean
}>(), { busy: false, compact: false })
</script>

<style scoped>
.auth-page {
  box-sizing: border-box;
  min-height: 100vh;
  min-height: 100svh;
  padding: 40px 24px;
  display: grid;
  place-items: center;
  color: #182235;
  background: radial-gradient(ellipse at 50% 0%, #1b3659 0%, #101d32 65%);
}
.auth-panel {
  box-sizing: border-box;
  width: min(456px, 100%);
  min-width: 0;
  padding: 36px 40px;
  border: 1px solid #e4e9ef;
  border-top: 3px solid #3178f6;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 16px 48px rgba(3, 14, 31, .18);
}
.auth-panel-compact { width: min(480px, 100%); }
.auth-brand-mark {
  width: 48px;
  height: 48px;
  margin-bottom: 20px;
  display: grid;
  place-items: center;
  border: 1px solid #dce8fc;
  border-radius: 10px;
  color: #2c68d7;
  background: #edf4ff;
  font-size: 24px;
}
.auth-eyebrow { color: #42648f; font-size: 12px; font-weight: 600; letter-spacing: .06em; }
.auth-heading h1 { margin: 8px 0 10px; font-size: 24px; line-height: 1.4; font-weight: 600; overflow-wrap: anywhere; }
.auth-heading p { margin: 0; color: #526176; font-size: 14px; line-height: 1.75; }
.auth-status { margin-top: 24px; }
.auth-panel :deep(.auth-form) { margin-top: 24px; display: grid; gap: 20px; }
.auth-panel :deep(.auth-field) { min-width: 0; display: grid; gap: 8px; }
.auth-panel :deep(.auth-field > label) { color: #334155; font-size: 14px; font-weight: 500; }
.auth-panel :deep(.ant-input-affix-wrapper),
.auth-panel :deep(.ant-input),
.auth-panel :deep(.ant-btn) { border-radius: 6px; }
.auth-panel :deep(.ant-input-prefix) { margin-right: 10px; color: #69768a; }
.auth-panel :deep(.ant-btn-primary) { min-height: 44px; font-weight: 500; box-shadow: none; }
.auth-panel :deep(.ant-alert-message) { overflow-wrap: anywhere; }
.auth-panel :deep(button:focus-visible),
.auth-panel :deep(input:focus-visible) { outline: 2px solid #3178f6; outline-offset: 3px; }
.auth-security-note { margin-top: 24px; padding-top: 16px; border-top: 1px solid #e8ecf2; color: #526176; font-size: 13px; line-height: 1.75; text-align: center; overflow-wrap: anywhere; }
.auth-security-note :deep(.anticon) { margin-right: 6px; color: #69768a; }
@media (max-width: 600px) {
  .auth-page { padding: 24px 16px; }
  .auth-panel { padding: 28px 24px; }
  .auth-heading h1 { font-size: 24px; }
}
@media (max-height: 640px) {
  .auth-page { align-items: start; padding-block: 20px; }
  .auth-brand-mark { margin-bottom: 16px; }
}
</style>
