"use client"

import { useEffect, useState } from "react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api, ApiError } from "@/lib/api/client"
import type { AuditEntry, Page } from "@/lib/api/types"

export default function AuditPage() {
  const [items, setItems] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [action, setAction] = useState("")
  const [entity, setEntity] = useState("")
  const [q, setQ] = useState("")
  const [error, setError] = useState<string | null>(null)
  const pageSize = 25

  const load = async () => {
    try {
      const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) })
      if (action) params.set("action", action)
      if (entity) params.set("entity_type", entity)
      if (q) params.set("q", q)
      const page = await api<Page<AuditEntry>>(`/audit?${params}`)
      setItems(page.items)
      setTotal(page.total)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load audit log")
    }
  }

  useEffect(() => {
    void load()
  }, [offset, action, entity])

  return (
    <>
      <AppTopbar title="Audit log" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-5 p-4 md:p-6">
        <div>
          <h2 className="text-xl font-semibold">Operational history</h2>
          <p className="mt-1 text-sm text-muted-foreground">Who changed what, and when. Passwords and tokens are never stored here.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (setOffset(0), void load())} placeholder="Search action or entity…" className="h-10 flex-1 rounded-xl border border-border bg-card px-3 text-sm outline-none" />
          <input value={action} onChange={(e) => { setAction(e.target.value); setOffset(0) }} placeholder="Action" className="h-10 w-48 rounded-xl border border-border bg-card px-3 text-sm outline-none" />
          <input value={entity} onChange={(e) => { setEntity(e.target.value); setOffset(0) }} placeholder="Entity" className="h-10 w-40 rounded-xl border border-border bg-card px-3 text-sm outline-none" />
          <Button variant="outline" onClick={() => { setOffset(0); void load() }}>Filter</Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">When</th>
                <th className="px-4 py-3 font-medium">Actor</th>
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium">Entity</th>
                <th className="px-4 py-3 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">No audit events match these filters.</td></tr>
              )}
              {items.map((row) => (
                <tr key={row.id}>
                  <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{new Date(row.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3">{row.actor ?? "System"}</td>
                  <td className="px-4 py-3"><Badge variant="neutral">{row.action}</Badge></td>
                  <td className="px-4 py-3 text-muted-foreground">{row.entity_type}{row.entity_id ? ` · ${row.entity_id.slice(0, 8)}` : ""}</td>
                  <td className="max-w-xs truncate px-4 py-3 text-xs text-muted-foreground">{Object.keys(row.details || {}).length ? JSON.stringify(row.details) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{total} events</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</Button>
            <Button variant="outline" size="sm" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>Next</Button>
          </div>
        </div>
      </div>
    </>
  )
}
