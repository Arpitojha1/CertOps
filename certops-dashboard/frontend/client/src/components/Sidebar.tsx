import { Link, useLocation } from "wouter";
import {
  Shield,
  Database,
  Activity,
  Settings,
  Bell,
  Calendar,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function Sidebar() {
  const [location] = useLocation();

  const navItems = [
    { href: "/dashboard", label: "Dashboard", icon: Database },
    { href: "/certificates", label: "Certificates", icon: Shield },
    { href: "/activity", label: "Activity", icon: Activity },
    { href: "/groups", label: "Groups & Policies", icon: Settings },
    { href: "/notifications", label: "Notifications", icon: Bell },
    { href: "/scheduler", label: "Scheduler", icon: Calendar },
  ];

  return (
    <aside className="w-64 border-r border-border bg-sidebar flex flex-col">
      <div className="p-6 border-b border-sidebar-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-semibold text-sm text-sidebar-foreground">
              CertOps
            </h1>
            <p className="text-xs text-sidebar-accent-foreground">Dashboard</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const isActive = location === href;
          return (
            <Link key={href} href={href}>
              <a
                className={cn(
                  "flex items-center gap-3 px-4 py-2.5 rounded-md text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-primary text-sidebar-primary-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent"
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
              </a>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-sidebar-border text-xs text-sidebar-accent-foreground">
        <p>v1.0.0</p>
      </div>
    </aside>
  );
}
