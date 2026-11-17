<template>
  <a-config-provider :theme="{ algorithm: theme.defaultAlgorithm, token: { colorPrimary: '#087e83' } }">
  <div class="login-page">
    <header class="login-brand"><img :src="wordmark" alt="乐游五洲 ONE WORLD TRIP" /></header>
    <main class="login-main">
      <section class="login-story" aria-label="数据中台介绍">
        <h1>连接业务与数据<br />让每一次决策有据可依</h1>
        <p>汇聚经营数据，统一指标口径，协同业务洞察。</p>
        <LoginBrandScene />
        <ul><li>统一数据入口</li><li>清晰指标口径</li><li>按权限访问</li></ul>
      </section>
      <section class="login-panel" aria-labelledby="login-title" :aria-busy="loading">
        <div class="login-product"><img :src="platformIcon" alt="" /><div><strong>数据中台</strong><span>乐游五洲 · 企业数据平台</span></div></div>
        <h2 id="login-title">欢迎登录</h2><p class="login-intro">使用管理员分配的账号访问数据工作台</p>
        <a-alert v-if="configured === false" type="warning" show-icon message="系统尚未初始化管理员账号，请联系部署人员完成首次管理员配置。" role="status" />
        <form class="login-form" @submit.prevent="submit">
          <label for="login-username">用户名</label>
          <a-input id="login-username" v-model:value="username" name="username" size="large" autocomplete="username" placeholder="请输入用户名" :maxlength="64" :disabled="loading" :aria-describedby="errorMessage ? 'login-error' : undefined" />
          <label for="login-password">密码</label>
          <a-input-password id="login-password" v-model:value="password" name="password" size="large" autocomplete="current-password" placeholder="请输入密码" :disabled="loading" :aria-describedby="errorMessage ? 'login-error' : undefined" />
          <label for="login-captcha">图形验证码</label>
          <div class="login-captcha-row">
            <a-input id="login-captcha" v-model:value="captchaValue" name="captcha" size="large" autocomplete="off" autocapitalize="characters" :spellcheck="false" placeholder="请输入验证码" :maxlength="4" :disabled="loading" aria-describedby="captcha-hint" />
            <button class="login-captcha-image" type="button" :disabled="loading || captchaLoading" aria-label="刷新图形验证码" @click="refreshCaptcha">
              <img v-if="challenge" :src="challenge.image" alt="图形验证码，点击刷新" @error="captchaImageFailed" />
              <span v-else>{{ captchaLoading ? '加载中…' : '点击重试' }}</span>
            </button>
          </div>
          <p id="captcha-hint" class="login-hint" :class="{ 'has-error': captchaError }" role="status">{{ captchaError || '看不清？点击图片刷新' }}</p>
          <a-alert v-if="errorMessage" id="login-error" class="login-error" type="error" show-icon :message="errorMessage" role="alert" />
          <a-button class="login-submit" type="primary" size="large" html-type="submit" block :loading="loading" :disabled="configured === false || captchaLoading || !challenge">登录数据中台</a-button>
        </form>
        <p class="login-help">无法登录？<button type="button" :aria-expanded="helpVisible" aria-controls="login-help-detail" @click="helpVisible = !helpVisible">联系管理员</button></p>
        <p v-if="helpVisible" id="login-help-detail" class="login-help-detail" role="status">请通过公司内部渠道联系系统管理员，申请账号或重置密码。</p>
        <p class="login-session"><SafetyOutlined aria-hidden="true" />闲置4小时自动退出 · 单次登录最长24小时</p>
      </section>
    </main>
    <footer class="login-footer">乐游五洲 · 数据中台<span>｜</span>仅限授权人员访问</footer>
  </div>
  </a-config-provider>
</template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SafetyOutlined } from '@ant-design/icons-vue'
import { theme } from 'ant-design-vue'
import LoginBrandScene from '@/components/LoginBrandScene.vue'
import wordmark from '@/assets/brand/company-wordmark.png'
import platformIcon from '@/assets/brand/data-platform.svg'
import { authApi, type LoginChallenge } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const captchaValue = ref('')
const loading = ref(false)
const captchaLoading = ref(false)
const challenge = ref<LoginChallenge | null>(null)
const captchaError = ref('')
const configured = ref<boolean | null>(null)
const errorMessage = ref('')
const helpVisible = ref(false)
let alive = true
onBeforeUnmount(() => { alive = false })
const refreshCaptcha = async () => {
  if (captchaLoading.value) return
  captchaLoading.value = true
  challenge.value = null
  captchaValue.value = ''
  captchaError.value = ''
  try {
    const result = await authApi.captcha()
    if (alive) challenge.value = result
  } catch (error) {
    if (alive) captchaError.value = error instanceof Error ? error.message : '验证码加载失败，请点击重试'
  } finally {
    if (alive) captchaLoading.value = false
  }
}
const captchaImageFailed = () => {
  challenge.value = null
  captchaError.value = '验证码图片加载失败，请点击重试'
}
onMounted(async () => {
  void refreshCaptcha()
  try {
    const status = await authApi.status()
    if (alive) configured.value = status.configured
  } catch {
    if (alive) configured.value = null
  }
})
const safeRedirect = () => {
  const value = typeof route.query.redirect === 'string' ? route.query.redirect : '/home'
  return value.startsWith('/') && !value.startsWith('//') ? value : '/home'
}
const submit = async () => {
  if (loading.value || captchaLoading.value || configured.value === false) return
  errorMessage.value = ''
  if (!username.value.trim() || !password.value) {
    errorMessage.value = '请输入用户名和密码'
    return
  }
  if (!challenge.value || !captchaValue.value) {
    errorMessage.value = '请加载并输入图形验证码'
    return
  }
  loading.value = true
  try {
    const user = await authStore.login(username.value, password.value, challenge.value.challengeId, captchaValue.value)
    if (alive) await router.replace(user.mustChangePassword ? { name: 'change-password', query: { first: '1' } } : safeRedirect())
  } catch (error) {
    if (alive) {
      errorMessage.value = error instanceof Error ? error.message : '登录失败，请重试'
      await refreshCaptcha()
    }
  } finally {
    if (alive) loading.value = false
  }
}
</script>
<style scoped>
.login-page { min-height: 100vh; display: flex; flex-direction: column; background: #f3f9fa; color: #16343d; font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; }
.login-brand { padding: 30px clamp(24px, 5.2vw, 80px) 0; }
.login-brand img { width: 150px; height: auto; display: block; mix-blend-mode: multiply; }
.login-main { flex: 1; width: min(100%, 1320px); margin: 0 auto; padding: 70px 44px 54px; display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-items: center; gap: clamp(40px, 6vw, 96px); }
.login-story h1 { font-size: clamp(28px, 2.8vw, 42px); line-height: 1.5; font-weight: 650; margin: 0 0 24px; color: #16343d; }
.login-story > p { font-size: 15px; color: #617f89; line-height: 1.8; margin: 0; }
.login-story ul { list-style: none; display: flex; flex-wrap: wrap; gap: 12px 32px; padding: 0; margin: 28px 0 0; color: #527680; font-size: 13px; }
.login-story li::before { content: '✓'; color: #087e83; margin-right: 9px; }
.login-panel { background: #fff; border: 1px solid #e0ebed; border-radius: 17px; padding: 38px 42px 24px; width: 100%; max-width: 460px; justify-self: end; }
.login-product { display: flex; gap: 13px; align-items: center; margin-bottom: 28px; }
.login-product img { width: 45px; height: 45px; }
.login-product strong { display: block; font-size: 18px; line-height: 1.5; }
.login-product span { display: block; font-size: 11px; color: #68838d; line-height: 1.8; }
.login-panel h2 { color: #16343d; font-size: 27px; margin: 0 0 8px; font-weight: 650; line-height: 1.5; }
.login-intro { font-size: 13px; color: #617f89; margin: 0 0 28px; line-height: 1.7; }
.login-form label { display: block; font-size: 13px; font-weight: 600; margin: 20px 0 9px; }
.login-form :deep(.ant-input), .login-form :deep(.ant-input-affix-wrapper) { border-color: #cddfe3; border-radius: 7px; font-size: 14px; }
.login-form > :deep(.ant-input), .login-form > :deep(.ant-input-affix-wrapper), .login-captcha-row > :deep(.ant-input) { min-height: 48px; }
.login-form :deep(.ant-input::placeholder) { color: #829ca5; font-size: 13px; }
.login-form :deep(.ant-input:hover), .login-form :deep(.ant-input:focus), .login-form :deep(.ant-input-affix-wrapper:hover), .login-form :deep(.ant-input-affix-wrapper-focused) { border-color: #087e83; }
.login-form :deep(.ant-input:focus), .login-form :deep(.ant-input-affix-wrapper-focused) { box-shadow: 0 0 0 3px #40b3b622; }
.login-captcha-row { display: grid; grid-template-columns: minmax(0, 1fr) 124px; gap: 10px; }
.login-captcha-image { padding: 0; overflow: hidden; min-width: 0; height: 48px; border: 1px solid #c9e2e5; border-radius: 7px; background: #eef8f8; cursor: pointer; color: #527680; font-size: 12px; }
.login-captcha-image img { display: block; width: 100%; height: 100%; object-fit: fill; }
.login-captcha-image:disabled { cursor: wait; opacity: .65; }
.login-hint { color: #68838d; margin: 7px 0 0; font-size: 11px; line-height: 1.7; }
.login-hint.has-error { color: #a82b27; }
.login-error { margin-top: 16px; }
.login-submit.ant-btn { height: 48px; margin-top: 26px; border-radius: 7px; font-size: 14px; font-weight: 600; }
.login-submit.ant-btn-primary:not(:disabled) { background: #087e83; border-color: #087e83; box-shadow: none; }
.login-submit.ant-btn-primary:not(:disabled):hover { background: #066b70; border-color: #066b70; }
.login-help { text-align: center; margin: 20px 0 0; font-size: 12px; color: #68838d; }
.login-help button { padding: 0 0 0 6px; border: 0; background: none; color: #087e83; font: inherit; cursor: pointer; }
.login-help-detail { margin: 10px 0 0; font-size: 12px; color: #527680; line-height: 1.7; }
.login-session { margin: 25px 0 0; padding-top: 18px; border-top: 1px solid #edf3f4; text-align: center; font-size: 10px; line-height: 1.8; color: #68838d; }
.login-session :deep(.anticon) { margin-right: 5px; }
.login-footer { text-align: center; color: #68838d; padding: 16px 20px 28px; font-size: 11px; }
.login-footer span { padding: 0 8px; }
.login-page button:focus-visible { outline: 3px solid #40b3b6; outline-offset: 3px; }
@media (max-width: 1000px) { .login-main { gap: 32px; padding-inline: 32px; } .login-panel { padding-inline: 28px; } .login-story ul { gap: 10px 18px; } }
@media (max-width: 760px) { .login-brand { padding: 24px 24px 0; } .login-brand img { width: 136px; } .login-main { display: block; padding: 32px 20px; } .login-story { display: none; } .login-panel { margin: 0 auto; padding: 30px 24px 24px; } .login-footer { font-size: 10px; } }
@media (max-width: 360px) { .login-panel { padding-inline: 18px; } .login-captcha-row { grid-template-columns: minmax(0, 1fr) 102px; } }
@media (max-height: 740px) and (min-width: 761px) { .login-main { padding-block: 28px; } .login-panel { padding-top: 26px; } }
@media (prefers-reduced-motion: reduce) { .login-page :deep(*) { transition: none !important; animation: none !important; } }
</style>
