import { Activity as ActivityIcon, Bot, PackagePlus, ShoppingCart, Truck, Wallet } from "lucide-react"
import type { Dashboard } from "@/lib/api/types"
import { relativeTime } from "@/lib/format"

const activityIcon: Record<string, typeof Bot> = {
  ai: Bot,
  sale: ShoppingCart,
  shipment: Truck,
  inventory: PackagePlus,
  cash: Wallet,
}

export function RecentActivity({ activity }: { activity: Dashboard["activity"] }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <ActivityIcon className="size-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Recent activity</h3>
      </div>
      <ol className="mt-4 space-y-1">
        {activity.map((a) => {
          const Icon = activityIcon[a.type] ?? ActivityIcon
          return (
            <li key={a.id} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-muted/60">
              <span
                className={`flex size-8 items-center justify-center rounded-full ${
                  a.type === "ai" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                }`}
              >
                <Icon className="size-4" />
              </span>
              <p className="flex-1 text-sm">
                <span className="font-medium">{a.who}</span> <span className="text-muted-foreground">{a.action}</span>
              </p>
              <span className="text-xs text-muted-foreground">{relativeTime(a.time)}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
