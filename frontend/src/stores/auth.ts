import { defineStore } from 'pinia'
import { authApi, type AuthUser } from '@/api/auth'
import { setCsrfToken } from '@/api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as AuthUser | null,
    initialized: false,
  }),
  actions: {
    apply(user: AuthUser | null, csrfToken = '') {
      this.user = user
      setCsrfToken(csrfToken)
    },
    clear() {
      this.apply(null)
      this.initialized = true
    },
    async fetchMe(force = false) {
      if (this.initialized && !force) return this.user
      try {
        const result = await authApi.me()
        this.apply(result.user, result.csrfToken)
        return result.user
      } catch (error) {
        this.apply(null)
        throw error
      } finally {
        this.initialized = true
      }
    },
    async login(username: string, password: string) {
      const result = await authApi.login(username, password)
      this.apply(result.user, result.csrfToken)
      this.initialized = true
      return result.user
    },
    async logout() {
      try {
        await authApi.logout()
      } finally {
        this.clear()
      }
    },
    async changePassword(currentPassword: string, newPassword: string) {
      const result = await authApi.changePassword(currentPassword, newPassword)
      setCsrfToken(result.csrfToken)
      await this.fetchMe(true)
    },
  },
})
