import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Shield, Lock, Mail, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { apiPost } from "@/lib/api";
import { useAppStore, UserProfile } from "@/lib/store";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { setUser } = useAppStore();
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Please enter both email and password.");
      return;
    }
    setError(null);
    setIsLoading(true);

    try {
      const res = await apiPost<UserProfile & { tenant_id?: string }>("/auth/login", {
        email,
        password,
      });
      setUser(res);
      if (res.tenant_id) {
        localStorage.setItem("certops_tenant_id", res.tenant_id);
      }
      navigate("/dashboard");
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || "Invalid credentials";
      setError(detail);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-brand-dark flex flex-col justify-center items-center p-4 relative overflow-hidden">
      {/* Background Decorative Glows */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-purple/20 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brand-lime/10 rounded-full blur-3xl pointer-events-none" />

      {/* Top Header / Logo */}
      <Link to="/" className="flex items-center gap-3 mb-8 z-10 group">
        <div className="w-10 h-10 rounded-full bg-brand-lime flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform">
          <Shield className="w-5 h-5 text-brand-dark fill-brand-dark" />
        </div>
        <span className="text-white font-display font-bold text-2xl tracking-tight">CertOps</span>
      </Link>

      {/* Login Card */}
      <div className="w-full max-w-md bg-neutral-900/80 backdrop-blur-xl border border-neutral-800 rounded-3xl p-8 shadow-2xl z-10">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-white mb-2">Welcome Back</h1>
          <p className="text-neutral-400 text-sm">
            Sign in to access your certificate management dashboard
          </p>
        </div>

        {error && (
          <div className="mb-6 bg-red-500/10 border border-red-500/30 rounded-2xl p-4 flex items-start gap-3 text-red-300 text-sm">
            <AlertCircle className="w-5 h-5 shrink-0 text-red-400 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-5">
          <div>
            <label className="block text-xs font-semibold text-neutral-300 uppercase tracking-wider mb-2">
              Email Address
            </label>
            <div className="relative">
              <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@example.com"
                required
                className="w-full bg-neutral-950/60 border border-neutral-800 rounded-2xl py-3 pl-12 pr-4 text-white placeholder-neutral-600 focus:outline-none focus:border-brand-lime transition-colors text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-300 uppercase tracking-wider mb-2">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                className="w-full bg-neutral-950/60 border border-neutral-800 rounded-2xl py-3 pl-12 pr-4 text-white placeholder-neutral-600 focus:outline-none focus:border-brand-lime transition-colors text-sm"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-brand-lime text-brand-dark font-bold py-3.5 px-6 rounded-2xl flex items-center justify-center gap-2 hover:bg-[#B6D63A] disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg hover:shadow-brand-lime/20 text-sm mt-2"
          >
            {isLoading ? (
              <span>Signing in...</span>
            ) : (
              <>
                <span>Log In</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-neutral-800/80 text-center">
          <p className="text-xs text-neutral-500">
            Running locally for the first time? Make sure you have seeded the admin user using{" "}
            <code className="bg-neutral-800 px-1.5 py-0.5 rounded text-neutral-300">
              seed_admin.py
            </code>
          </p>
        </div>
      </div>
    </div>
  );
}
