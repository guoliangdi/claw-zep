import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { message } from 'antd'

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

export const http = axios.create({ baseURL: API_BASE, timeout: 60000 })

// ---- 全局请求拦截器：自动携带 JWT / X-Tenant-ID / X-Project-ID ----
http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('cz_access_token')
  const tenantId = localStorage.getItem('cz_tenant_id')
  const projectId = localStorage.getItem('cz_project_id')
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  if (tenantId) config.headers.set('X-Tenant-ID', tenantId)
  if (projectId) config.headers.set('X-Project-ID', projectId)
  return config
})

// ---- 响应拦截器：401 跳登录；统一错误提示 ----
let refreshing = false
http.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError<any>) => {
    const status = error.response?.status
    const data = error.response?.data
    if (status === 401) {
      const refresh = localStorage.getItem('cz_refresh_token')
      const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
      if (refresh && !original._retry && !refreshing && !original.url?.includes('/auth/')) {
        original._retry = true
        refreshing = true
        try {
          const r = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: refresh })
          localStorage.setItem('cz_access_token', r.data.access_token)
          localStorage.setItem('cz_refresh_token', r.data.refresh_token)
          refreshing = false
          return http(original)
        } catch {
          refreshing = false
        }
      }
      localStorage.removeItem('cz_access_token')
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login'
      }
    } else {
      const msg = data?.message || data?.detail || error.message || '请求失败'
      message.error(typeof msg === 'string' ? msg : '请求失败')
    }
    return Promise.reject(error)
  },
)
