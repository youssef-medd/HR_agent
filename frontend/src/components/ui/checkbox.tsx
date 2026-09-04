"use client"

import * as React from "react"
import { Checkbox as CheckboxPrimitive } from "radix-ui"
import { Check, Minus } from "lucide-react"

import { cn } from "@/lib/utils"

function Checkbox({
  className,
  checked,
  indeterminate,
  ...props
}: Omit<React.ComponentProps<typeof CheckboxPrimitive.Root>, "checked"> & {
  checked?: boolean | "indeterminate"
  /** Convenience flag — wins over `checked`, renders the dash state. */
  indeterminate?: boolean
}) {
  const state: boolean | "indeterminate" = indeterminate
    ? "indeterminate"
    : (checked ?? false)

  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      checked={state}
      className={cn(
        "peer size-4 shrink-0 rounded-[5px] border border-input bg-background outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
        "data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
        "data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="flex items-center justify-center text-current"
      >
        {state === "indeterminate" ? (
          <Minus className="size-3" aria-hidden />
        ) : (
          <Check className="size-3" aria-hidden />
        )}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
