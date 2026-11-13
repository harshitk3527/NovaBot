import { api, setTokens } from './client'
import type { Tokens, User } from './types'
export const login = async (data: { email: string; password: string }) => { const tokens = await api.post<Tokens>('/auth/login', data); setTokens(tokens); return api.get<User>('/auth/me') }
export const register = (data: { email: string; password: string }) => api.post<User>('/auth/register', data)
export const me = () => api.get<User>('/auth/me')
