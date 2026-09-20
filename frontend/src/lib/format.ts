export function currency(n: number) {
  return new Intl.NumberFormat("en-GH", { style: "currency", currency: "GHS" }).format(n)
}

function century(year: number) {
  return year < 1000 ? year + 2000 : year
}

function localDate(year: number, month: number, day: number) {
  const then = new Date(year, month - 1, day)
  return Number.isNaN(then.getTime()) || then.getFullYear() !== year || then.getMonth() !== month - 1 || then.getDate() !== day
    ? null
    : then
}

/** Two-digit years like 0027-09-16 were stored as year 27 AD. Treat those as 20xx. */
export function parseExpiry(dateStr: string) {
  if (!dateStr) return null
  const raw = dateStr.trim().replace("T", " ").split(/\s/)[0]
  const iso = raw.match(/^(\d{3,4})-(\d{1,2})-(\d{1,2})/)
  if (iso) return localDate(century(Number(iso[1])), Number(iso[2]), Number(iso[3]))
  const isoSlash = raw.match(/^(\d{3,4})\/(\d{1,2})\/(\d{1,2})$/)
  if (isoSlash) return localDate(century(Number(isoSlash[1])), Number(isoSlash[2]), Number(isoSlash[3]))
  const dmy = raw.match(/^(\d{1,2})[/.](\d{1,2})[/.](\d{2}|\d{4})$/)
  if (dmy) return localDate(century(Number(dmy[3])), Number(dmy[2]), Number(dmy[1]))
  const dmyDash = raw.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/)
  if (dmyDash) return localDate(century(Number(dmyDash[3])), Number(dmyDash[2]), Number(dmyDash[1]))
  const ymdShort = raw.match(/^(\d{1,2})-(\d{1,2})-(\d{2})$/)
  if (ymdShort) return localDate(century(Number(ymdShort[1])), Number(ymdShort[2]), Number(ymdShort[3]))
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return null
  if (parsed.getFullYear() < 1000) parsed.setFullYear(parsed.getFullYear() + 2000)
  return parsed
}

export function normalizeExpiryInput(raw: string) {
  const then = parseExpiry(raw)
  if (!then) return raw.trim()
  const y = then.getFullYear()
  const m = String(then.getMonth() + 1).padStart(2, "0")
  const d = String(then.getDate()).padStart(2, "0")
  return `${y}-${m}-${d}`
}

export function daysUntil(dateStr: string) {
  const then = parseExpiry(dateStr)
  if (!then) return null
  return Math.round((then.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
}

export function formatExpiry(dateStr: string, opts?: Intl.DateTimeFormatOptions) {
  const then = parseExpiry(dateStr)
  if (!then) return "Invalid date"
  return then.toLocaleDateString("en-GH", opts ?? { day: "numeric", month: "short", year: "numeric" })
}

export function daysLeftLabel(dateStr: string) {
  const days = daysUntil(dateStr)
  if (days === null) return "Invalid date"
  if (days < -1) return `Expired ${Math.abs(days)} days ago`
  if (days === -1) return "Expired yesterday"
  if (days === 0) return "Expires today"
  if (days === 1) return "1 day left"
  return `${days} days left`
}

export function relativeTime(iso: string) {
  if (!iso) return ""
  const then = new Date(iso).getTime()
  const diff = Date.now() - then
  const mins = Math.round(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? "yesterday" : `${days}d ago`
}
