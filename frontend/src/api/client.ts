import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { ApiError, type ApiErrorShape, type Tokens } from './types'

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
let accessToken: string | null = null
let refreshToken: string | null = localStorage.getItem('refresh_token')
let refreshPromise: Promise<Tokens> | null = null
let onLogout: (() => void) | null = null
export const setLogoutHandler = (handler: () => void) => { onLogout = handler }
export const setTokens = (tokens: Tokens) => { accessToken = tokens.access_token; refreshToken = tokens.refresh_token; localStorage.setItem('refresh_token', tokens.refresh_token) }
export const clearTokens = () => { accessToken = null; refreshToken = null; localStorage.removeItem('refresh_token') }
export const hasRefreshToken = () => Boolean(refreshToken)

const raw = axios.create({ baseURL, headers: { 'Content-Type': 'application/json' } })
const parseError = (error: AxiosError<ApiErrorShape>) => {
  const status = error.response?.status ?? 0
  const payload = error.response?.data?.error
  return new ApiError(status, payload?.message || 'Something went wrong', payload?.code || 'request_error')
}
async function refresh(): Promise<Tokens> {
  if (!refreshToken) throw new ApiError(401, 'Invalid or expired credentials')
  if (!refreshPromise) {
    refreshPromise = raw.post<Tokens>('/auth/refresh', { refresh_token: refreshToken })
      .then(({ data }) => { setTokens(data); return data })
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}
export async function request<T>(config: AxiosRequestConfig, retried = false): Promise<T> {
  try {
    const response = await raw.request<T>({ ...config, headers: { ...config.headers, ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) } })
    return response.data
  } catch (caught) {
    const error = caught instanceof AxiosError ? parseError(caught) : caught
    if (error instanceof ApiError && error.status === 401 && !retried && refreshToken && !String(config.url).includes('/auth/refresh')) {
      try { await refresh(); return request<T>(config, true) } catch { clearTokens(); onLogout?.(); throw new ApiError(401, 'Session expired') }
    }
    throw error
  }
}
export const api = {
  get: <T>(url: string, config?: AxiosRequestConfig) => request<T>({ method: 'GET', url, ...config }),
  post: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) => request<T>({ method: 'POST', url, data, ...config }),
  put: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) => request<T>({ method: 'PUT', url, data, ...config }),
  patch: <T>(url: string, data?: unknown) => request<T>({ method: 'PATCH', url, data }),
  delete: <T = void>(url: string) => request<T>({ method: 'DELETE', url }),
}
