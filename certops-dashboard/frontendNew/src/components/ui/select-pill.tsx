import * as React from "react"
import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"

export interface SelectPillProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value?: string;
}

const SelectPill = React.forwardRef<HTMLButtonElement, SelectPillProps>(
  ({ className, value, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-between rounded-xl border border-neutral-100 shadow-sm bg-white px-4 py-2 text-sm font-bold text-neutral-700 hover:bg-neutral-50 transition-colors focus:outline-none focus:ring-2 focus:ring-neutral-200",
          className
        )}
        {...props}
      >
        <span>{value || children}</span>
        <ChevronDown className="ml-2 h-4 w-4 text-neutral-400" />
      </button>
    )
  }
)
SelectPill.displayName = "SelectPill"

export { SelectPill }
