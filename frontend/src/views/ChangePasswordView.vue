<template>
  <AuthFrame eyebrow="ACCOUNT SECURITY" :title="firstLogin ? '首次登录，请修改密码' : '修改登录密码'" description="密码至少8位，并同时包含字母和数字。" :busy="loading" compact>
      <template #icon><SafetyOutlined /></template>
      <form class="auth-form" @submit.prevent="submit">
        <div class="auth-field"><label for="current-password">当前密码</label><a-input-password id="current-password" v-model:value="currentPassword" name="current-password" size="large" autocomplete="current-password" :disabled="loading" :aria-describedby="errorMessage ? 'password-error' : undefined" /></div>
        <div class="auth-field"><label for="new-password">新密码</label><a-input-password id="new-password" v-model:value="newPassword" name="new-password" size="large" autocomplete="new-password" :disabled="loading" :aria-describedby="errorMessage ? 'password-error' : undefined" /></div>
        <div class="auth-field"><label for="confirm-password">确认新密码</label><a-input-password id="confirm-password" v-model:value="confirmPassword" name="confirm-password" size="large" autocomplete="new-password" :disabled="loading" :aria-describedby="errorMessage ? 'password-error' : undefined" /></div>
        <a-alert v-if="errorMessage" id="password-error" type="error" show-icon :message="errorMessage" role="alert" />
        <a-button type="primary" size="large" html-type="submit" block :loading="loading">保存新密码</a-button>
        <a-button v-if="!firstLogin" size="large" block :disabled="loading" @click="router.back()">取消</a-button>
        <a-button v-else type="link" block :disabled="loading" @click="signOut">退出登录</a-button>
      </form>
  </AuthFrame>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { SafetyOutlined } from '@ant-design/icons-vue'
import AuthFrame from '@/components/AuthFrame.vue'
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
  if (loading.value) return
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
