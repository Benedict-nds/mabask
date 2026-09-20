"use client"

import { useAuth } from "@/app/auth"

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { loading, user } = useAuth()
  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading workspace…
      </div>
    )
  }
  return <>{children}</>
}
