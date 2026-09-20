"use client"

import { useEffect, useState } from "react"
import { Sparkles, DollarSign, Percent, Wallet, Package } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { BarChart, DonutChart } from "@/components/charts"
import { api } from "@/lib/api/client"
import type { SalesReport } from "@/lib/api/types"
import { currency } from "@/lib/format"
import { cn } from "@/lib/utils"

const ranges = ["Daily", "Weekly", "Monthly", "Custom"]

export default function ReportsPage() {
  const [range, setRange] = useState("Weekly")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [data, setData] = useState<SalesReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const params = new URLSearchParams()
    if (range === "Custom") {
      if (!start || !end) return
      params.set("start", start)
      params.set("end", end)
    } else {
      params.set("range", range.toLowerCase())
    }
    api<SalesReport>(`/reports/sales?${params}`)
      .then((report) => { setData(report); setError(null) })
      .catch((err) => { setData(null); setError(err.message) })
  }, [range, start, end])

  const kpis = [
    { label: "Revenue", value: currency(data?.revenue ?? 0), change: 0, icon: DollarSign },
    { label: "Gross profit", value: currency(data?.gross_profit ?? 0), change: 0, icon: Percent },
    { label: "Transactions", value: String(data?.transactions ?? 0), change: 0, icon: Wallet },
    { label: "Units sold", value: String(data?.units_sold ?? 0), change: 0, icon: Package },
  ]

  return (
    <>
      <AppTopbar title="Reports" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-5 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center rounded-lg border border-border bg-card p-0.5">
            {ranges.map((r) => (
              <button key={r} onClick={() => setRange(r)} className={cn("rounded-md px-3.5 py-1.5 text-sm font-medium", range === r ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>{r}</button>
            ))}
          </div>
          {range === "Custom" && (
            <div className="flex items-center gap-2">
              <input type="date" min="2000-01-01" max="2099-12-31" value={start} onChange={(e) => setStart(e.target.value)} className="h-9 rounded-lg border border-border bg-card px-3 text-sm" />
              <input type="date" min="2000-01-01" max="2099-12-31" value={end} onChange={(e) => setEnd(e.target.value)} className="h-9 rounded-lg border border-border bg-card px-3 text-sm" />
            </div>
          )}
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="rounded-2xl border border-primary/20 bg-primary/5 p-5">
          <div className="flex items-center gap-2 text-primary">
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary/15"><Sparkles className="size-4" /></span>
            <p className="text-sm font-semibold">Summary · {range}</p>
            <Badge variant="success" className="ml-auto">From live sales</Badge>
          </div>
          <p className="mt-3 text-sm leading-relaxed">
            Revenue is {currency(data?.revenue ?? 0)} across {data?.transactions ?? 0} transactions
            (average ticket {currency(data?.average_ticket ?? 0)}). Gross profit {currency(data?.gross_profit ?? 0)}.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {kpis.map((k) => (
            <div key={k.label} className="rounded-2xl border border-border bg-card p-4">
              <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground"><k.icon className="size-4" /></span>
              <p className="mt-3 text-2xl font-semibold tracking-tight">{k.value}</p>
              <p className="text-sm text-muted-foreground">{k.label}</p>
            </div>
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-2xl border border-border bg-card p-5 lg:col-span-2">
            <h3 className="text-sm font-semibold">Revenue trend</h3>
            {data?.trend?.length ? <BarChart data={data.trend} className="mt-6 h-52" currencyFormat /> : <p className="mt-10 text-sm text-muted-foreground">No sales in this range.</p>}
          </div>
          <div className="rounded-2xl border border-border bg-card p-5">
            <h3 className="text-sm font-semibold">Sales by category</h3>
            <div className="mt-6 flex justify-center">
              {data?.category_mix?.length ? <DonutChart data={data.category_mix} /> : <p className="text-sm text-muted-foreground">No sales in this range</p>}
            </div>
          </div>
        </div>
        <div className="rounded-2xl border border-border bg-card p-5">
          <h3 className="text-sm font-semibold">Top selling medicines</h3>
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="pb-2 font-medium">Medicine</th>
                <th className="pb-2 text-right font-medium">Units</th>
                <th className="pb-2 text-right font-medium">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {(data?.top_selling ?? []).map((t) => (
                <tr key={t.name} className="border-b border-border last:border-0">
                  <td className="py-3 font-medium">{t.name}</td>
                  <td className="py-3 text-right tabular-nums">{t.units}</td>
                  <td className="py-3 text-right tabular-nums">{currency(t.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
