import * as React from "react"
import { cn } from "@/lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "lime" | "purple" | "outline" | "secondary" | "destructive" | "success" | "warning";
  className?: string;
  children?: React.ReactNode;
  key?: React.Key;
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "bg-brand-dark text-white",
    lime: "bg-brand-lime text-brand-dark font-medium",
    purple: "bg-brand-purple text-brand-dark font-medium",
    secondary: "bg-neutral-100 text-neutral-900",
    outline: "border border-neutral-200 text-neutral-950",
    destructive: "bg-red-50 text-red-600 font-medium",
    success: "bg-green-50 text-green-700 font-medium",
    warning: "bg-orange-50 text-orange-700 font-medium",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-neutral-950 focus:ring-offset-2",
        variants[variant],
        className
      )}
      {...props}
    />
  )
}

export { Badge }
