"use client"

import { useEffect, useMemo, useState } from "react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { api, ApiError } from "@/lib/api/client"
import type { OverrideState, PermissionInfo, Role, User, UserPermissions } from "@/lib/api/types"
import { useAuth } from "@/lib/auth-context"
import { cn } from "@/lib/utils"
import {
  AccessChips,
  PermissionMatrix,
  effectiveFor,
  moduleAccess,
  type Overrides,
} from "@/features/users/components/PermissionMatrix"

const SUMMARY_GROUPS = ["inventory", "sales", "purchases", "receiving", "reports"]

function overrideCount(member: User) {
  return Object.keys(member.permission_overrides ?? {}).length
}

export default function UsersPage() {
  const { can, user: me } = useAuth()
  const [team, setTeam] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [catalog, setCatalog] = useState<PermissionInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [editing, setEditing] = useState<User | null>(null)
  const [creating, setCreating] = useState(false)

  const load = async () => {
    try {
      const [users, roleList, perms] = await Promise.all([
        api<User[]>("/users"),
        api<Role[]>("/users/roles"),
        api<PermissionInfo[]>("/users/permission-catalog"),
      ])
      setTeam(users)
      setRoles(roleList)
      setCatalog(perms)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load team")
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const canManage = can("users.update")

  return (
    <>
      <AppTopbar title="Team" />
      <div className="mx-auto w-full max-w-[1100px] flex-1 space-y-5 p-4 md:p-6">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Staff accounts</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Each person gets their role&apos;s permissions. Open a member to allow or deny individual capabilities without changing their role.
            </p>
          </div>
          {can("users.create") && (
            <Button onClick={() => { setCreating(true); setEditing(null) }}>Add staff</Button>
          )}
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {message && <p className="text-sm text-primary">{message}</p>}
        <div className="overflow-x-auto rounded-2xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Effective access</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Last login</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {team.map((member) => {
                const count = overrideCount(member)
                return (
                  <tr
                    key={member.id}
                    className={cn(canManage && "cursor-pointer hover:bg-muted/30")}
                    onClick={() => { if (canManage) { setEditing(member); setCreating(false) } }}
                  >
                    <td className="px-4 py-3">
                      <p className="font-medium">{member.full_name}</p>
                      <p className="text-xs text-muted-foreground">{member.email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-1">
                        <Badge variant={member.role === "admin" ? "default" : "neutral"}>{member.role}</Badge>
                        {count > 0 && <Badge variant="warning">{count} override{count === 1 ? "" : "s"}</Badge>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {catalog.length > 0 && (
                        <AccessChips access={moduleAccess(catalog, new Set(member.permissions))} only={SUMMARY_GROUPS} />
                      )}
                    </td>
                    <td className="px-4 py-3">{member.is_active ? "Active" : "Inactive"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{member.last_login_at ? new Date(member.last_login_at).toLocaleString() : "—"}</td>
                    <td className="px-4 py-3 text-right">
                      {canManage && (
                        <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setEditing(member); setCreating(false) }}>Manage</Button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {creating && (
          <CreateMember
            roles={roles}
            catalog={catalog}
            onClose={() => setCreating(false)}
            onSaved={async (note) => {
              setMessage(note)
              setCreating(false)
              await load()
            }}
          />
        )}
        {editing && (
          <MemberPanel
            key={editing.id}
            member={editing}
            roles={roles}
            catalog={catalog}
            selfId={me?.id}
            canDelete={can("users.delete")}
            onClose={() => setEditing(null)}
            onSaved={async (note, close) => {
              setMessage(note)
              if (close) setEditing(null)
              await load()
            }}
          />
        )}
      </div>
    </>
  )
}

function Panel({ children, onClose, wide }: { children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <Overlay onClose={onClose}>
      <div
        className={cn("max-h-[92vh] w-full overflow-y-auto rounded-2xl border border-border bg-card p-6", wide ? "max-w-3xl" : "max-w-md")}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </Overlay>
  )
}

function CreateMember({
  roles,
  catalog,
  onClose,
  onSaved,
}: {
  roles: Role[]
  catalog: PermissionInfo[]
  onClose: () => void
  onSaved: (note: string) => Promise<void>
}) {
  const [role, setRole] = useState("cashier")
  const [customize, setCustomize] = useState(false)
  const [overrides, setOverrides] = useState<Overrides>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const baseline = useMemo(() => new Set(roles.find((r) => r.name === role)?.permissions ?? []), [roles, role])
  const effective = useMemo(
    () => new Set(catalog.filter((e) => effectiveFor(e, baseline, overrides[e.code] ?? "INHERIT")).map((e) => e.code)),
    [catalog, baseline, overrides],
  )
  const custom = Object.entries(overrides).filter(([, s]) => s !== "INHERIT")

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setBusy(true)
    setError(null)
    try {
      await api("/users", {
        method: "POST",
        body: JSON.stringify({
          email: fd.get("email"),
          password: fd.get("password"),
          full_name: fd.get("full_name"),
          role,
          permission_overrides: Object.fromEntries(custom),
        }),
      })
      await onSaved("Staff account created")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel onClose={onClose} wide={customize}>
      <form className="space-y-3" onSubmit={submit}>
        <h3 className="text-lg font-semibold">Add staff</h3>
        <label className="block text-sm">Full name
          <input name="full_name" required className="mt-1 h-10 w-full rounded-lg border border-border px-3" />
        </label>
        <label className="block text-sm">Email
          <input name="email" type="email" required className="mt-1 h-10 w-full rounded-lg border border-border px-3" />
        </label>
        <label className="block text-sm">Role
          <select value={role} onChange={(e) => setRole(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-border px-3">
            {roles.map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
          </select>
        </label>
        <label className="block text-sm">Password
          <input name="password" type="password" minLength={8} required className="mt-1 h-10 w-full rounded-lg border border-border px-3" />
        </label>
        <div className="rounded-xl border border-border bg-muted/30 p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-sm font-medium">Permissions</p>
              <p className="text-xs text-muted-foreground">
                Starts with the {role} role: {baseline.size} permissions.
                {custom.length > 0 ? ` ${custom.length} customised.` : " No customisations."}
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => setCustomize((v) => !v)}>
              {customize ? "Hide" : "Customise (optional)"}
            </Button>
          </div>
          {catalog.length > 0 && (
            <div className="mt-2">
              <AccessChips access={moduleAccess(catalog, effective)} />
            </div>
          )}
          {customize && (
            <div className="mt-3">
              <PermissionMatrix
                catalog={catalog}
                baseline={baseline}
                overrides={overrides}
                onChange={(code, state) => setOverrides((o) => ({ ...o, [code]: state }))}
              />
            </div>
          )}
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create account"}</Button>
        </div>
      </form>
    </Panel>
  )
}

function MemberPanel({
  member,
  roles,
  catalog,
  selfId,
  canDelete,
  onClose,
  onSaved,
}: {
  member: User
  roles: Role[]
  catalog: PermissionInfo[]
  selfId?: string
  canDelete: boolean
  onClose: () => void
  onSaved: (note: string, close: boolean) => Promise<void>
}) {
  const [tab, setTab] = useState<"details" | "permissions">("details")
  return (
    <Panel onClose={onClose} wide={tab === "permissions"}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">{member.full_name}</h3>
          <p className="text-sm text-muted-foreground">{member.email}</p>
        </div>
        <Badge variant={member.role === "admin" ? "default" : "neutral"}>{member.role}</Badge>
      </div>
      <div className="mb-4 inline-flex rounded-lg border border-border bg-muted/40 p-0.5">
        {(["details", "permissions"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium capitalize",
              tab === t ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "details" ? (
        <MemberDetails member={member} roles={roles} selfId={selfId} canDelete={canDelete} onClose={onClose} onSaved={onSaved} />
      ) : (
        <MemberPermissions member={member} catalog={catalog} onSaved={(note) => onSaved(note, false)} />
      )}
    </Panel>
  )
}

function MemberDetails({
  member,
  roles,
  selfId,
  canDelete,
  onClose,
  onSaved,
}: {
  member: User
  roles: Role[]
  selfId?: string
  canDelete: boolean
  onClose: () => void
  onSaved: (note: string, close: boolean) => Promise<void>
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const isSelf = member.id === selfId

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setBusy(true)
    setError(null)
    try {
      const password = String(fd.get("password") || "")
      await api(`/users/${member.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          full_name: fd.get("full_name"),
          role: isSelf ? undefined : fd.get("role"),
          is_active: fd.get("is_active") === "true",
          password: password || undefined,
        }),
      })
      await onSaved("Staff account updated", true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed")
    } finally {
      setBusy(false)
    }
  }

  const deactivate = async () => {
    setBusy(true)
    try {
      await api(`/users/${member.id}`, { method: "DELETE" })
      await onSaved("Staff account deactivated", true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Deactivate failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="space-y-3" onSubmit={submit}>
      <label className="block text-sm">Full name
        <input name="full_name" required defaultValue={member.full_name} className="mt-1 h-10 w-full rounded-lg border border-border px-3" />
      </label>
      <label className="block text-sm">Role
        <select name="role" disabled={isSelf} defaultValue={member.role} className="mt-1 h-10 w-full rounded-lg border border-border px-3 disabled:opacity-60">
          {roles.map((role) => <option key={role.name} value={role.name}>{role.name}</option>)}
        </select>
        <span className="mt-1 block text-xs text-muted-foreground">
          {isSelf ? "You cannot change your own role." : "Changing the role keeps this person's individual permission overrides."}
        </span>
      </label>
      <label className="block text-sm">Status
        <select name="is_active" defaultValue={String(member.is_active)} className="mt-1 h-10 w-full rounded-lg border border-border px-3">
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </label>
      <label className="block text-sm">New password (optional)
        <input name="password" type="password" minLength={8} className="mt-1 h-10 w-full rounded-lg border border-border px-3" />
      </label>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        {canDelete && !isSelf && (
          <Button type="button" variant="ghost" disabled={busy} onClick={deactivate}>Deactivate</Button>
        )}
        <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
      </div>
    </form>
  )
}

function MemberPermissions({
  member,
  catalog,
  onSaved,
}: {
  member: User
  catalog: PermissionInfo[]
  onSaved: (note: string) => Promise<void>
}) {
  const [detail, setDetail] = useState<UserPermissions | null>(null)
  const [pending, setPending] = useState<Overrides>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<UserPermissions>(`/users/${member.id}/permissions`)
      .then(setDetail)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load permissions"))
  }, [member.id])

  const saved = useMemo<Overrides>(
    () => Object.fromEntries((detail?.permissions ?? []).filter((p) => p.override !== "INHERIT").map((p) => [p.code, p.override])),
    [detail],
  )
  const baseline = useMemo(() => new Set((detail?.permissions ?? []).filter((p) => p.role_default).map((p) => p.code)), [detail])
  const current = useMemo(() => ({ ...saved, ...pending }), [saved, pending])
  const effective = useMemo(
    () => new Set(catalog.filter((e) => effectiveFor(e, baseline, current[e.code] ?? "INHERIT")).map((e) => e.code)),
    [catalog, baseline, current],
  )
  const pendingCount = Object.keys(pending).length

  if (error && !detail) return <p className="text-sm text-destructive">{error}</p>
  if (!detail) return <p className="text-sm text-muted-foreground">Loading permissions…</p>

  const change = (code: string, state: OverrideState) => {
    setPending((p) => {
      const next = { ...p }
      if ((saved[code] ?? "INHERIT") === state) delete next[code]
      else next[code] = state
      return next
    })
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await api<UserPermissions>(`/users/${member.id}/permissions`, {
        method: "PUT",
        body: JSON.stringify({ overrides: pending }),
      })
      setDetail(res)
      setPending({})
      await onSaved(`Permissions updated for ${member.full_name}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save permissions")
    } finally {
      setBusy(false)
    }
  }

  const reset = async () => {
    if (!window.confirm(`Reset ${member.full_name} to the ${detail.role} role defaults? All ${detail.override_count} individual overrides will be removed.`)) return
    setBusy(true)
    setError(null)
    try {
      const res = await api<UserPermissions>(`/users/${member.id}/permissions/reset`, { method: "POST" })
      setDetail(res)
      setPending({})
      await onSaved(`${member.full_name} reset to ${detail.role} defaults`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset permissions")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-muted/30 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm">
            <span className="font-medium">Role baseline:</span> {detail.role} ·{" "}
            <span className="font-medium">Overrides:</span> {detail.override_count}
            {pendingCount > 0 && <span className="text-warning-foreground"> · {pendingCount} unsaved</span>}
          </p>
          {detail.editable && (
            <Button type="button" variant="outline" size="sm" disabled={busy || detail.override_count === 0} onClick={reset}>
              Reset to role defaults
            </Button>
          )}
        </div>
        <div className="mt-2">
          <AccessChips access={moduleAccess(catalog, effective)} />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Inherit uses the role. Allow or Deny applies to this person only and wins over the role. Admin-only permissions always follow the role.
        </p>
      </div>
      {!detail.editable && detail.not_editable_reason && (
        <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">{detail.not_editable_reason}</p>
      )}
      <PermissionMatrix
        catalog={catalog}
        baseline={baseline}
        overrides={current}
        onChange={detail.editable ? change : undefined}
        readOnly={!detail.editable || busy}
        changed={new Set(Object.keys(pending))}
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {detail.editable && (
        <div className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-card pt-3">
          <Button type="button" variant="outline" disabled={busy || pendingCount === 0} onClick={() => setPending({})}>Discard changes</Button>
          <Button type="button" disabled={busy || pendingCount === 0} onClick={save}>
            {busy ? "Saving…" : pendingCount ? `Save ${pendingCount} change${pendingCount === 1 ? "" : "s"}` : "Save"}
          </Button>
        </div>
      )}
    </div>
  )
}
