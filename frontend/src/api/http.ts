import axios from 'axios'

export interface ApiEnvelope<T> {
  success: boolean
  message: string
  data: T
}

export class ApiError extends Error {
  status?: number
  code?: string

  constructor(message: string, status?: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

let csrfToken = ''
let authFailureHandler: ((error: ApiError) => void) | undefined

export const setCsrfToken = (value: string) => { csrfToken = value }
export const setAuthFailureHandler = (handler: (error: ApiError) => void) => { authFailureHandler = handler }

export const http = axios.create({
  baseURL: '/api',
  timeout: 120_000,
  headers: { Accept: 'application/json' },
})

http.interceptors.request.use((config) => {
  const method = (config.method ?? 'get').toLowerCase()
  if (csrfToken && ['post', 'put', 'patch', 'delete'].includes(method)) {
    config.headers.set('X-CSRF-Token', csrfToken)
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const apiError = new ApiError(
      error.response?.data?.message ?? error.message ?? '请求失败',
      error.response?.status,
      error.response?.data?.code,
    )
    if (apiError.code === 'AUTH_REQUIRED' || apiError.code === 'PASSWORD_CHANGE_REQUIRED') {
      authFailureHandler?.(apiError)
    }
    return Promise.reject(apiError)
  },
)
