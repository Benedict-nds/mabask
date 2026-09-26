import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./auth/token"
import type { AuthResponse } from "./types"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export { clearTokens, getAccessToken, setTokens }

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json()
    const err = body.error ?? body
    return new ApiError(res.status, err.code ?? "ERROR", err.message ?? res.statusText, err.details ?? {})
  } catch {
    return new ApiError(res.status, "ERROR", res.statusText)
  }
}

async function refreshAccess(): Promise<string | null> {
  const refresh = getRefreshToken()
  if (!refresh) return null
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!res.ok) {
    clearTokens()
    return null
  }
  const data = await res.json()
  setTokens(data.access_token, data.refresh_token)
  return data.access_token
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData) && !headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json")
  }
  const token = getAccessToken()
  if (token) headers.set("Authorization", `Bearer ${token}`)

  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (res.status === 401 && retry && !path.startsWith("/auth/login")) {
    const next = await refreshAccess()
    if (next) return api<T>(path, init, false)
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return res.json()
}

/** Authenticated CSV/file download (does not parse JSON). */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const headers = new Headers()
  const token = getAccessToken()
  if (token) headers.set("Authorization", `Bearer ${token}`)
  let res = await fetch(`${BASE}${path}`, { headers })
  if (res.status === 401) {
    const next = await refreshAccess()
    if (next) {
      headers.set("Authorization", `Bearer ${next}`)
      res = await fetch(`${BASE}${path}`, { headers })
    }
  }
  if (!res.ok) throw await parseError(res)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export const authApi = {
  login: (email: string, password: string) =>
    api<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => api<AuthResponse["user"]>("/auth/me"),
  logout: async () => {
    const refresh = getRefreshToken()
    try {
      if (refresh) await api("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) })
    } finally {
      clearTokens()
    }
  },
}

export { BASE as API_BASE }
