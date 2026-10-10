import { http, type ApiEnvelope } from './http'

export interface BusinessRole {
  code: string
  name: string
  description: string
  isActive?: boolean
  userCount?: number
  menuCodes?: string[]
  permissions?: string[]
  dataScope?: 'ALL'
}

export interface MenuPermission {
  code: string
  name: string
  description: string
}

export interface FunctionPermission {
  code: string
  name: string
  description: string
  menuCode: string
}

export interface RolePayload {
  roleCode?: string
  name: string
  description: string
  isActive: boolean
  menuCodes: string[]
  permissions: string[]
}

export interface AuthUser {
  id: number
  username: string
  email: string
  displayName: string
  isAdmin: boolean
  isEnabled: boolean
  mustChangePassword: boolean
  failedAttempts?: number
  lockedUntil?: string | null
  passwordChangedAt?: string | null
  createdAt?: string | null
  businessRoles: BusinessRole[]
  permissions: string[]
  rbacConfigured: boolean
  menuCodes: string[]
  legacyMenuCodes?: string[]
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
  businessRoles: () => http.get<ApiEnvelope<BusinessRole[]>>('/admin/business-roles').then(response => response.data.data),
  roles: () => http.get<ApiEnvelope<BusinessRole[]>>('/admin/roles').then(response => response.data.data),
  permissionCatalog: () => http.get<ApiEnvelope<FunctionPermission[]>>('/admin/permission-catalog').then(response => response.data.data),
  menuCatalog: () => http.get<ApiEnvelope<MenuPermission[]>>('/admin/menu-catalog').then(response => response.data.data),
  createUser: (payload: { username: string; email: string; displayName: string; initialPassword: string; isAdmin: boolean; roleCodes: string[] }) => http.post<ApiEnvelope<AuthUser>>('/admin/users', payload).then(response => response.data.data),
  createRole: (payload: RolePayload) => http.post<ApiEnvelope<BusinessRole>>('/admin/roles', payload).then(response => response.data.data),
  updateRole: (code: string, payload: RolePayload) => http.put<ApiEnvelope<BusinessRole>>(`/admin/roles/${code}`, payload).then(response => response.data.data),
  updateUser: (id: number, payload: { displayName?: string; email?: string; isAdmin?: boolean; isEnabled?: boolean }) => http.patch<ApiEnvelope<AuthUser>>(`/admin/users/${id}`, payload).then(response => response.data.data),
  resetPassword: (id: number, newPassword: string) => http.post<ApiEnvelope<null>>(`/admin/users/${id}/reset-password`, { newPassword }).then(response => response.data.data),
  updateBusinessRoles: (id: number, roleCodes: string[]) => http.put<ApiEnvelope<AuthUser>>(`/admin/users/${id}/business-roles`, { roleCodes }).then(response => response.data.data),
  updateMenus: (id: number, menuCodes: string[]) => http.put<ApiEnvelope<AuthUser>>(`/admin/users/${id}/menus`, { menuCodes }).then(response => response.data.data),
  audits: (limit = 200) => http.get<ApiEnvelope<AuthAudit[]>>('/admin/audits', { params: { limit } }).then(response => response.data.data),
}
