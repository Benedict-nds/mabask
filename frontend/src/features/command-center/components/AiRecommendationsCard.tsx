import { ArrowRight, Sparkles } from "lucide-react"
import { ButtonLink } from "@/components/ui/button"
import type { Dashboard } from "@/lib/api/types"

export function AiRecommendationsCard({ insights }: { insights: Dashboard["insights"] }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 lg:col-span-2">
      <div className="flex items-center gap-2">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Sparkles className="size-4" />
        </span>
        <div>
          <h3 className="text-sm font-semibold">Today&apos;s recommendations</h3>
          <p className="text-xs text-muted-foreground">Computed from live inventory and sales</p>
        </div>
        <ButtonLink href="/copilot" variant="ghost" size="sm" className="ml-auto gap-1">
          Ask more <ArrowRight className="size-3.5" />
        </ButtonLink>
      </div>
      <div className="mt-4 flex flex-col gap-2.5">
        {insights.map((ins, i) => (
          <div key={i} className="flex items-start gap-3 rounded-xl border border-border bg-background p-3.5">
            <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-secondary/10 text-xs font-semibold text-secondary">
              {i + 1}
            </span>
            <p className="flex-1 text-sm leading-relaxed">{ins.text}</p>
            <ButtonLink href={ins.href} variant="outline" size="sm" className="shrink-0">
              {ins.action}
            </ButtonLink>
          </div>
        ))}
      </div>
    </div>
  )
}
