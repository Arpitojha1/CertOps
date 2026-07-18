import { Outlet, NavLink, useLocation, useNavigate, Link, Navigate } from "react-router-dom"
import { 
  Home, 
  Shield, 
  Database, 
  Activity, 
  Users, 
  Bell, 
  Calendar, 
  Settings,
  Search,
  ChevronDown,
  Building2,
  ChevronLeft,
  ChevronRight,
  Menu,
  LogOut
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/lib/store"

const NAV_ITEMS = [
  { path: "/dashboard", icon: Home, label: "Dashboard" },
  { path: "/certificates", icon: Shield, label: "Certificates", badge: 3 },
  { path: "/connectors", icon: Database, label: "Connectors" },
  { path: "/activity", icon: Activity, label: "Activity" },
  { path: "/groups", icon: Users, label: "Groups & Policies" },
  { path: "/notifications", icon: Bell, label: "Notifications" },
  { path: "/scheduler", icon: Calendar, label: "Scheduler" },
  { path: "/settings", icon: Settings, label: "Settings" },
]

function Sidebar() {
  const { isSidebarCollapsed, setIsSidebarCollapsed, plan } = useAppStore();
  const navigate = useNavigate();

  return (
    <aside className={cn("bg-brand-dark h-full flex flex-col justify-between shrink-0 transition-all duration-300", isSidebarCollapsed ? "w-20" : "w-64")}>
      <div className="flex flex-col h-full overflow-y-auto overflow-x-hidden p-4">
        {/* Logo */}
        <div className={cn("flex items-center mb-10", isSidebarCollapsed ? "justify-center" : "gap-3 px-2")}>
          <div className="w-8 h-8 rounded-full bg-brand-lime flex items-center justify-center shrink-0">
            <div className="w-4 h-4 bg-brand-dark rounded-full"></div>
          </div>
          {!isSidebarCollapsed && <span className="text-white font-bold text-xl tracking-tight">CertOps</span>}
        </div>

        {/* Nav */}
        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              title={isSidebarCollapsed ? item.label : undefined}
              className={({ isActive }) => cn(
                "flex items-center px-4 py-3 rounded-xl transition-all group",
                isSidebarCollapsed ? "justify-center px-0" : "gap-3",
                isActive 
                  ? "bg-white text-brand-dark font-semibold shadow-lg" 
                  : "text-neutral-400 hover:text-white"
              )}
            >
              {({ isActive }) => (
                <>
                  <item.icon className={cn("w-5 h-5 shrink-0", !isActive && "opacity-70")} />
                  {!isSidebarCollapsed && <span>{item.label}</span>}
                  {!isSidebarCollapsed && item.badge && (
                    <span className="ml-auto bg-brand-lime text-brand-dark text-[10px] font-bold px-2 py-0.5 rounded-full">
                      {item.badge}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
          
          <div className="my-4 border-t border-neutral-800" />
          
          <NavLink
            to="/enterprise/insights"
            title={isSidebarCollapsed ? "Enterprise Dashboard" : undefined}
            onClick={(e) => {
              if (plan !== "Enterprise") {
                e.preventDefault();
                navigate("/enterprise/upgrade");
              }
            }}
            className={({ isActive }) => cn(
              "flex items-center px-4 py-3 rounded-xl transition-all group",
              isSidebarCollapsed ? "justify-center px-0" : "gap-3",
              isActive 
                ? "bg-white text-brand-dark font-semibold shadow-lg" 
                : "text-neutral-400 hover:text-white"
            )}
          >
            {({ isActive }) => (
              <>
                <Building2 className={cn("w-5 h-5 shrink-0", !isActive && "opacity-70")} />
                {!isSidebarCollapsed && <span>Enterprise Dashboard</span>}
              </>
            )}
          </NavLink>
        </nav>
      </div>

      <div className="p-4 mt-auto">
        {!isSidebarCollapsed && plan !== "Enterprise" && (
          <div className="bg-gradient-to-br from-brand-lime to-[#B6D63A] rounded-2xl p-5 relative overflow-hidden mb-4">
            <div className="absolute -right-4 -top-4 w-24 h-24 bg-black/5 rounded-full blur-xl pointer-events-none" />
            <h4 className="text-brand-dark font-bold text-lg mb-1 leading-tight">Upgrade to Enterprise</h4>
            <p className="text-brand-dark/70 text-xs mb-4 leading-snug">Unlock bulk discovery and policy enforcement.</p>
            <button 
              className="bg-brand-dark text-white py-2 px-4 rounded-full text-xs font-bold"
              onClick={() => navigate('/enterprise/upgrade')}
            >
              Learn More
            </button>
          </div>
        )}
        <button 
          onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          className="w-full flex items-center justify-center p-2 text-neutral-400 hover:text-white hover:bg-white/5 rounded-xl transition-colors"
        >
          {isSidebarCollapsed ? <Menu className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
        </button>
      </div>
    </aside>
  )
}

import * as React from "react"
import { PromptModal } from "@/components/ui/prompt-modal"
import { MOCK_NOTIFICATIONS, MOCK_EVENTS } from "@/mock-data"

function TopBar() {
  const { user, logout } = useAppStore();
  const navigate = useNavigate();
  const [showNotifications, setShowNotifications] = React.useState(false);
  const [searchVal, setSearchVal] = React.useState("");
  const [prompt, setPrompt] = React.useState<{isOpen: boolean, title?: string, desc?: string}>({isOpen: false});

  const displayName = user?.email ? user.email.split("@")[0] : "Admin User";
  const displayEmail = user?.email || "admin@certops.io";
  const initials = displayEmail.slice(0, 2).toUpperCase();
  const roleBadge = user?.role === "admin" ? "Global Admin" : "Viewer";

  const handleSearchSubmit = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      if (searchVal.trim()) {
        navigate(`/certificates?search=${encodeURIComponent(searchVal.trim())}`);
      } else {
        setPrompt({
          isOpen: true,
          title: "Search Inventory",
          desc: "Type a domain or connector name and press Enter to search certificates directly across your inventory."
        });
      }
    }
  };

  return (
    <header className="flex items-center justify-between mb-8 shrink-0 relative z-40">
      <div className="flex items-center gap-2">
        <Link to="/profile" className="flex items-center gap-3 hover:bg-neutral-50 p-1.5 pr-4 rounded-full transition-colors cursor-pointer border border-transparent hover:border-neutral-200">
          <div className="w-10 h-10 bg-brand-purple rounded-full border-2 border-white shadow-sm overflow-hidden flex items-center justify-center font-bold text-sm text-brand-dark">
            {initials}
          </div>
          <div>
            <div className="text-sm font-bold flex items-center gap-1.5 text-neutral-900">
              <span>{displayName}</span>
              <span className="text-[10px] font-semibold bg-brand-lime/30 text-brand-dark px-2 py-0.5 rounded-full border border-brand-lime/40">
                {roleBadge}
              </span>
            </div>
            <div className="text-[11px] text-neutral-500 font-medium tracking-tight">{displayEmail}</div>
          </div>
        </Link>
        <button
          onClick={logout}
          title="Log out"
          className="p-2.5 text-neutral-400 hover:text-red-600 hover:bg-red-50 rounded-full transition-colors border border-transparent hover:border-red-100"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
      
      <div className="flex items-center gap-4 relative">
        <div className="relative flex items-center bg-white px-4 py-2 rounded-full border border-neutral-100 shadow-sm">
          <Search className="w-4 h-4 text-neutral-400 mr-2" />
          <input 
            type="text" 
            placeholder="Search inventory..." 
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
            onKeyDown={handleSearchSubmit}
            className="bg-transparent text-sm outline-none w-48 font-medium placeholder:text-neutral-400"
          />
        </div>
        
        <div className="relative">
          <button 
            onClick={() => setShowNotifications(!showNotifications)} 
            className="relative w-10 h-10 bg-white rounded-full flex items-center justify-center border border-neutral-100 shadow-sm hover:bg-neutral-50 transition-colors"
          >
            <Bell className="w-5 h-5 text-neutral-600" />
            <div className="absolute top-2.5 right-3 w-2.5 h-2.5 bg-brand-lime border-2 border-white rounded-full"></div>
          </button>

          {showNotifications && (
            <>
              <div 
                className="fixed inset-0 z-40" 
                onClick={() => setShowNotifications(false)} 
              />
              <div className="absolute right-0 top-12 w-80 bg-white rounded-3xl p-5 shadow-2xl border border-neutral-100 z-50 animate-in fade-in-0 zoom-in-95">
                <div className="flex items-center justify-between mb-4 border-b border-neutral-100 pb-3">
                  <h4 className="font-display font-bold text-base text-brand-dark">Notifications</h4>
                  <Link 
                    to="/notifications" 
                    onClick={() => setShowNotifications(false)}
                    className="text-xs font-bold text-brand-purple hover:underline"
                  >
                    View all
                  </Link>
                </div>
                
                <div className="space-y-3 max-h-64 overflow-y-auto pr-1 mb-4">
                  {MOCK_EVENTS.slice(0, 3).map((evt) => (
                    <div key={evt.id} className="p-3 rounded-2xl bg-neutral-50 border border-neutral-100 text-xs">
                      <div className="flex items-center justify-between font-bold text-neutral-800 mb-1">
                        <span>{evt.type}</span>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] ${
                          evt.status === "Success" ? "bg-brand-lime/40 text-brand-dark" : "bg-red-100 text-red-700"
                        }`}>{evt.status}</span>
                      </div>
                      <p className="text-neutral-600 font-medium leading-snug">{evt.description}</p>
                    </div>
                  ))}
                  {MOCK_NOTIFICATIONS.slice(0, 1).map((notif) => (
                    <div key={notif.id} className="p-3 rounded-2xl bg-brand-purple/10 border border-brand-purple/20 text-xs">
                      <div className="font-bold text-brand-dark mb-1">Policy: {notif.group}</div>
                      <p className="text-neutral-600 font-medium leading-snug">Thresholds: {notif.threshold}</p>
                    </div>
                  ))}
                </div>

                <button
                  onClick={() => {
                    setShowNotifications(false);
                    setPrompt({
                      isOpen: true,
                      title: "Configure Alert Channel",
                      desc: "Quick alerting setup is not implemented yet. Please manage alert policies from the Notifications page."
                    });
                  }}
                  className="w-full py-2 bg-brand-dark text-white rounded-full text-xs font-bold hover:bg-neutral-800 transition-colors"
                >
                  Configure New Alert
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <PromptModal
        isOpen={prompt.isOpen}
        onClose={() => setPrompt({ isOpen: false })}
        title={prompt.title}
        description={prompt.desc}
      />
    </header>
  )
}

export function MainLayout() {
  const { plan, user, isLoadingAuth } = useAppStore();
  
  if (isLoadingAuth) {
    return (
      <div className="h-screen w-full bg-brand-bg flex items-center justify-center font-sans">
        <div className="text-neutral-600 text-sm font-semibold flex items-center gap-3 bg-white px-6 py-4 rounded-2xl shadow-sm border border-neutral-100">
          <div className="w-5 h-5 border-2 border-brand-lime border-t-transparent rounded-full animate-spin" />
          <span>Verifying authentication...</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (plan === "None") {
    return <Navigate to="/pricing" replace />;
  }

  return (
    <div className="h-screen w-full bg-brand-bg flex items-center justify-center font-sans overflow-hidden">
      <div className="w-full h-full bg-white flex overflow-hidden relative">
        <Sidebar />
        <div className="flex-1 bg-brand-canvas h-full flex flex-col p-8 overflow-hidden relative">
          <TopBar />
          <main className="flex-1 overflow-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
