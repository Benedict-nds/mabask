"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Image from "next/image"
import { Boxes, Mail, Lock, ArrowRight, ShieldCheck, Sparkles, Eye, EyeOff, Sun, Moon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth-context"
import { useTheme } from "@/app/theme"
import { homeFor } from "@/app/permissions"
import { ApiError } from "@/lib/api/client"

export default function LoginPage() {
  const { login, loading, user } = useAuth()
  const { resolved, setTheme } = useTheme()
  const router = useRouter()
  const [showPw, setShowPw] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!loading && user) router.replace(homeFor(user))
  }, [loading, user, router])

  if (!loading && user) return null

  return (
    <main className="flex min-h-screen bg-background">
      <div className="flex w-full flex-col justify-between px-6 py-8 md:px-12 lg:w-[46%] lg:px-16">
        <div className="flex items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <Boxes className="size-5" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold">AetherQore</p>
              <p className="text-[11px] text-muted-foreground">Pharmacy OS</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setTheme(resolved === "dark" ? "light" : "dark")}
            className="flex size-9 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={resolved === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {resolved === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>

        <div className="mx-auto w-full max-w-sm py-10">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-foreground">
            <Sparkles className="size-3" /> AI-native pharmacy operations
          </span>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-balance">Welcome back</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            Sign in to your pharmacy workspace on this computer. Inventory, sales, and reports work without internet.
          </p>

          <form
            className="mt-8 flex flex-col gap-4"
            onSubmit={async (e) => {
              e.preventDefault()
              setSubmitting(true)
              setError(null)
              try {
                await login(email, password)
              } catch (err) {
                setError(err instanceof ApiError ? err.message : "Unable to sign in")
              } finally {
                setSubmitting(false)
              }
            }}
          >
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-sm font-medium">Email</label>
              <div className="flex h-11 items-center gap-2.5 rounded-xl border border-border bg-card px-3.5 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20">
                <Mail className="size-4 text-muted-foreground" />
                <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="h-full flex-1 bg-transparent text-sm outline-none" placeholder="you@pharmacy.com" />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="text-sm font-medium">Password</label>
              </div>
              <div className="flex h-11 items-center gap-2.5 rounded-xl border border-border bg-card px-3.5 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20">
                <Lock className="size-4 text-muted-foreground" />
                <input id="password" type={showPw ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} required className="h-full flex-1 bg-transparent text-sm outline-none" placeholder="••••••••" />
                <button type="button" onClick={() => setShowPw((s) => !s)} className="text-muted-foreground hover:text-foreground" aria-label="Toggle password visibility">
                  {showPw ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
            )}

            <Button size="lg" className="mt-1 h-11 w-full gap-2 text-sm" disabled={submitting} type="submit">
              {submitting ? "Signing in…" : <>Sign in <ArrowRight className="size-4" /></>}
            </Button>
          </form>

          <div className="mt-6 flex items-center gap-2 rounded-xl border border-border bg-muted/50 p-3 text-xs text-muted-foreground">
            <ShieldCheck className="size-4 shrink-0 text-primary" />
            On a pharmacy PC, use the admin email in the FIRST_LOGIN.txt file in the AetherQore data folder. Training databases still use the seed accounts in the project README.
          </div>
        </div>

        <p className="text-xs text-muted-foreground">© 2026 AetherQore, Inc.</p>
      </div>

      <div className="relative hidden flex-1 items-center justify-center overflow-hidden bg-accent lg:flex">
        <Image
          src="/assets/placeholder.svg"
          alt="Illustration of an AI-powered pharmacy workspace"
          fill
          priority
          className="object-cover opacity-80"
        />
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-foreground/70 to-transparent p-12">
          <blockquote className="max-w-md text-lg font-medium leading-relaxed text-background text-balance">
            &ldquo;AetherQore cut our shipment intake from two hours to nine minutes. It feels like the software is thinking with us.&rdquo;
          </blockquote>
          <p className="mt-3 text-sm text-background/80">Dr. Lena Osei · Owner, BrightCare Pharmacy</p>
        </div>
      </div>
    </main>
  )
}
