import axios from 'axios'

export interface ApiEnvelope<T> {
  success: boolean
  message: string
  data: T
}

export const http = axios.create({
  baseURL: '/api',
  timeout: 15_000,
  headers: { Accept: 'application/json' },
})

http.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(new Error(error.response?.data?.message ?? error.message ?? '请求失败')),
)

