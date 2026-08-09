import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, auth, type User } from '@/lib/api'

interface AuthState {
  user: User | null
  /** True until the initial "am I already signed in?" check finishes. */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

/**
 * Holds the signed-in user for the whole app.
 *
 * The session lives in an httpOnly cookie that JavaScript cannot read, so on boot the only way
 * to know whether someone is signed in is to ask the server. That single `/api/auth/me` call is
 * what `loading` covers — rendering routes before it settles would flash the login screen at an
 * already-authenticated user on every refresh.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    auth
      .me()
      .then(setUser)
      .catch((error) => {
        // A 401 here is the normal "not signed in" case, not a failure worth surfacing.
        if (!(error instanceof ApiError) || error.status !== 401) console.error(error)
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setUser((await auth.login(email, password)).user)
  }, [])

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      setUser((await auth.register(email, password, displayName)).user)
    },
    [],
  )

  const logout = useCallback(async () => {
    await auth.logout()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
