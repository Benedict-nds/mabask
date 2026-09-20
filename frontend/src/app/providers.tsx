"use client"

import { AuthProvider } from "@/app/auth"
import { ThemeProvider } from "@/app/theme"

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>{children}</AuthProvider>
    </ThemeProvider>
  )
}
