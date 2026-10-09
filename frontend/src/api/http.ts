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
const requestStartedAt = new WeakMap<object, number>()

export const setCsrfToken = (value: string) => { csrfToken = value }
export const getCsrfToken = () => csrfToken
export const setAuthFailureHandler = (handler: (error: ApiError) => void) => { authFailureHandler = handler }

function publishApiResult(config: object & { url?: string; method?: string }, status: number, success: boolean, errorCode?: string, emptyResult = false) {
  if (typeof window === 'undefined' || !config.url || config.url.includes('/telemetry/')) return
  const startedAt = requestStartedAt.get(config) ?? performance.now()
  window.dispatchEvent(new CustomEvent('data-report:api-result', { detail: {
    apiPath: config.url.split('?')[0], method: (config.method ?? 'get').toUpperCase(),
    statusCode: status, success, emptyResult, errorCode: errorCode ?? '',
    durationMs: Math.max(0, Math.round(performance.now() - startedAt)),
  } }))
}

export const http = axios.create({
  baseURL: '/api',
  timeout: 120_000,
  headers: { Accept: 'application/json' },
})

http.interceptors.request.use((config) => {
  requestStartedAt.set(config, performance.now())
  const method = (config.method ?? 'get').toLowerCase()
  if (csrfToken && ['post', 'put', 'patch', 'delete'].includes(method)) {
    config.headers.set('X-CSRF-Token', csrfToken)
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    const payload = response.data?.data
    const emptyResult = payload?.available === true && (
      (typeof payload?.total === 'number' && payload.total === 0)
      || (Array.isArray(payload?.rows) && payload.rows.length === 0)
      || (Array.isArray(payload?.comparison) && payload.comparison.length === 0)
    )
    publishApiResult(response.config, response.status, true, undefined, emptyResult)
    return response
  },
  (error) => {
    const apiError = new ApiError(
      error.response?.data?.message ?? error.message ?? '请求失败',
      error.response?.status,
      error.response?.data?.code,
    )
    if (apiError.code === 'AUTH_REQUIRED' || apiError.code === 'PASSWORD_CHANGE_REQUIRED') {
      authFailureHandler?.(apiError)
    }
    if (error.config) publishApiResult(error.config, error.response?.status ?? 0, false, apiError.code)
    return Promise.reject(apiError)
  },
)
