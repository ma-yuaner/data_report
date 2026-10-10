<template>
  <main class="auth-page">
    <section class="auth-panel auth-panel-compact">
      <div class="auth-heading">
        <span>ACCOUNT SECURITY</span>
        <h1>{{ firstLogin ? '首次登录，请修改密码' : '修改登录密码' }}</h1>
        <p>密码至少8位，并同时包含字母和数字。</p>
      </div>
      <form class="auth-form" @submit.prevent="submit">
        <label><span>当前密码</span><a-input-password v-model:value="currentPassword" size="large" autocomplete="current-password" /></label>
        <label><span>新密码</span><a-input-password v-model:value="newPassword" size="large" autocomplete="new-password" /></label>
        <label><span>确认新密码</span><a-input-password v-model:value="confirmPassword" size="large" autocomplete="new-password" /></label>
        <a-alert v-if="errorMessage" type="error" show-icon :message="errorMessage" />
        <a-button type="primary" size="large" html-type="submit" block :loading="loading">保存新密码</a-button>
        <a-button v-if="!firstLogin" size="large" block @click="router.back()">取消</a-button>
        <a-button v-else type="link" block @click="signOut">退出登录</a-button>
      </form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMessage = ref('')
const firstLogin = computed(() => route.query.first === '1' || authStore.user?.mustChangePassword)

const submit = async () => {
  errorMessage.value = ''
  if (newPassword.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的新密码不一致'
    return
  }
  loading.value = true
  try {
    await authStore.changePassword(currentPassword.value, newPassword.value)
    message.success('密码修改成功')
    await router.replace('/home')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '密码修改失败'
  } finally {
    loading.value = false
  }
}

const signOut = async () => {
  await authStore.logout()
  await router.replace('/login')
}
</script>
