"use client"

import { cn } from "@/lib/utils"
import { currency } from "@/lib/format"

export function BarChart({
  data,
  className,
  currencyFormat = false,
}: {
  data: { label: string; value: number }[]
  className?: string
  currencyFormat?: boolean
}) {
  const format = currencyFormat ? (n: number) => currency(n) : (n: number) => String(n)
  const max = Math.max(...data.map((d) => d.value))
  return (
    <div className={cn("flex items-end gap-2", className)}>
      {data.map((d) => (
        <div key={d.label} className="group flex flex-1 flex-col items-center gap-2">
          <div className="relative flex w-full flex-1 items-end">
            <div
              className="w-full rounded-t-md bg-primary/85 transition-all duration-500 group-hover:bg-primary"
              style={{ height: `${Math.max((d.value / max) * 100, 4)}%` }}
            >
              <span className="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 rounded-md bg-foreground px-1.5 py-0.5 text-[10px] font-medium text-background opacity-0 transition-opacity group-hover:opacity-100">
                {format(d.value)}
              </span>
            </div>
          </div>
          <span className="text-xs text-muted-foreground">{d.label}</span>
        </div>
      ))}
    </div>
  )
}

export function Sparkline({
  data,
  className,
  stroke = "var(--primary)",
}: {
  data: number[]
  className?: string
  stroke?: string
}) {
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const w = 100
  const h = 32
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((v - min) / range) * (h - 4) - 2
    return `${x},${y}`
  })
  const areaPts = `0,${h} ${pts.join(" ")} ${w},${h}`
  const id = `sl-${Math.round(min)}-${data.length}`
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={cn("h-8 w-full", className)}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPts} fill={`url(#${id})`} />
      <polyline points={pts.join(" ")} fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function DonutChart({
  data,
  className,
}: {
  data: { label: string; value: number; color: string }[]
  className?: string
}) {
  const total = data.reduce((a, b) => a + b.value, 0)
  const r = 60
  const c = 2 * Math.PI * r
  let offset = 0
  return (
    <div className={cn("flex items-center gap-6", className)}>
      <svg viewBox="0 0 160 160" className="h-36 w-36 -rotate-90">
        {data.map((d) => {
          const len = (d.value / total) * c
          const seg = (
            <circle
              key={d.label}
              cx="80"
              cy="80"
              r={r}
              fill="none"
              stroke={d.color}
              strokeWidth="20"
              strokeDasharray={`${len} ${c - len}`}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
            />
          )
          offset += len
          return seg
        })}
        <circle cx="80" cy="80" r="42" fill="var(--card)" />
      </svg>
      <div className="flex flex-col gap-2">
        {data.map((d) => (
          <div key={d.label} className="flex items-center gap-2 text-sm">
            <span className="size-2.5 rounded-full" style={{ backgroundColor: d.color }} />
            <span className="text-muted-foreground">{d.label}</span>
            <span className="ml-auto font-medium text-foreground">{d.value}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
