"use client"

import { useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@/app/auth"
import { ROUTE_PERMISSIONS, homeFor } from "@/app/permissions"

export function RequirePermission({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { can, user } = useAuth()
  const needed = ROUTE_PERMISSIONS[pathname]

  useEffect(() => {
    if (!needed || can(needed)) return
    const home = homeFor(user)
    if (home !== pathname) router.replace(home)
  }, [needed, can, user, router, pathname])

  if (needed && !can(needed)) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        You do not have access to this area.
      </div>
    )
  }
  return <>{children}</>
}
