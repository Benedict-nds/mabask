"use client"

import { useEffect, useState } from "react"
import { AppTopbar } from "@/components/app-topbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Overlay } from "@/components/ui/dismissable"
import { api, ApiError } from "@/lib/api/client"
import type { Role, User } from "@/lib/api/types"
import { useAuth } from "@/lib/auth-context"

export default function UsersPage() {
  const { can, user: me } = useAuth()
  const [team, setTeam] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [editing, setEditing] = useState<User | null>(null)
  const [creating, setCreating] = useState(false)

  const load = async () => {
    try {
      const [users, roleList] = await Promise.all([api<User[]>("/users"), api<Role[]>("/users/roles")])
      setTeam(users)
      setRoles(roleList)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load team")
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <>
      <AppTopbar title="Team" />
      <div className="mx-auto w-full max-w-[1100px] flex-1 space-y-5 p-4 md:p-6">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Staff accounts</h2>
            <p className="mt-1 text-sm text-muted-foreground">Create, update, and deactivate pharmacy users. Roles cannot be raised above your own.</p>
          </div>
          {can("users.create") && (
            <Button onClick={() => { setCreating(true); setEditing(null) }}>Add staff</Button>
          )}
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {message && <p className="text-sm text-primary">{message}</p>}
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Last login</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {team.map((member) => (
                <tr key={member.id}>
                  <td className="px-4 py-3 font-medium">{member.full_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{member.email}</td>
                  <td className="px-4 py-3"><Badge variant={member.role === "admin" ? "default" : "neutral"}>{member.role}</Badge></td>
                  <td className="px-4 py-3">{member.is_active ? "Active" : "Inactive"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{member.last_login_at ? new Date(member.last_login_at).toLocaleString() : "—"}</td>
                  <td className="px-4 py-3 text-right">
                    {can("users.update") && (
                      <Button variant="ghost" size="sm" onClick={() => { setEditing(member); setCreating(false) }}>Edit</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(creating || editing) && (
          <UserForm
            roles={roles}
            user={editing}
            selfId={me?.id}
            onClose={() => { setCreating(false); setEditing(null) }}
            onSaved={async (note) => {
              setMessage(note)
              setCreating(false)
              setEditing(null)
              await load()
            }}
            canDelete={can("users.delete")}
          />
        )}
      </div>
    </>
  )
}

function UserForm({
  user,
  roles,
  selfId,
  onClose,
  onSaved,
  canDelete,
}: {
  user: User | null
  roles: Role[]
  selfId?: string
  onClose: () => void
  onSaved: (note: string) => Promise<void>
  canDelete: boolean
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const isSelf = user?.id === selfId

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setBusy(true)
    setError(null)
    try {
      if (user) {
        const password = String(fd.get("password") || "")
        await api(`/users/${user.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            full_name: fd.get("full_name"),
            role: isSelf ? undefined : fd.get("role"),
            is_active: fd.get("is_active") === "true",
            password: password || undefined,
          }),
        })
        await onSaved("Staff account updated")
      } else {
        await api("/users", {
          method: "POST",
          body: JSON.stringify({
            email: fd.get("email"),
            password: fd.get("password"),
            full_name: fd.get("full_name"),
            role: fd.get("role"),
          }),
        })
        await onSaved("Staff account created")
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed")
    } finally {
      setBusy(false)
    }
  }

  const deactivate = async () => {
    if (!user) return
    setBusy(true)
    try {
      await api(`/users/${user.id}`, { method: "DELETE" })
      await onSaved("Staff account deactivated")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Deactivate failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Overlay onClose={onClose}>
      <form className="w-full max-w-md space-y-3 rounded-2xl border border-border bg-card p-6" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3 className="text-lg font-semibold">{user ? "Edit staff" : "Add staff"}</h3>
        <label className="block text-sm">Full name
          <input name="full_name" required defaultValue={user?.full_name} className="mt-1 h-10 w-full rounded-lg border border-border px-3" />
        </label>
        <label className="block text-sm">Email
          <input name="email" type="email" required disabled={!!user} defaultValue={user?.email} className="mt-1 h-10 w-full rounded-lg border border-border px-3 disabled:opacity-60" />
        </label>
        <label className="block text-sm">Role
          <select name="role" disabled={isSelf} defaultValue={user?.role ?? "cashier"} className="mt-1 h-10 w-full rounded-lg border border-border px-3 disabled:opacity-60">
            {roles.map((role) => <option key={role.name} value={role.name}>{role.name}</option>)}
          </select>
        </label>
        {user && (
          <label className="block text-sm">Status
            <select name="is_active" defaultValue={String(user.is_active)} className="mt-1 h-10 w-full rounded-lg border border-border px-3">
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          </label>
        )}
        <label className="block text-sm">{user ? "New password (optional)" : "Password"}
          <input name="password" type="password" minLength={8} required={!user} className="mt-1 h-10 w-full rounded-lg border border-border px-3" />
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          {user && canDelete && !isSelf && (
            <Button type="button" variant="ghost" disabled={busy} onClick={deactivate}>Deactivate</Button>
          )}
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
        </div>
      </form>
    </Overlay>
  )
}
