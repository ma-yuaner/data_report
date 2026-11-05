<template>
  <AuthFrame eyebrow="DATA INSIGHT PORTAL" title="登录企业数据中心" description="使用管理员分配的本地账号访问经营分析数据。" :busy="loading">
      <template #icon><BarChartOutlined /></template>
      <template v-if="configured === false" #status>
        <a-alert type="warning" show-icon message="系统尚未初始化管理员账号，请联系部署人员完成首次管理员配置。" role="status" />
      </template>
      <form class="auth-form" @submit.prevent="submit">
        <div class="auth-field">
          <label for="login-username">用户名</label>
          <a-input id="login-username" v-model:value="username" name="username" size="large" autocomplete="username" placeholder="请输入用户名" :maxlength="64" :disabled="loading" :aria-describedby="errorMessage ? 'login-error' : undefined">
            <template #prefix><UserOutlined aria-hidden="true" /></template>
          </a-input>
        </div>
        <div class="auth-field">
          <label for="login-password">密码</label>
          <a-input-password id="login-password" v-model:value="password" name="password" size="large" autocomplete="current-password" placeholder="请输入密码" :disabled="loading" :aria-describedby="errorMessage ? 'login-error' : undefined">
            <template #prefix><LockOutlined aria-hidden="true" /></template>
          </a-input-password>
        </div>
        <a-alert v-if="errorMessage" id="login-error" type="error" show-icon :message="errorMessage" role="alert" />
        <a-button type="primary" size="large" html-type="submit" block :loading="loading" :disabled="configured === false">登录</a-button>
      </form>
      <template #footer><SafetyOutlined aria-hidden="true" />闲置4小时自动退出 · 单次登录最长24小时</template>
  </AuthFrame>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BarChartOutlined, LockOutlined, SafetyOutlined, UserOutlined } from '@ant-design/icons-vue'
import AuthFrame from '@/components/AuthFrame.vue'
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
  const value = typeof route.query.redirect === 'string' ? route.query.redirect : '/home'
  return value.startsWith('/') && !value.startsWith('//') ? value : '/home'
}

const submit = async () => {
  if (loading.value || configured.value === false) return
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
