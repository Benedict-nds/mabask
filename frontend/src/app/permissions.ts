export const ROUTE_PERMISSIONS: Record<string, string> = {
  "/dashboard": "reports.read",
  "/inventory": "inventory.read",
  "/suppliers": "suppliers.read",
  "/receiving": "purchases.receive",
  "/pos": "sales.create",
  "/corrections": "sales.correction_approve",
  "/reports": "reports.read",
  "/copilot": "ai.use",
  "/settings": "settings.manage",
  "/users": "users.read",
  "/audit": "audit.read",
  "/help": "inventory.read",
}

const HOME_ORDER = ["/dashboard", "/pos", "/inventory", "/receiving", "/suppliers", "/reports", "/copilot", "/audit", "/users", "/settings"]

/** The role's usual landing page, or the first area this user can actually open. */
export function homeFor(user: { role: string; permissions: string[] } | null | undefined) {
  if (!user) return "/dashboard"
  const preferred = user.role === "cashier" ? "/pos" : "/dashboard"
  const allowed = (path: string) => user.permissions.includes(ROUTE_PERMISSIONS[path])
  if (allowed(preferred)) return preferred
  return HOME_ORDER.find(allowed) ?? preferred
}
