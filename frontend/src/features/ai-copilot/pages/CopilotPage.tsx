"use client"

import { useEffect, useRef, useState } from "react"
import { Sparkles, Send, ArrowRight, User } from "lucide-react"
import { AppTopbar } from "@/components/app-topbar"
import { Button, ButtonLink } from "@/components/ui/button"
import { api } from "@/lib/api/client"
import type { CopilotAnswer, CopilotStatus } from "@/lib/api/types"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"

type Msg = { role: "user" | "ai"; text: string; table?: CopilotAnswer["table"]; actions?: string[]; followups?: string[] }

const suggestions = [
  "Show medicines expiring next month",
  "How much revenue did we make today?",
  "Which medicines should be reordered?",
]

const ACTION_HREFS: Record<string, string> = {
  "Open full report": "/reports",
  "Open suppliers": "/suppliers",
  "Draft purchase orders": "/suppliers",
  "Create clearance promotion": "/inventory",
}

function exportTable(table: NonNullable<CopilotAnswer["table"]>) {
  const lines = [table.head, ...table.rows].map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "copilot-export.csv"
  a.click()
  URL.revokeObjectURL(url)
}

export default function CopilotPage() {
  const { user } = useAuth()
  const [status, setStatus] = useState<CopilotStatus | null>(null)
  const [messages, setMessages] = useState<Msg[]>([
    { role: "ai", text: `Hi ${user?.full_name.split(" ")[0] ?? "there"}. I can answer from this pharmacy's inventory and sales on this computer.`, followups: suggestions },
  ])
  const [input, setInput] = useState("")
  const [thinking, setThinking] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api<CopilotStatus>("/copilot/status").then(setStatus).catch(() => setStatus(null))
  }, [])

  const send = async (q: string) => {
    if (!q.trim() || thinking) return
    setMessages((m) => [...m, { role: "user", text: q }])
    setInput("")
    setThinking(true)
    try {
      const res = await api<CopilotAnswer>("/copilot/ask", { method: "POST", body: JSON.stringify({ question: q }) })
      const note = status && !status.ai_enabled
        ? ""
        : res.llm_used
          ? ""
          : status?.ai_enabled
            ? " Cloud AI could not be reached, so this answer uses local pharmacy data only."
            : ""
      setMessages((m) => [...m, { role: "ai", text: res.text + note, table: res.table, actions: res.actions, followups: res.followups }])
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "I couldn't reach the copilot service. If AetherQore is running, try again. This tool does not need the internet for local inventory and sales answers." }])
    } finally {
      setThinking(false)
      requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: 9e9, behavior: "smooth" }))
    }
  }

  return (
    <>
      <AppTopbar title="AI Copilot" />
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col p-4 md:p-6">
        {status && !status.ai_enabled && (
          <div className="mb-4 rounded-xl border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
            Cloud AI is not configured on this computer (no internet provider key). Questions still run against this pharmacy&apos;s live inventory and sales. Answers are not invented.
          </div>
        )}
        <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto scrollbar-thin pb-4">
          {messages.map((m, i) => (
            <div key={i} className={cn("flex gap-3", m.role === "user" && "justify-end")}>
              {m.role === "ai" && <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Sparkles className="size-4" /></span>}
              <div className={cn("max-w-[85%] animate-fade-up", m.role === "user" && "order-1")}>
                <div className={cn("rounded-2xl px-4 py-3 text-sm leading-relaxed", m.role === "user" ? "bg-secondary text-secondary-foreground rounded-tr-sm" : "border border-border bg-card rounded-tl-sm")}>
                  {m.text}
                  {m.table && (
                    <div className="mt-3 overflow-hidden rounded-xl border border-border">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-muted/60 text-left text-muted-foreground">
                            {m.table.head.map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {m.table.rows.map((r, ri) => (
                            <tr key={ri} className="border-t border-border">
                              {r.map((c, ci) => <td key={ci} className={cn("px-3 py-2", ci === 0 && "font-medium")}>{c}</td>)}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {m.actions && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {m.actions.map((a) => {
                        const href = ACTION_HREFS[a]
                        const className = "gap-1.5 bg-background"
                        if (href) {
                          return (
                            <ButtonLink key={a} href={href} size="sm" variant="outline" className={className}>
                              {a} <ArrowRight className="size-3.5" />
                            </ButtonLink>
                          )
                        }
                        if (a === "Export list" && m.table) {
                          return (
                            <Button key={a} size="sm" variant="outline" className={className} onClick={() => exportTable(m.table!)}>
                              {a} <ArrowRight className="size-3.5" />
                            </Button>
                          )
                        }
                        return null
                      })}
                    </div>
                  )}
                </div>
                {m.followups && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {m.followups.map((f) => (
                      <button key={f} onClick={() => send(f)} className="rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground">{f}</button>
                    ))}
                  </div>
                )}
              </div>
              {m.role === "user" && <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-secondary/10 text-secondary"><User className="size-4" /></span>}
            </div>
          ))}
          {thinking && (
            <div className="flex gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Sparkles className="size-4" /></span>
              <div className="flex items-center gap-1.5 rounded-2xl border border-border bg-card px-4 py-3.5">
                <span className="size-2 animate-aether-pulse rounded-full bg-primary" />
                <span className="size-2 animate-aether-pulse rounded-full bg-primary" style={{ animationDelay: "200ms" }} />
                <span className="size-2 animate-aether-pulse rounded-full bg-primary" style={{ animationDelay: "400ms" }} />
              </div>
            </div>
          )}
        </div>
        <div className="rounded-2xl border border-border bg-card p-2 shadow-sm">
          <div className="flex items-end gap-2">
            <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(input) } }} rows={1} placeholder="Ask about inventory, sales, suppliers…" className="max-h-32 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none" />
            <Button size="icon" className="size-9 shrink-0" onClick={() => send(input)} disabled={!input.trim() || thinking} aria-label="Send"><Send className="size-4" /></Button>
          </div>
        </div>
        <p className="mt-2 text-center text-[11px] text-muted-foreground">Answers are grounded in this pharmacy&apos;s database. Clinical decisions stay with a licensed pharmacist.</p>
      </div>
    </>
  )
}
