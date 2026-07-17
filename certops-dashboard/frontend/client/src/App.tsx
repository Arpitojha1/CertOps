import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch, useLocation } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Sidebar from "./components/Sidebar";
import Navigation from "./components/Navigation";

// Public pages
import LandingPage from "./pages/LandingPage";
import PricingPage from "./pages/PricingPage";
import ContactPage from "./pages/ContactPage";

// Authenticated pages
import ConnectorsPage from "./pages/ConnectorsPage";
import CertificatesPage from "./pages/CertificatesPage";
import ActivityPage from "./pages/ActivityPage";
import GroupsPage from "./pages/GroupsPage";
import NotificationsPage from "./pages/NotificationsPage";
import SchedulerPage from "./pages/SchedulerPage";
import DashboardHome from "./pages/DashboardHome";
import ProfilePage from "./pages/ProfilePage";
import SettingsPage from "./pages/SettingsPage";

function ProtectedRoute({
  component: Component,
}: {
  component: React.ComponentType;
}) {
  const { isAuthenticated, isLoading } = useAuth();
  const [, navigate] = useLocation();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-border border-t-foreground rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    navigate("/");
    return null;
  }

  return <Component />;
}

function Router() {
  const { isAuthenticated } = useAuth();
  const [location] = useLocation();
  const isNotFound = location === "/404";
  const isPublicPage = ["/", "/pricing", "/contact"].includes(location);
  const isDashboardPage = !isPublicPage && !isNotFound;
  // Landing page uses window-level scroll so GSAP ScrollTrigger works correctly
  const isLandingPage = location === "/";

  return (
    <div
      className={`flex ${isLandingPage ? "min-h-screen" : "h-screen"} bg-background`}
    >
      {isAuthenticated && isDashboardPage && !isNotFound && <Sidebar />}
      <div
        className={`flex-1 flex flex-col ${isLandingPage ? "" : "overflow-hidden"}`}
      >
        <Navigation />
        <main className={`flex-1 ${isLandingPage ? "" : "overflow-auto"}`}>
          <Switch>
            {/* Public */}
            <Route path="/" component={LandingPage} />
            <Route path="/pricing" component={PricingPage} />
            <Route path="/contact" component={ContactPage} />

            {/* Authenticated */}
            <Route
              path="/dashboard"
              component={() => <ProtectedRoute component={DashboardHome} />}
            />
            <Route
              path="/connectors"
              component={() => <ProtectedRoute component={ConnectorsPage} />}
            />
            <Route
              path="/certificates"
              component={() => <ProtectedRoute component={CertificatesPage} />}
            />
            <Route
              path="/activity"
              component={() => <ProtectedRoute component={ActivityPage} />}
            />
            <Route
              path="/groups"
              component={() => <ProtectedRoute component={GroupsPage} />}
            />
            <Route
              path="/notifications"
              component={() => <ProtectedRoute component={NotificationsPage} />}
            />
            <Route
              path="/scheduler"
              component={() => <ProtectedRoute component={SchedulerPage} />}
            />
            <Route
              path="/profile"
              component={() => <ProtectedRoute component={ProfilePage} />}
            />
            <Route
              path="/settings"
              component={() => <ProtectedRoute component={SettingsPage} />}
            />

            {/* 404 */}
            <Route path="/404" component={NotFound} />
            <Route component={NotFound} />
          </Switch>
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="light">
        <AuthProvider>
          <TooltipProvider>
            <Toaster />
            <Router />
          </TooltipProvider>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
