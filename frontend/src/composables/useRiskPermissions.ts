import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

export function useRiskPermissions() {
  const auth = useAuthStore()
  const can = (action: string) => Boolean(auth.user?.isAdmin || (
    auth.user?.menuCodes?.includes('risk.verification') &&
    auth.user?.permissions?.includes('risk.verification.view') &&
    auth.user?.permissions?.includes(`risk.verification.${action}`)
  ))
  return {
    canView: computed(() => can('view')),
    canCheck: computed(() => can('check')),
    canReview: computed(() => can('review')),
    canManageTypes: computed(() => can('types.manage')),
    canPublish: computed(() => can('knowledge.publish')),
  }
}
