"use client"

import { createContext, useContext, useEffect, useMemo, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { ApiError, authApi } from "@/lib/api/client"
import { clearTokens, getAccessToken, setTokens } from "@/lib/api/auth/token"
import type { User } from "@/lib/api/types"
import { homeFor } from "@/app/permissions"

type AuthState = {
  user: User | null
  loading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  can: (permission: string) => boolean
}

const AuthContext = createContext<AuthState | null>(null)

const PUBLIC = new Set(["/"])

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      setLoading(false)
      if (!PUBLIC.has(pathname)) router.replace("/")
      return
    }
    authApi
      .me()
      .then(setUser)
      .catch(() => {
        clearTokens()
        setUser(null)
        if (!PUBLIC.has(pathname)) router.replace("/")
      })
      .finally(() => setLoading(false))
  }, [pathname, router])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      error,
      can: (permission) => Boolean(user?.permissions.includes(permission)),
      login: async (email, password) => {
        setError(null)
        try {
          const res = await authApi.login(email, password)
          setTokens(res.tokens.access_token, res.tokens.refresh_token)
          setUser(res.user)
          router.push(homeFor(res.user))
        } catch (err) {
          const message = err instanceof ApiError ? err.message : "Unable to sign in"
          setError(message)
          throw err
        }
      },
      logout: async () => {
        await authApi.logout()
        setUser(null)
        router.replace("/")
      },
    }),
    [user, loading, error, router],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
