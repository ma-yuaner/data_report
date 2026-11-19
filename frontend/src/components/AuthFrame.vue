<template>
  <a-config-provider :theme="{ inherit: false, algorithm: theme.defaultAlgorithm, token: { colorPrimary: '#087e83' } }">
    <div class="auth-page">
      <header class="auth-brand"><img :src="wordmark" alt="乐游五洲 ONE WORLD TRIP" /></header>
      <main class="auth-main" :aria-busy="busy">
        <section class="auth-story" aria-label="数据中台介绍">
          <h2>连接业务与数据<br />让每一次决策有据可依</h2>
          <p>汇聚经营数据，统一指标口径，协同业务洞察。</p>
          <LoginBrandScene />
        </section>
        <section class="auth-panel" :class="{ 'auth-panel-compact': compact }" aria-labelledby="auth-title">
          <div class="auth-product"><img :src="platformIcon" alt="" /><div><strong>数据中台</strong><span>乐游五洲 · 企业数据平台</span></div></div>
          <header class="auth-heading">
            <span class="auth-eyebrow">{{ eyebrow }}</span>
            <h1 id="auth-title">{{ title }}</h1>
            <p>{{ description }}</p>
          </header>
          <div v-if="$slots.status" class="auth-status"><slot name="status" /></div>
          <slot />
          <footer v-if="$slots.footer" class="auth-security-note"><slot name="footer" /></footer>
        </section>
      </main>
      <footer class="auth-footer">乐游五洲 · 数据中台<span>｜</span>仅限授权人员访问</footer>
    </div>
  </a-config-provider>
</template>

<script setup lang="ts">
import { theme } from 'ant-design-vue'
import LoginBrandScene from '@/components/LoginBrandScene.vue'
import wordmark from '@/assets/brand/company-wordmark.png'
import platformIcon from '@/assets/brand/data-platform.svg'
withDefaults(defineProps<{
  eyebrow: string
  title: string
  description: string
  busy?: boolean
  compact?: boolean
}>(), { busy: false, compact: false })
</script>

<style scoped>
.auth-page { min-height: 100vh; min-height: 100svh; display: flex; flex-direction: column; color: #16343d; background: #f3f9fa; font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; }
.auth-brand { padding: 30px clamp(24px, 5.2vw, 80px) 0; }
.auth-brand img { display: block; width: 150px; height: auto; mix-blend-mode: multiply; }
.auth-main { box-sizing: border-box; flex: 1; width: min(100%, 1320px); margin: 0 auto; padding: 54px 44px; display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-items: center; gap: clamp(40px, 6vw, 96px); }
.auth-story { min-width: 0; }
.auth-story h2 { font-size: clamp(28px, 2.8vw, 42px); line-height: 1.5; font-weight: 650; margin: 0 0 24px; color: #16343d; }
.auth-story > p { font-size: 15px; color: #617f89; line-height: 1.8; margin: 0; }
.auth-panel { box-sizing: border-box; width: min(456px, 100%); min-width: 0; justify-self: end; padding: 36px 40px; border: 1px solid #e0ebed; border-radius: 17px; background: #fff; }
.auth-panel-compact { width: min(480px, 100%); }
.auth-product { display: flex; gap: 13px; align-items: center; margin-bottom: 24px; }
.auth-product img { width: 45px; height: 45px; }
.auth-product strong { display: block; font-size: 18px; line-height: 1.5; }
.auth-product span { display: block; font-size: 11px; color: #68838d; line-height: 1.8; }
.auth-eyebrow { color: #527680; font-size: 12px; font-weight: 600; letter-spacing: .06em; }
.auth-heading h1 { margin: 8px 0 10px; font-size: 24px; line-height: 1.4; font-weight: 600; overflow-wrap: anywhere; }
.auth-heading p { margin: 0; color: #617f89; font-size: 14px; line-height: 1.75; }
.auth-status { margin-top: 20px; padding: 10px 12px; border: 1px solid #d8ebed; border-radius: 7px; color: #38616b; background: #f0f8f9; font-size: 13px; line-height: 1.75; }
.auth-panel :deep(.auth-form) { margin-top: 24px; display: grid; gap: 20px; }
.auth-panel :deep(.auth-field) { min-width: 0; display: grid; gap: 8px; }
.auth-panel :deep(.auth-field > label) { color: #334155; font-size: 14px; font-weight: 500; }
.auth-panel :deep(.ant-input-affix-wrapper), .auth-panel :deep(.ant-input), .auth-panel :deep(.ant-btn) { border-radius: 7px; font-size: 14px; }
.auth-panel :deep(.ant-input-affix-wrapper) { min-height: 48px; border-color: #cddfe3; }
.auth-panel :deep(.ant-input-affix-wrapper:hover), .auth-panel :deep(.ant-input-affix-wrapper-focused) { border-color: #087e83; }
.auth-panel :deep(.ant-input-affix-wrapper-focused) { box-shadow: 0 0 0 3px #40b3b622; }
.auth-panel :deep(.ant-btn-primary) { min-height: 48px; font-weight: 500; box-shadow: none; }
.auth-panel :deep(.ant-alert-message) { overflow-wrap: anywhere; }
.auth-panel :deep(button:focus-visible), .auth-panel :deep(input:focus-visible) { outline: 2px solid #087e83; outline-offset: 3px; }
.auth-security-note { margin-top: 24px; padding-top: 16px; border-top: 1px solid #edf3f4; color: #68838d; font-size: 13px; line-height: 1.75; text-align: center; overflow-wrap: anywhere; }
.auth-footer { padding: 16px 20px 28px; color: #68838d; font-size: 11px; text-align: center; }
.auth-footer span { padding: 0 8px; }
@media (max-width: 1000px) { .auth-main { gap: 32px; padding-inline: 32px; } .auth-panel { padding-inline: 28px; } }
@media (max-width: 760px) { .auth-brand { padding: 24px 24px 0; } .auth-brand img { width: 136px; } .auth-main { display: block; padding: 32px 20px; } .auth-story { display: none; } .auth-panel { margin: 0 auto; padding: 28px 24px; } }
@media (max-width: 360px) { .auth-panel { padding-inline: 18px; } }
@media (max-height: 740px) and (min-width: 761px) { .auth-main { padding-block: 28px; } }
@media (prefers-reduced-motion: reduce) { .auth-page :deep(*) { transition: none !important; animation: none !important; } }
</style>
