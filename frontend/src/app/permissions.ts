export const ROUTE_PERMISSIONS: Record<string, string> = {
  "/dashboard": "reports.read",
  "/inventory": "inventory.read",
  "/suppliers": "suppliers.read",
  "/receiving": "purchases.receive",
  "/pos": "sales.create",
  "/reports": "reports.read",
  "/copilot": "ai.use",
  "/settings": "settings.manage",
  "/users": "users.read",
  "/audit": "audit.read",
  "/help": "inventory.read",
}

export function homeForRole(role: string | undefined) {
  return role === "cashier" ? "/pos" : "/dashboard"
}
