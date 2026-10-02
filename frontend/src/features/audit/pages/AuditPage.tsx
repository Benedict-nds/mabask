"use client"

import { Fragment, useEffect, useMemo, useState } from "react"
import { ChevronDown, ChevronRight, Copy, Search } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api, ApiError } from "@/lib/api/client"
import type { AuditEntry, AuditFacets, Page } from "@/lib/api/types"

const PAGE_SIZE = 25

const entityLabels: Record<string, string> = {
  purchase_order: "Purchase order",
  product: "Product",
  batch: "Batch",
  sale: "Sale",
  return: "Return",
  sale_correction: "Sale correction",
  supplier: "Supplier",
  user: "User",
  settings: "Settings",
  manual_receipt: "Manual receipt",
}

const detailLabels: Record<string, string> = {
  po_number: "PO",
  previous_status: "From",
  new_status: "To",
  reason: "Reason",
  changes: "Changes",
  sale_number: "Sale",
  corrected_sale_number: "Corrected sale",
  return_number: "Return",
  refund_amount: "Refund",
  corrected_total: "Corrected total",
  financial_difference: "Difference",
  reviewer_edit: "Reviewer edit",
  reference: "Reference",
  supplier: "Supplier",
  purchase_order: "Purchase order",
  lines: "Lines",
  units: "Units",
  items: "Items",
  notes: "Notes",
  review_note: "Review note",
  permission: "Permission",
  previous: "From",
  new: "To",
  target_user: "Staff member",
  target_name: "Name",
  role: "Role",
  previous_expiry: "From",
  new_expiry: "To",
  batch_number: "Batch",
  product: "Medicine",
}

const HIDDEN_DETAIL_KEYS = new Set(["sale_id", "corrected_sale_id", "return_id", "product_id"])

function humanizeAction(action: string) {
  const text = action.replace(/_/g, " ").toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—"
  if (typeof value === "boolean") return value ? "Yes" : "No"
  if (Array.isArray(value)) return value.map(formatValue).join("; ")
  if (typeof value === "object") return JSON.stringify(value)
  return String(value).replace(/_/g, " ")
}

function detailEntries(details: Record<string, unknown>) {
  return Object.entries(details || {}).filter(([k, v]) => !HIDDEN_DETAIL_KEYS.has(k) && v !== "" && v !== null && v !== undefined)
}

function summary(row: AuditEntry) {
  const d = row.details || {}
  const parts: string[] = []
  if (d.permission && d.previous && d.new) parts.push(`${d.permission}: ${formatValue(d.previous)} → ${formatValue(d.new)}`)
  else if (row.action === "ROLE_CHANGED" && d.previous && d.new) parts.push(`Role ${formatValue(d.previous)} → ${formatValue(d.new)}`)
  if (d.previous_expiry && d.new_expiry) parts.push(`Expiry ${formatValue(d.previous_expiry)} → ${formatValue(d.new_expiry)}`)
  if (d.previous_status && d.new_status) parts.push(`${formatValue(d.previous_status)} → ${formatValue(d.new_status)}`)
  else if (d.new_status) parts.push(`Status ${formatValue(d.new_status)}`)
  if (d.reason) parts.push(`Reason: ${formatValue(d.reason)}`)
  if (Array.isArray(d.changes) && d.changes.length) parts.push(`${d.changes.length} change${d.changes.length === 1 ? "" : "s"}`)
  if (d.units) parts.push(`${formatValue(d.units)} units`)
  if (d.financial_difference) parts.push(`Difference ${formatValue(d.financial_difference)}`)
  if (!parts.length) {
    const first = detailEntries(d).slice(0, 2).map(([k, v]) => `${detailLabels[k] ?? k.replace(/_/g, " ")}: ${formatValue(v)}`)
    parts.push(...first)
  }
  return parts.join(" · ") || "—"
}

export default function AuditPage() {
  const [items, setItems] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [facets, setFacets] = useState<AuditFacets>({ actions: [], entity_types: [], users: [] })
  const [action, setAction] = useState("")
  const [entity, setEntity] = useState("")
  const [entityId, setEntityId] = useState("")
  const [userId, setUserId] = useState("")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [q, setQ] = useState("")
  const [qLive, setQLive] = useState("")
  const [entityIdLive, setEntityIdLive] = useState("")
  const [expanded, setExpanded] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<AuditFacets>("/audit/facets").then(setFacets).catch(() => undefined)
  }, [])

  useEffect(() => {
    const t = window.setTimeout(() => {
      setQLive(q)
      setEntityIdLive(entityId)
    }, 300)
    return () => window.clearTimeout(t)
  }, [q, entityId])

  const filterKey = useMemo(
    () => JSON.stringify([action, entity, entityIdLive, userId, dateFrom, dateTo, qLive]),
    [action, entity, entityIdLive, userId, dateFrom, dateTo, qLive],
  )

  useEffect(() => {
    setOffset(0)
  }, [filterKey])

  useEffect(() => {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
    if (action) params.set("action", action)
    if (entity) params.set("entity_type", entity)
    if (entityIdLive.trim()) params.set("entity_id", entityIdLive.trim())
    if (userId) params.set("user_id", userId)
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    if (qLive.trim()) params.set("q", qLive.trim())
    api<Page<AuditEntry>>(`/audit?${params}`)
      .then((page) => {
        setItems(page.items)
        setTotal(page.total)
        setError(null)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load audit log"))
  }, [offset, filterKey, action, entity, entityIdLive, userId, dateFrom, dateTo, qLive])

  const clear = () => {
    setAction("")
    setEntity("")
    setEntityId("")
    setUserId("")
    setDateFrom("")
    setDateTo("")
    setQ("")
  }

  const selectCls = "mt-1 block h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground"

  return (
    <>
      <AppTopbar title="Audit log" />
      <div className="mx-auto w-full max-w-[1400px] flex-1 space-y-5 p-4 md:p-6">
        <div>
          <h2 className="text-xl font-semibold">Operational history</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Who changed what, and when. Passwords, tokens, and other secrets are never shown here.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2 rounded-2xl border border-border bg-card p-4">
          <label className="text-xs text-muted-foreground">
            From
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={selectCls} />
          </label>
          <label className="text-xs text-muted-foreground">
            To
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={selectCls} />
          </label>
          <label className="text-xs text-muted-foreground">
            User
            <select value={userId} onChange={(e) => setUserId(e.target.value)} className={selectCls}>
              <option value="">All users</option>
              {facets.users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </label>
          <label className="text-xs text-muted-foreground">
            Action
            <select value={action} onChange={(e) => setAction(e.target.value)} className={`${selectCls} max-w-64`}>
              <option value="">All actions</option>
              {facets.actions.map((a) => <option key={a} value={a}>{humanizeAction(a)}</option>)}
            </select>
          </label>
          <label className="text-xs text-muted-foreground">
            Entity type
            <select value={entity} onChange={(e) => setEntity(e.target.value)} className={selectCls}>
              <option value="">All types</option>
              {facets.entity_types.map((t) => <option key={t} value={t}>{entityLabels[t] ?? t}</option>)}
            </select>
          </label>
          <label className="text-xs text-muted-foreground">
            Entity ID
            <input value={entityId} onChange={(e) => setEntityId(e.target.value)} placeholder="Exact ID" className={`${selectCls} w-48 font-mono`} />
          </label>
          <label className="min-w-48 flex-1 text-xs text-muted-foreground">
            Search
            <div className="mt-1 flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-2">
              <Search className="size-3.5 text-muted-foreground" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="PO number, sale number, reason…" className="h-full flex-1 bg-transparent text-sm text-foreground outline-none" />
            </div>
          </label>
          <Button type="button" variant="ghost" onClick={clear}>Clear</Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="overflow-x-auto rounded-2xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="w-6 px-2 py-3" />
                <th className="px-3 py-3 font-medium">Timestamp</th>
                <th className="px-3 py-3 font-medium">User</th>
                <th className="px-3 py-3 font-medium">Action</th>
                <th className="px-3 py-3 font-medium">Entity</th>
                <th className="px-3 py-3 font-medium">Entity ID</th>
                <th className="px-3 py-3 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">No audit events match these filters.</td></tr>
              )}
              {items.map((row) => {
                const open = expanded === row.id
                const entries = detailEntries(row.details)
                return (
                  <Fragment key={row.id}>
                    <tr className="cursor-pointer align-top hover:bg-muted/30" onClick={() => setExpanded(open ? null : row.id)}>
                      <td className="px-2 py-3 text-muted-foreground">
                        {entries.length ? (open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />) : null}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-muted-foreground">{new Date(row.created_at).toLocaleString()}</td>
                      <td className="px-3 py-3">{row.actor ?? "System"}</td>
                      <td className="px-3 py-3">
                        <Badge variant="neutral" title={row.action}>{humanizeAction(row.action)}</Badge>
                      </td>
                      <td className="px-3 py-3">
                        <p>{row.entity_label ?? "—"}</p>
                        <p className="text-xs text-muted-foreground">{entityLabels[row.entity_type] ?? row.entity_type}</p>
                      </td>
                      <td className="px-3 py-3">
                        {row.entity_id ? (
                          <span className="inline-flex items-center gap-1">
                            <code className="break-all text-xs">{row.entity_id}</code>
                            <button
                              type="button"
                              aria-label="Copy entity ID"
                              className="text-muted-foreground hover:text-foreground"
                              onClick={(e) => {
                                e.stopPropagation()
                                void navigator.clipboard?.writeText(row.entity_id)
                              }}
                            >
                              <Copy className="size-3" />
                            </button>
                          </span>
                        ) : "—"}
                      </td>
                      <td className="max-w-sm px-3 py-3 text-xs text-muted-foreground">{summary(row)}</td>
                    </tr>
                    {open && entries.length > 0 && (
                      <tr className="bg-muted/20">
                        <td />
                        <td colSpan={6} className="px-3 py-3">
                          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-xs">
                            {entries.map(([k, v]) => (
                              <Fragment key={k}>
                                <dt className="text-muted-foreground">{detailLabels[k] ?? k.replace(/_/g, " ")}</dt>
                                <dd>
                                  {Array.isArray(v) ? (
                                    <ul className="list-disc pl-4">{v.map((item, i) => <li key={i}>{formatValue(item)}</li>)}</ul>
                                  ) : (
                                    formatValue(v)
                                  )}
                                </dd>
                              </Fragment>
                            ))}
                          </dl>
                          <button
                            type="button"
                            className="mt-2 text-xs text-primary hover:underline"
                            onClick={() => {
                              setEntity(row.entity_type)
                              setEntityId(row.entity_id)
                            }}
                          >
                            Show full history of this {entityLabels[row.entity_type]?.toLowerCase() ?? "record"}
                          </button>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{total} event{total === 1 ? "" : "s"}</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
            <span className="tabular-nums">Page {Math.floor(offset / PAGE_SIZE) + 1} / {Math.max(1, Math.ceil(total / PAGE_SIZE))}</span>
            <Button variant="outline" size="sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button>
          </div>
        </div>
      </div>
    </>
  )
}
