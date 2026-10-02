"use client"

import { useId, useState, type InputHTMLAttributes, type ReactNode } from "react"
import { Eye, EyeOff } from "lucide-react"
import { cn } from "@/lib/utils"

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  /** Classes for the bordered wrapper that holds the input and the toggle. */
  wrapperClassName?: string
  /** Optional icon or content rendered before the input, inside the wrapper. */
  leading?: ReactNode
}

/** Password field with its own show/hide toggle. Visibility is local to each field. */
export function PasswordInput({ wrapperClassName, leading, className, id, ...props }: PasswordInputProps) {
  const [visible, setVisible] = useState(false)
  const generatedId = useId()
  const inputId = id ?? generatedId
  const label = visible ? "Hide password" : "Show password"

  return (
    <div
      className={cn(
        "flex h-10 items-center rounded-lg border border-border focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20",
        wrapperClassName,
      )}
    >
      {leading}
      <input
        {...props}
        id={inputId}
        type={visible ? "text" : "password"}
        autoComplete={props.autoComplete ?? "new-password"}
        className={cn("h-full min-w-0 flex-1 bg-transparent px-3 text-sm outline-none", className)}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={label}
        aria-controls={inputId}
        title={label}
        className="mr-1 flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {visible ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
      </button>
    </div>
  )
}
