import { http, type ApiEnvelope } from './http'

export interface AuthUser {
  id: number
  username: string
  displayName: string
  isAdmin: boolean
  isEnabled: boolean
  mustChangePassword: boolean
  failedAttempts?: number
  lockedUntil?: string | null
  passwordChangedAt?: string | null
  createdAt?: string | null
}

export interface AuthAudit {
  id: number
  userId?: number | null
  username?: string | null
  action: string
  success: boolean
  ipAddress?: string | null
  detail: Record<string, unknown>
  createdAt?: string | null
}

export const authApi = {
  status: () => http.get<ApiEnvelope<{ enabled: boolean; configured: boolean }>>('/auth/status').then(response => response.data.data),
  login: (username: string, password: string) => http.post<ApiEnvelope<{ user: AuthUser; csrfToken: string }>>('/auth/login', { username, password }).then(response => response.data.data),
  me: () => http.get<ApiEnvelope<{ user: AuthUser; csrfToken: string }>>('/auth/me').then(response => response.data.data),
  logout: () => http.post<ApiEnvelope<null>>('/auth/logout').then(response => response.data.data),
  changePassword: (currentPassword: string, newPassword: string) => http.post<ApiEnvelope<{ csrfToken: string }>>('/auth/change-password', { currentPassword, newPassword }).then(response => response.data.data),
  users: () => http.get<ApiEnvelope<AuthUser[]>>('/admin/users').then(response => response.data.data),
  createUser: (payload: { username: string; displayName: string; initialPassword: string; isAdmin: boolean }) => http.post<ApiEnvelope<AuthUser>>('/admin/users', payload).then(response => response.data.data),
  updateUser: (id: number, payload: { displayName?: string; isAdmin?: boolean; isEnabled?: boolean }) => http.patch<ApiEnvelope<AuthUser>>(`/admin/users/${id}`, payload).then(response => response.data.data),
  resetPassword: (id: number, newPassword: string) => http.post<ApiEnvelope<null>>(`/admin/users/${id}/reset-password`, { newPassword }).then(response => response.data.data),
  audits: (limit = 200) => http.get<ApiEnvelope<AuthAudit[]>>('/admin/audits', { params: { limit } }).then(response => response.data.data),
}
