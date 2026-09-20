"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  FileClock,
  CalendarClock,
  Truck,
  ShoppingCart,
  PackagePlus,
  FileBarChart,
  Sparkles,
  ArrowUpRight,
  CircleDollarSign,
} from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { ButtonLink } from "@/components/ui/button"
import { api } from "@/lib/api/client"
import type { Dashboard } from "@/lib/api/types"
import { currency } from "@/lib/format"
import { useAuth } from "@/lib/auth-context"
import { AiRecommendationsCard } from "@/features/command-center/components/AiRecommendationsCard"
import { RecentActivity } from "@/features/command-center/components/RecentActivity"
import { RevenueCard } from "@/features/command-center/components/RevenueCard"
import { useInventoryLive } from "@/lib/inventory-sync"

export default function CommandCenterPage() {
  const { user } = useAuth()
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api<Dashboard>("/dashboard").then(setData).catch((e) => setError(e.message))
  }, [])
  useEffect(() => { load() }, [load])
  useInventoryLive(load)

  const first = user?.full_name.split(" ")[0] ?? "there"
  const priorities = data
    ? [
        { tone: "danger", icon: AlertTriangle, label: "Expiring soon", value: String(data.expiring_count), sub: "medicines within 30 days", href: "/inventory" },
        { tone: "warning", icon: FileClock, label: "Low stock", value: String(data.low_stock_count), sub: "below reorder point", href: "/inventory" },
        { tone: "info", icon: Truck, label: "Open POs", value: String(data.pending_invoices), sub: "awaiting receive", href: "/suppliers" },
        { tone: "success", icon: CircleDollarSign, label: "Today's revenue", value: currency(data.today_revenue), sub: `${data.today_sales_count} sales`, href: "/reports" },
        { tone: "neutral", icon: CalendarClock, label: "Yesterday", value: currency(data.yesterday_revenue), sub: `${data.yesterday_change_pct}% vs prior`, href: "/reports" },
      ]
    : []

  const toneMap: Record<string, { ring: string; icon: string }> = {
    danger: { ring: "before:bg-destructive", icon: "text-destructive bg-destructive/10" },
    warning: { ring: "before:bg-warning", icon: "text-warning-foreground bg-warning/15" },
    info: { ring: "before:bg-secondary", icon: "text-secondary bg-secondary/10" },
    success: { ring: "before:bg-primary", icon: "text-primary bg-primary/10" },
    neutral: { ring: "before:bg-muted-foreground/40", icon: "text-muted-foreground bg-muted" },
  }

  return (
    <>
      <AppTopbar title="Command Center" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-6 p-4 md:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Good day, {first}</h2>
            <p className="mt-1 text-sm text-muted-foreground">Live operational picture for BrightCare Pharmacy.</p>
          </div>
          <Badge variant="success">
            <span className="size-1.5 animate-aether-pulse rounded-full bg-primary" /> All systems operational
          </Badge>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
          {priorities.map((p) => {
            const t = toneMap[p.tone]
            return (
              <Link
                key={p.label}
                href={p.href}
                className={`group relative overflow-hidden rounded-2xl border border-border bg-card p-4 transition-all hover:-translate-y-0.5 hover:shadow-md before:absolute before:inset-x-0 before:top-0 before:h-1 ${t.ring}`}
              >
                <div className={`flex size-9 items-center justify-center rounded-xl ${t.icon}`}>
                  <p.icon className="size-[18px]" />
                </div>
                <p className="mt-3 text-2xl font-semibold tracking-tight">{p.value}</p>
                <p className="text-sm font-medium">{p.label}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{p.sub}</p>
                <ArrowUpRight className="absolute right-4 top-4 size-4 text-muted-foreground opacity-0 group-hover:opacity-100" />
              </Link>
            )
          })}
        </div>
        <div className="flex flex-wrap gap-2.5">
          {[
            { label: "Receive Shipment", icon: Truck, href: "/receiving", primary: true },
            { label: "New Sale", icon: ShoppingCart, href: "/pos" },
            { label: "Add Medicine", icon: PackagePlus, href: "/inventory" },
            { label: "Generate Report", icon: FileBarChart, href: "/reports" },
            { label: "Open AI Copilot", icon: Sparkles, href: "/copilot" },
          ].map((a) => (
            <ButtonLink key={a.label} href={a.href} variant={a.primary ? "default" : "outline"} size="lg" className="h-11 gap-2 rounded-xl px-4">
              <a.icon className="size-4" /> {a.label}
            </ButtonLink>
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <AiRecommendationsCard insights={data?.insights ?? []} />
          <RevenueCard weeklyRevenue={data?.weekly_revenue ?? 0} weeklyTrend={data?.weekly_trend ?? []} />
        </div>
        <RecentActivity activity={data?.activity ?? []} />
      </div>
    </>
  )
}
