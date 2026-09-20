import { TrendingUp } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { BarChart } from "@/components/charts"
import type { Dashboard } from "@/lib/api/types"
import { currency } from "@/lib/format"

export function RevenueCard({
  weeklyRevenue,
  weeklyTrend,
}: {
  weeklyRevenue: Dashboard["weekly_revenue"]
  weeklyTrend: Dashboard["weekly_trend"]
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">This week&apos;s revenue</h3>
        <Badge variant="success">
          <TrendingUp className="size-3" /> live
        </Badge>
      </div>
      <p className="mt-2 text-3xl font-semibold tracking-tight">{currency(weeklyRevenue)}</p>
      {weeklyTrend.length ? (
        <BarChart data={weeklyTrend} className="mt-5 h-32" currencyFormat />
      ) : (
        <p className="mt-8 text-sm text-muted-foreground">No sales recorded this week.</p>
      )}
    </div>
  )
}
