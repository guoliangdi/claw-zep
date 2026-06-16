import { create } from 'zustand'
import type { CurrentUser } from '@/types'
import { authApi } from '@/api'

interface AuthState {
  user: CurrentUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  loadMe: () => Promise<void>
  logout: () => void
  hasPermission: (code: string) => boolean
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: false,
  login: async (email, password) => {
    const tok = await authApi.login(email, password)
    localStorage.setItem('cz_access_token', tok.access_token)
    localStorage.setItem('cz_refresh_token', tok.refresh_token)
    const me = await authApi.me()
    if (me.tenant_id) localStorage.setItem('cz_tenant_id', me.tenant_id)
    set({ user: me })
  },
  loadMe: async () => {
    set({ loading: true })
    try {
      const me = await authApi.me()
      if (me.tenant_id) localStorage.setItem('cz_tenant_id', me.tenant_id)
      set({ user: me })
    } finally {
      set({ loading: false })
    }
  },
  logout: () => {
    localStorage.removeItem('cz_access_token')
    localStorage.removeItem('cz_refresh_token')
    localStorage.removeItem('cz_project_id')
    set({ user: null })
  },
  hasPermission: (code: string) => {
    const u = get().user
    if (!u) return false
    if (u.system_role === 'super_admin') return true
    if (u.permissions.includes(code)) return true
    const resource = code.split(':')[0]
    return u.permissions.includes(`${resource}:*`) || u.permissions.includes('*')
  },
}))
