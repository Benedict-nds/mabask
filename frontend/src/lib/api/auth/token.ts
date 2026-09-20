const ACCESS = "aq.access"
const REFRESH = "aq.refresh"

export function getAccessToken() {
  if (typeof window === "undefined") return null
  return localStorage.getItem(ACCESS)
}

export function getRefreshToken() {
  if (typeof window === "undefined") return null
  return localStorage.getItem(REFRESH)
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS, access)
  localStorage.setItem(REFRESH, refresh)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS)
  localStorage.removeItem(REFRESH)
}
