"use client"

import { useEffect, useState } from "react"
import { Building2, Bell, Users, Sparkles, ShieldCheck, Check } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Button, ButtonLink } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { api, ApiError } from "@/lib/api/client"
import type { CopilotStatus, Settings, User } from "@/lib/api/types"
import { useAuth } from "@/lib/auth-context"

const TABS = [
  { id: "pharmacy", label: "Pharmacy", icon: Building2 },
  { id: "team", label: "Team", icon: Users },
  { id: "ai", label: "AI Copilot", icon: Sparkles },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "security", label: "Security", icon: ShieldCheck },
]

export default function SettingsPage() {
  const { can } = useAuth()
  const [tab, setTab] = useState("pharmacy")
  const [settings, setSettings] = useState<Settings | null>(null)
  const [team, setTeam] = useState<User[]>([])
  const [aiStatus, setAiStatus] = useState<CopilotStatus | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!can("settings.manage")) return
    api<Settings>("/settings").then(setSettings).catch(() => setSettings(null))
    api<User[]>("/users").then(setTeam).catch(() => setTeam([]))
    api<CopilotStatus>("/copilot/status").then(setAiStatus).catch(() => setAiStatus(null))
  }, [can])

  const save = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    try {
      const next = await api<Settings>("/settings", {
        method: "PATCH",
        body: JSON.stringify({
          pharmacy_name: fd.get("pharmacy_name"),
          license_number: fd.get("license_number"),
          phone: fd.get("phone"),
          email: fd.get("email"),
          address: fd.get("address"),
          tax_rate: fd.get("tax_rate"),
        }),
      })
      setSettings(next)
      setMessage("Saved")
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Save failed")
    }
  }

  return (
    <>
      <AppTopbar title="Settings" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 p-4 md:p-6">
        <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
          <nav className="flex gap-1 overflow-x-auto scrollbar-thin lg:flex-col">
            {TABS.map((t) => {
              const Icon = t.icon
              return (
                <button key={t.id} onClick={() => setTab(t.id)} className={cn("flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium", tab === t.id ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-muted")}>
                  <Icon className="size-4" /> {t.label}
                </button>
              )
            })}
          </nav>
          <div className="rounded-2xl border border-border bg-card p-6">
            {tab === "pharmacy" && settings && (
              <form className="max-w-xl space-y-4" onSubmit={save}>
                <h3 className="text-base font-semibold">Pharmacy profile</h3>
                {[
                  ["pharmacy_name", "Pharmacy name", settings.pharmacy_name],
                  ["license_number", "License number", settings.license_number],
                  ["phone", "Phone", settings.phone],
                  ["email", "Email", settings.email],
                  ["address", "Address", settings.address],
                  ["tax_rate", "Tax rate (%)", String(settings.tax_rate)],
                ].map(([name, label, value]) => (
                  <label key={name} className="flex flex-col gap-1.5 text-sm">
                    {label}
                    <input name={name} defaultValue={value} className="h-10 rounded-lg border border-input bg-card px-3 text-sm outline-none" />
                  </label>
                ))}
                {message && <p className="text-sm text-primary">{message}</p>}
                <Button type="submit">Save changes</Button>
              </form>
            )}
            {tab === "team" && (
              <div>
                <div className="mb-5 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold">Team members</h3>
                    <p className="text-sm text-muted-foreground">{team.length} people have access.</p>
                  </div>
                  {can("users.read") && (
                    <ButtonLink href="/users" variant="outline">Manage team</ButtonLink>
                  )}
                </div>
                <div className="divide-y divide-border">
                  {team.map((m) => (
                    <div key={m.id} className="flex items-center gap-3 py-3">
                      <div className="flex size-9 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">{m.full_name.split(" ").map((p) => p[0]).join("")}</div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{m.full_name}</p>
                        <p className="truncate text-sm text-muted-foreground">{m.email}</p>
                      </div>
                      <Badge variant={m.role === "admin" ? "default" : "neutral"}>{m.role}</Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {tab === "ai" && (
              <div className="max-w-xl">
                <h3 className="text-base font-semibold">AI Copilot</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {aiStatus?.message ?? "The copilot answers from live inventory and sales on this computer. Cloud AI is optional and needs a provider key plus internet."}
                </p>
                {aiStatus && (
                  <p className="mt-3 text-sm">
                    Current mode: <span className="font-medium">{aiStatus.ai_enabled ? "Cloud AI + local data" : "Local pharmacy data only"}</span>
                  </p>
                )}
              </div>
            )}
            {tab === "notifications" && (
              <div className="max-w-xl">
                <h3 className="text-base font-semibold">Notifications</h3>
                <p className="mt-2 text-sm text-muted-foreground">The bell in the top bar shows live low-stock and expiry alerts computed from inventory.</p>
              </div>
            )}
            {tab === "security" && (
              <div className="max-w-xl space-y-3">
                <h3 className="text-base font-semibold">Security</h3>
                {["Passwords hashed with bcrypt", "JWT access + refresh tokens", "Permission checks on every API", "Audit log for state-changing actions"].map((f) => (
                  <div key={f} className="flex items-center gap-2 text-sm">
                    <span className="flex size-5 items-center justify-center rounded-full bg-primary/10"><Check className="size-3 text-primary" /></span>
                    {f}
                  </div>
                ))}
                {can("audit.read") && (
                  <ButtonLink href="/audit" variant="outline" className="mt-4">Open audit log</ButtonLink>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
