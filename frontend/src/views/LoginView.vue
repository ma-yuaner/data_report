<template>
  <main class="auth-page">
    <section class="auth-panel">
      <div class="auth-brand-mark"><BarChartOutlined /></div>
      <div class="auth-heading">
        <span>DATA INSIGHT PORTAL</span>
        <h1>登录企业数据中心</h1>
        <p>使用管理员分配的本地账号访问经营分析数据。</p>
      </div>

      <a-alert v-if="configured === false" type="warning" show-icon message="系统尚未初始化管理员账号，请联系部署人员完成首次管理员配置。" />
      <form class="auth-form" @submit.prevent="submit">
        <label>
          <span>用户名</span>
          <a-input v-model:value="username" size="large" autocomplete="username" placeholder="请输入用户名" :maxlength="64" />
        </label>
        <label>
          <span>密码</span>
          <a-input-password v-model:value="password" size="large" autocomplete="current-password" placeholder="请输入密码" />
        </label>
        <a-alert v-if="errorMessage" type="error" show-icon :message="errorMessage" />
        <a-button type="primary" size="large" html-type="submit" block :loading="loading" :disabled="configured === false">登录</a-button>
      </form>
      <div class="auth-security-note">闲置4小时自动退出 · 单次登录最长24小时</div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BarChartOutlined } from '@ant-design/icons-vue'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)
const configured = ref<boolean | null>(null)
const errorMessage = ref('')

onMounted(async () => {
  try {
    configured.value = (await authApi.status()).configured
  } catch {
    configured.value = null
  }
})

const safeRedirect = () => {
  const value = typeof route.query.redirect === 'string' ? route.query.redirect : '/overview'
  return value.startsWith('/') && !value.startsWith('//') ? value : '/overview'
}

const submit = async () => {
  errorMessage.value = ''
  if (!username.value.trim() || !password.value) {
    errorMessage.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    const user = await authStore.login(username.value, password.value)
    await router.replace(user.mustChangePassword ? { name: 'change-password', query: { first: '1' } } : safeRedirect())
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>
