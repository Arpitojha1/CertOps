import { Link, useLocation } from "wouter";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Shield, LogOut, User, Settings } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

export default function Navigation() {
  const { isAuthenticated, user, logout } = useAuth();
  const [location] = useLocation();
  const isPublicPage = ["/", "/pricing", "/contact"].includes(location);

  // Landing page renders its own inline header; suppress global Navigation there
  if (location === "/") return null;

  return (
    <nav className="border-b border-border bg-card">
      <div className="max-w-7xl mx-auto px-8 py-4 flex items-center justify-between">
        {/* Logo */}
        <Link href={isAuthenticated ? "/dashboard" : "/"}>
          <a className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold text-foreground">CertOps</span>
          </a>
        </Link>

        {/* Public nav */}
        {!isAuthenticated && isPublicPage && (
          <div className="flex items-center gap-6">
            <Link href="/">
              <a
                className={`text-sm font-medium ${location === "/" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                Product
              </a>
            </Link>
            <Link href="/pricing">
              <a
                className={`text-sm font-medium ${location === "/pricing" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                Pricing
              </a>
            </Link>
            <Link href="/contact">
              <a
                className={`text-sm font-medium ${location === "/contact" ? "text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                Contact
              </a>
            </Link>
          </div>
        )}

        {/* Auth section */}
        <div className="flex items-center gap-4">
          {isAuthenticated ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="gap-2">
                  <div className="w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center text-xs font-semibold text-slate-700">
                    {user?.email.charAt(0).toUpperCase()}
                  </div>
                  {user?.email}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  disabled
                  className="text-xs text-muted-foreground"
                >
                  {user?.email}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <Link href="/profile">
                  <DropdownMenuItem asChild>
                    <a className="cursor-pointer gap-2">
                      <User className="w-4 h-4" />
                      Profile
                    </a>
                  </DropdownMenuItem>
                </Link>
                <Link href="/settings">
                  <DropdownMenuItem asChild>
                    <a className="cursor-pointer gap-2">
                      <Settings className="w-4 h-4" />
                      Settings
                    </a>
                  </DropdownMenuItem>
                </Link>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => logout()}
                  className="gap-2 text-red-600"
                >
                  <LogOut className="w-4 h-4" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Link href="/">
              <a>
                <Button variant="default" size="sm">
                  Log in
                </Button>
              </a>
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
