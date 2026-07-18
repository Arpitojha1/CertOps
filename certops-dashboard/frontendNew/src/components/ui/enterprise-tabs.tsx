import { NavLink } from "react-router-dom"
import { cn } from "@/lib/utils"

const ENTERPRISE_TABS = [
  { path: "/enterprise/insights", label: "Insights" },
  { path: "/enterprise/inventory", label: "Inventory" },
  { path: "/enterprise/actions", label: "Actions" },
  { path: "/enterprise/discovery", label: "Discovery" },
  { path: "/enterprise/health", label: "Health & Analytics" },
  { path: "/enterprise/policies", label: "Groups & Policies" },
  { path: "/enterprise/logs", label: "Alerts & Logs" },
]

export function EnterpriseTabs() {
  return (
    <div className="flex items-center gap-2 mb-8 overflow-x-auto pb-2 scrollbar-hide border-b border-neutral-100">
      {ENTERPRISE_TABS.map((tab) => (
        <NavLink
          key={tab.path}
          to={tab.path}
          className={({ isActive }) => cn(
            "whitespace-nowrap px-4 py-2 rounded-full text-sm font-bold transition-all border",
            isActive 
              ? "bg-white text-brand-dark border-neutral-200 shadow-sm" 
              : "border-transparent text-neutral-500 hover:text-brand-dark hover:bg-neutral-50"
          )}
        >
          {tab.label}
        </NavLink>
      ))}
    </div>
  )
}
