"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import {
  Search,
  Bell,
  Plus,
  Sparkles,
  LayoutDashboard,
  Package,
  Truck,
  ShoppingCart,
  BarChart3,
  Users,
  Settings,
  Command,
  X,
} from "lucide-react"
import { Button, ButtonLink } from "@/components/ui/button"
import { Overlay, useDismissable } from "@/components/ui/dismissable"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api/client"
import type { Notification } from "@/lib/api/types"
import { useAuth } from "@/lib/auth-context"

const commands = [
  { label: "Go to Command Center", href: "/dashboard", icon: LayoutDashboard, group: "Navigate", permission: "reports.read" },
  { label: "Open Inventory", href: "/inventory", icon: Package, group: "Navigate", permission: "inventory.read" },
  { label: "Receive a Shipment", href: "/receiving", icon: Truck, group: "Actions", permission: "purchases.receive" },
  { label: "Start a New Sale", href: "/pos", icon: ShoppingCart, group: "Actions", permission: "sales.create" },
  { label: "View Reports", href: "/reports", icon: BarChart3, group: "Navigate", permission: "reports.read" },
  { label: "Ask the AI Copilot", href: "/copilot", icon: Sparkles, group: "Actions", permission: "ai.use" },
  { label: "Manage Suppliers", href: "/suppliers", icon: Users, group: "Navigate", permission: "suppliers.read" },
  { label: "Open Settings", href: "/settings", icon: Settings, group: "Navigate", permission: "settings.manage" },
]

export function AppTopbar({ title }: { title: string }) {
  const router = useRouter()
  const { can } = useAuth()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [notesOpen, setNotesOpen] = useState(false)
  const [notes, setNotes] = useState<Notification[]>([])
  const notesRef = useDismissable(notesOpen, () => setNotesOpen(false))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  useEffect(() => {
    api<Notification[]>("/notifications").then(setNotes).catch(() => setNotes([]))
  }, [])

  const filtered = commands.filter((c) => can(c.permission) && c.label.toLowerCase().includes(query.toLowerCase()))
  const groups = Array.from(new Set(filtered.map((c) => c.group)))

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md md:px-6">
      <h1 className="ml-12 text-base font-semibold text-foreground md:text-lg lg:ml-0">{title}</h1>

      <button
        onClick={() => setOpen(true)}
        className="ml-auto hidden h-9 w-64 items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground transition-colors hover:border-ring/40 md:flex"
      >
        <Search className="size-4" />
        <span>Search or ask AI…</span>
        <kbd className="ml-auto flex items-center gap-0.5 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium">
          <Command className="size-2.5" />K
        </kbd>
      </button>

      <Button variant="outline" size="icon" className="md:hidden ml-auto" onClick={() => setOpen(true)} aria-label="Search">
        <Search className="size-4" />
      </Button>

      <div className="relative" ref={notesRef}>
        <Button variant="outline" size="icon" className="relative" aria-label="Notifications" onClick={() => setNotesOpen((o) => !o)}>
          <Bell className="size-4" />
          {notes.length > 0 && <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-destructive ring-2 ring-background" />}
        </Button>
        {notesOpen && (
          <div className="absolute right-0 top-11 z-40 w-80 rounded-xl border border-border bg-card p-2 shadow-lg">
            <p className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">Alerts</p>
            {notes.length === 0 && <p className="px-2 py-4 text-sm text-muted-foreground">No alerts right now.</p>}
            {notes.slice(0, 8).map((n) => (
              <div key={n.id} className="rounded-lg px-2 py-2 hover:bg-muted">
                <p className="text-sm font-medium">{n.title}</p>
                <p className="text-xs text-muted-foreground">{n.message}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {can("sales.create") && (
        <ButtonLink href="/pos" className="gap-1.5">
          <Plus className="size-4" />
          <span className="hidden sm:inline">New Sale</span>
        </ButtonLink>
      )}

      {open && (
        <Overlay onClose={() => setOpen(false)} className="items-start justify-center pt-[12vh] backdrop-blur-sm">
          <div className="w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-popover shadow-2xl animate-fade-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 border-b border-border px-4">
              <Search className="size-4 text-muted-foreground" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search commands, medicines, or ask the AI…"
                className="h-14 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
              <button onClick={() => setOpen(false)} className="rounded-md p-1 text-muted-foreground hover:bg-muted">
                <X className="size-4" />
              </button>
            </div>
            <div className="max-h-80 overflow-y-auto scrollbar-thin p-2">
              {query && can("ai.use") && (
                <button
                  onClick={() => { setOpen(false); router.push("/copilot") }}
                  className="mb-1 flex w-full items-center gap-3 rounded-lg bg-accent px-3 py-2.5 text-left text-sm"
                >
                  <Sparkles className="size-4 text-primary" />
                  <span className="text-accent-foreground">Ask AI Copilot: <span className="font-medium">{query}</span></span>
                </button>
              )}
              {groups.map((g) => (
                <div key={g} className="mb-1">
                  <p className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/70">{g}</p>
                  {filtered.filter((c) => c.group === g).map((c) => (
                    <button
                      key={c.href}
                      onClick={() => { setOpen(false); router.push(c.href) }}
                      className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-muted")}
                    >
                      <c.icon className="size-4 text-muted-foreground" />
                      {c.label}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </Overlay>
      )}
    </header>
  )
}
