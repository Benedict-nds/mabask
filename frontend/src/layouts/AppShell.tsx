"use client"

import { AppSidebar } from "@/components/app-sidebar"
import { RequireAuth } from "@/app/RequireAuth"
import { RequirePermission } from "@/app/RequirePermission"

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <RequirePermission>
        <div className="flex min-h-screen bg-background">
          <AppSidebar />
          <div className="flex min-w-0 flex-1 flex-col">{children}</div>
        </div>
      </RequirePermission>
    </RequireAuth>
  )
}
