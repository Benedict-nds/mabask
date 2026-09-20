"use client"

import { AppShell } from "@/layouts/AppShell"

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
