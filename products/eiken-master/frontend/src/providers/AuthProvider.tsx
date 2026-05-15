'use client'

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useState,
} from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { apiGetMe } from '@/lib/api'
import { clearToken, getToken, isTokenExpired } from '@/lib/auth'
import type { User } from '@/lib/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  logout: () => void
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const PUBLIC_PATHS = new Set(['/login', '/register', '/onboarding'])

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    const token = getToken()
    if (!token || isTokenExpired(token)) {
      clearToken()
      setLoading(false)
      if (!PUBLIC_PATHS.has(pathname)) {
        router.replace('/login')
      }
      return
    }
    apiGetMe()
      .then(setUser)
      .catch(() => {
        clearToken()
        router.replace('/login')
      })
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const logout = () => {
    clearToken()
    setUser(null)
    router.replace('/login')
  }

  return (
    <AuthContext.Provider value={{ user, loading, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
