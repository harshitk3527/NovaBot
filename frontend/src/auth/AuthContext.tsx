import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { clearTokens, hasRefreshToken, setLogoutHandler } from '../api/client'
import { login as loginApi, register as registerApi, me } from '../api/auth'
import type { User } from '../api/types'
interface AuthValue { user: User | null; booting: boolean; login: (email: string, password: string) => Promise<void>; register: (email: string, password: string) => Promise<void>; logout: () => void }
const Context = createContext<AuthValue | null>(null)
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null); const [booting, setBooting] = useState(true); const queryClient = useQueryClient()
  const logout = () => { clearTokens(); setUser(null); queryClient.clear() }
  useEffect(() => { setLogoutHandler(logout); if (hasRefreshToken()) me().then(setUser).catch(logout).finally(() => setBooting(false)); else setBooting(false) }, [])
  const value = useMemo<AuthValue>(() => ({ user, booting, login: async (email, password) => setUser(await loginApi({ email, password })), register: async (email, password) => { await registerApi({ email, password }); setUser(await loginApi({ email, password })) }, logout }), [user, booting])
  return <Context.Provider value={value}>{children}</Context.Provider>
}
export const useAuth = () => { const value = useContext(Context); if (!value) throw new Error('useAuth must be used within AuthProvider'); return value }
