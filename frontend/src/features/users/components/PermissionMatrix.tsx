"use client"

import { Check, Lock, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { OverrideState, PermissionInfo } from "@/lib/api/types"
import { cn } from "@/lib/utils"

export type Overrides = Record<string, OverrideState>

/** Same rule as the backend resolver: admin-only codes follow the role, otherwise ALLOW/DENY win. */
export function effectiveFor(entry: PermissionInfo, baseline: Set<string>, state: OverrideState) {
  if (entry.admin_only || state === "INHERIT") return baseline.has(entry.code)
  return state === "ALLOW"
}

export type ModuleAccess = { group: string; label: string; level: "full" | "partial" | "none" }

export function moduleAccess(catalog: PermissionInfo[], effective: Set<string>): ModuleAccess[] {
  const groups = new Map<string, { label: string; codes: string[] }>()
  for (const entry of catalog) {
    const g = groups.get(entry.group) ?? { label: entry.group_label, codes: [] }
    g.codes.push(entry.code)
    groups.set(entry.group, g)
  }
  return [...groups.entries()].map(([group, { label, codes }]) => {
    const granted = codes.filter((c) => effective.has(c)).length
    return { group, label, level: granted === codes.length ? "full" : granted === 0 ? "none" : "partial" }
  })
}

export function AccessChips({ access, only }: { access: ModuleAccess[]; only?: string[] }) {
  const shown = only ? access.filter((a) => only.includes(a.group)) : access
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((a) => (
        <Badge
          key={a.group}
          variant={a.level === "full" ? "success" : a.level === "partial" ? "warning" : "neutral"}
          title={`${a.label}: ${a.level === "full" ? "full access" : a.level === "partial" ? "partial access" : "no access"}`}
          className={cn(a.level === "none" && "line-through opacity-70")}
        >
          {a.level === "full" ? <Check /> : a.level === "none" ? <X /> : null}
          {a.label}
        </Badge>
      ))}
    </div>
  )
}

const STATES: { value: OverrideState; label: string }[] = [
  { value: "INHERIT", label: "Inherit" },
  { value: "ALLOW", label: "Allow" },
  { value: "DENY", label: "Deny" },
]

function StateControl({
  value,
  onChange,
  disabled,
  label,
}: {
  value: OverrideState
  onChange: (next: OverrideState) => void
  disabled?: boolean
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-border bg-muted/40 p-0.5">
      {STATES.map((s) => (
        <button
          key={s.value}
          type="button"
          role="radio"
          aria-checked={value === s.value}
          disabled={disabled}
          onClick={() => onChange(s.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
            value === s.value
              ? s.value === "ALLOW"
                ? "bg-primary text-primary-foreground"
                : s.value === "DENY"
                  ? "bg-destructive text-white"
                  : "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {s.label}
        </button>
      ))}
    </div>
  )
}

export function PermissionMatrix({
  catalog,
  baseline,
  overrides,
  onChange,
  readOnly,
  changed,
}: {
  catalog: PermissionInfo[]
  baseline: Set<string>
  overrides: Overrides
  onChange?: (code: string, state: OverrideState) => void
  readOnly?: boolean
  changed?: Set<string>
}) {
  const groups: { key: string; label: string; entries: PermissionInfo[] }[] = []
  for (const entry of catalog) {
    let g = groups.find((x) => x.key === entry.group)
    if (!g) {
      g = { key: entry.group, label: entry.group_label, entries: [] }
      groups.push(g)
    }
    g.entries.push(entry)
  }

  return (
    <div className="space-y-4">
      {groups.map((g) => {
        const granted = g.entries.filter((e) => effectiveFor(e, baseline, overrides[e.code] ?? "INHERIT")).length
        return (
          <section key={g.key} className="rounded-xl border border-border">
            <header className="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-2">
              <h4 className="text-sm font-semibold">{g.label}</h4>
              <span className="text-xs text-muted-foreground">{granted} of {g.entries.length} allowed</span>
            </header>
            <ul className="divide-y divide-border">
              {g.entries.map((e) => {
                const state = overrides[e.code] ?? "INHERIT"
                const inRole = baseline.has(e.code)
                const effective = effectiveFor(e, baseline, state)
                const differs = effective !== inRole
                return (
                  <li
                    key={e.code}
                    className={cn("grid gap-2 px-3 py-2.5 sm:grid-cols-[1fr_auto_auto] sm:items-center", changed?.has(e.code) && "bg-warning/5")}
                  >
                    <div className="min-w-0">
                      <p className="text-sm">{e.description}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {e.code} · Role: {inRole ? "allowed" : "not included"}
                      </p>
                    </div>
                    {e.admin_only ? (
                      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title="Admin-only permissions follow the role and cannot be overridden. Change the role instead.">
                        <Lock className="size-3" /> Admin only
                      </span>
                    ) : (
                      <StateControl
                        value={state}
                        disabled={readOnly || !onChange}
                        onChange={(next) => onChange?.(e.code, next)}
                        label={`${e.description} override`}
                      />
                    )}
                    <span
                      className={cn(
                        "inline-flex min-w-[112px] items-center gap-1 text-xs font-medium sm:justify-end",
                        effective ? "text-primary" : "text-muted-foreground",
                        differs && !effective && "text-destructive",
                      )}
                    >
                      {effective ? <Check className="size-3.5" /> : <X className="size-3.5" />}
                      {effective ? "Can" : "Cannot"}
                      {differs && <span className="font-normal text-muted-foreground">(override)</span>}
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
