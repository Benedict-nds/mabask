"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  Package,
  Truck,
  ShoppingCart,
  BarChart3,
  Sparkles,
  Users,
  Settings,
  LifeBuoy,
  Boxes,
  ChevronsUpDown,
  Menu,
  X,
  LogOut,
  ScrollText,
  Sun,
  Moon,
  Monitor,
} from "lucide-react"
import { Overlay, useDismissable } from "@/components/ui/dismissable"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import { useTheme, type Theme } from "@/app/theme"

const nav = [
  { section: "Workspace", items: [
    { href: "/dashboard", label: "Command Center", icon: LayoutDashboard, permission: "reports.read" },
    { href: "/inventory", label: "Inventory", icon: Package, permission: "inventory.read" },
    { href: "/suppliers", label: "Suppliers", icon: Users, permission: "suppliers.read" },
    { href: "/receiving", label: "Receive Shipment", icon: Truck, permission: "purchases.receive" },
    { href: "/pos", label: "Point of Sale", icon: ShoppingCart, permission: "sales.create" },
  ]},
  { section: "Intelligence", items: [
    { href: "/reports", label: "Reports", icon: BarChart3, permission: "reports.read" },
    { href: "/copilot", label: "AI Copilot", icon: Sparkles, permission: "ai.use" },
  ]},
  { section: "Manage", items: [
    { href: "/users", label: "Team", icon: Users, permission: "users.read" },
    { href: "/audit", label: "Audit log", icon: ScrollText, permission: "audit.read" },
    { href: "/settings", label: "Settings", icon: Settings, permission: "settings.manage" },
    { href: "/help", label: "Help", icon: LifeBuoy, permission: "inventory.read" },
  ]},
]

function UserAccountMenu({ onNavigate }: { onNavigate?: () => void }) {
  const { user, can, logout } = useAuth()
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useState(false)
  const menuRef = useDismissable(open, () => setOpen(false))
  const initials = (user?.full_name ?? "AQ").split(" ").map((p) => p[0]).join("").slice(0, 2)
  const themes: { id: Theme; label: string; icon: typeof Sun }[] = [
    { id: "light", label: "Light", icon: Sun },
    { id: "dark", label: "Dark", icon: Moon },
    { id: "system", label: "System", icon: Monitor },
  ]

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
      >
        <span className="flex size-8 items-center justify-center rounded-full bg-secondary/10 text-xs font-semibold text-secondary">
          {initials}
        </span>
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-sm font-medium text-sidebar-foreground">{user?.full_name ?? "…"}</span>
          <span className="block truncate text-xs text-muted-foreground capitalize">{user?.role ?? ""}</span>
        </span>
        <ChevronsUpDown className="size-4 text-muted-foreground" />
      </button>
      {open && (
        <div role="menu" className="absolute bottom-full left-0 right-0 z-20 mb-1 overflow-hidden rounded-xl border border-border bg-card py-1 shadow-lg">
          <div className="border-b border-border px-3 py-2">
            <p className="truncate text-sm font-medium">{user?.full_name}</p>
            <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
          </div>
          {can("settings.manage") && (
            <Link role="menuitem" href="/settings" onClick={() => { setOpen(false); onNavigate?.() }} className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted">
              <Settings className="size-4 text-muted-foreground" /> Settings
            </Link>
          )}
          {can("users.read") && (
            <Link role="menuitem" href="/users" onClick={() => { setOpen(false); onNavigate?.() }} className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted">
              <Users className="size-4 text-muted-foreground" /> Team
            </Link>
          )}
          <div className="border-t border-border px-3 py-2">
            <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Appearance</p>
            <div className="grid grid-cols-3 gap-1">
              {themes.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => setTheme(option.id)}
                  className={cn(
                    "flex flex-col items-center gap-1 rounded-lg px-1 py-1.5 text-[11px]",
                    theme === option.id ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  <option.icon className="size-3.5" />
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <button
            role="menuitem"
            onClick={() => { setOpen(false); void logout() }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <LogOut className="size-4" /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}

export function AppSidebar() {
  const pathname = usePathname()
  const { can } = useAuth()
  const [open, setOpen] = useState(false)

  const content = (
    <>
      <div className="flex h-16 items-center gap-2.5 px-5">
        <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
          <Boxes className="size-5" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-sidebar-foreground">AetherQore</p>
          <p className="text-[11px] text-muted-foreground">Pharmacy OS</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto scrollbar-thin px-3 py-2">
        {nav.map((group) => {
          const items = group.items.filter((item) => can(item.permission))
          if (!items.length) return null
          return (
            <div key={group.section} className="mb-5">
              <p className="px-3 pb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground/70 uppercase">
                {group.section}
              </p>
              <ul className="flex flex-col gap-0.5">
                {items.map((item) => {
                  const active = pathname === item.href
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={() => setOpen(false)}
                        className={cn(
                          "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                          active
                            ? "bg-sidebar-accent text-sidebar-accent-foreground"
                            : "text-sidebar-foreground hover:bg-muted hover:text-foreground",
                        )}
                      >
                        <item.icon className={cn("size-[18px]", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")} />
                        {item.label}
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <UserAccountMenu onNavigate={() => setOpen(false)} />
      </div>
    </>
  )

  return (
    <>
      <button
        className="fixed left-4 top-4 z-40 flex size-9 items-center justify-center rounded-lg border border-border bg-card lg:hidden"
        onClick={() => setOpen(true)}
        aria-label="Open menu"
      >
        <Menu className="size-4" />
      </button>
      {open && (
        <Overlay onClose={() => setOpen(false)} className="z-40 items-stretch justify-start bg-foreground/30 p-0 lg:hidden">
          <aside className="flex h-full w-64 flex-col border-r border-sidebar-border bg-sidebar" onClick={(e) => e.stopPropagation()}>
            <button className="absolute right-3 top-4 text-muted-foreground" onClick={() => setOpen(false)} aria-label="Close menu">
              <X className="size-4" />
            </button>
            {content}
          </aside>
        </Overlay>
      )}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        {content}
      </aside>
    </>
  )
}
