import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { apiGet, apiPost } from "./api";

type Plan = "None" | "Starter" | "Professional" | "Enterprise";

export interface UserProfile {
  id: number;
  email: string;
  role: string;
  tenant_id?: string;
}

interface AppState {
  plan: Plan;
  setPlan: (plan: Plan) => void;
  isSidebarCollapsed: boolean;
  setIsSidebarCollapsed: (collapsed: boolean) => void;
  user: UserProfile | null;
  setUser: (user: UserProfile | null) => void;
  isLoadingAuth: boolean;
  checkAuth: () => Promise<void>;
  logout: () => Promise<void>;
}

const AppContext = createContext<AppState | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [plan, setPlanState] = useState<Plan>(() => {
    return (localStorage.getItem("certops_plan") as Plan) || "Starter";
  });
  const setPlan = useCallback((newPlan: Plan) => {
    localStorage.setItem("certops_plan", newPlan);
    setPlanState(newPlan);
  }, []);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);

  const checkAuth = useCallback(async () => {
    setIsLoadingAuth(true);
    try {
      const p = await apiGet<UserProfile>("/auth/me");
      setUser(p);
      if (p.tenant_id) {
        localStorage.setItem("certops_tenant_id", p.tenant_id);
      }
    } catch {
      setUser(null);
    } finally {
      setIsLoadingAuth(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost("/auth/logout", {});
    } catch {
      // ignore errors on logout
    } finally {
      setUser(null);
      localStorage.removeItem("certops_tenant_id");
      window.location.href = "/login";
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  return (
    <AppContext.Provider
      value={{
        plan,
        setPlan,
        isSidebarCollapsed,
        setIsSidebarCollapsed,
        user,
        setUser,
        isLoadingAuth,
        checkAuth,
        logout,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useAppStore() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error("useAppStore must be used within an AppProvider");
  }
  return context;
}
