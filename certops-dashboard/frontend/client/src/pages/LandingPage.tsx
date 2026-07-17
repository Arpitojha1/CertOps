import { Link, useLocation } from "wouter";
import { useAuth } from "@/contexts/AuthContext";
import { useState, useEffect, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import DotField from "@/components/DotField";
import ScrollStack from "@/components/ScrollStack";
import Vault3D from "@/components/Vault3D";
import ScrollFloat from "@/components/ScrollFloat";
import { Shield } from "lucide-react";
import Lenis from "lenis";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

function LoginDialog({
  open,
  onOpenChange,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSuccess: () => void;
}) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) {
      setError("Email and password are required.");
      return;
    }
    setError("");
    setIsSubmitting(true);
    try {
      await login(email, password);
      onOpenChange(false);
      onSuccess();
    } catch {
      setError("Invalid credentials. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Log In to CertOps</DialogTitle>
          <DialogDescription>
            Enter your credentials to access the dashboard.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label htmlFor="login-email">Email</Label>
            <Input
              id="login-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleLogin()}
            />
          </div>
          <div>
            <Label htmlFor="login-password">Password</Label>
            <Input
              id="login-password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleLogin()}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button
            onClick={handleLogin}
            className="w-full"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Logging in..." : "Log In"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const NAV_ITEMS = [
  { label: "Product", href: "/" },
  { label: "Pricing", href: "/pricing" },
  { label: "Contact", href: "/contact" },
];

const FOOTER_LINKS = [
  {
    heading: "Product",
    links: [
      { label: "Overview", href: "/" },
      { label: "Pricing", href: "/pricing" },
    ],
  },
  {
    heading: "Resources",
    links: [
      { label: "Docs", href: "#" }, // TODO: link to public runbook when hosted
      { label: "Contact", href: "/contact" },
    ],
  },
];

/**
 * Landing page footer — a genuine standout moment, not an afterthought strip.
 *
 * Uses GSAP ScrollTrigger to stagger-reveal the footer content as it scrolls
 * into view. This justifies the animation: the footer is the last thing the
 * visitor sees, so the reveal creates a sense of arrival and intentionality
 * rather than an abrupt end.
 *
 * ponytail: GSAP (already installed) covers this — no anime.js needed. Single
 * consumer, so this is inline in LandingPage rather than its own file.
 */
function LandingFooter({ onLoginClick }: { onLoginClick: () => void }) {
  const footerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = footerRef.current;
    if (!el) return;

    const items = gsap.utils.toArray<HTMLElement>(
      ".lp-footer-item",
      el
    );

    gsap.set(items, { opacity: 0, y: 30 });

    const ctx = gsap.context(() => {
      gsap.to(items, {
        opacity: 1,
        y: 0,
        duration: 0.6,
        stagger: 0.08,
        ease: "power2.out",
        scrollTrigger: {
          trigger: el,
          start: "top bottom-=100",
          end: "top center",
          scrub: false,
          once: true,
        },
      });
    }, el);

    return () => ctx.revert();
  }, []);

  return (
    <footer
      ref={footerRef}
      className="border-t border-border bg-background"
      style={{ padding: "4rem 2rem 2.5rem" }}
    >
      <div
        style={{
          maxWidth: "1100px",
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "2fr 1fr 1fr",
          gap: "3rem",
        }}
      >
        {/* Brand column */}
        <div className="lp-footer-item">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
              <Shield size={16} className="text-primary-foreground" />
            </div>
            <span
              className="text-foreground"
              style={{
                fontWeight: 700,
                fontSize: "1.1rem",
                letterSpacing: "-0.02em",
              }}
            >
              CertOps
            </span>
          </div>
          <p
            className="text-muted-foreground"
            style={{
              fontSize: "0.9rem",
              lineHeight: 1.7,
              maxWidth: "32ch",
              margin: 0,
            }}
          >
            Vault-to-CA automation bridge. Certificate lifecycle management
            without exposing private keys.
          </p>
          <button
            onClick={onLoginClick}
            className="bg-primary text-primary-foreground hover:opacity-90 rounded-md px-5 py-2.5 text-sm font-semibold mt-6"
          >
            Log in
          </button>
        </div>

        {/* Link columns */}
        {FOOTER_LINKS.map((col) => (
          <div key={col.heading} className="lp-footer-item">
            <h4
              className="text-foreground"
              style={{
                fontWeight: 600,
                fontSize: "0.85rem",
                letterSpacing: "0.04em",
                textTransform: "uppercase",
                marginBottom: "1rem",
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {col.heading}
            </h4>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {col.links.map((link) => (
                <li key={link.label} style={{ marginBottom: "0.6rem" }}>
                  <Link
                    href={link.href}
                    className="text-muted-foreground hover:text-foreground text-sm no-underline"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* Copyright bar */}
      <div
        className="lp-footer-item border-t border-border"
        style={{
          maxWidth: "1100px",
          margin: "2.5rem auto 0",
          paddingTop: "1.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <p className="text-muted-foreground" style={{ fontSize: "0.8rem", margin: 0 }}>
          &copy; 2026 CertOps. All rights reserved.
        </p>
        <p
          className="text-muted-foreground"
          style={{ fontSize: "0.75rem", margin: 0, fontFamily: "'JetBrains Mono', monospace" }}
        >
          v1.0.0
        </p>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  const [, navigate] = useLocation();
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  // Wire Lenis smooth scroll + GSAP ScrollTrigger
  useEffect(() => {
    const lenis = new Lenis({ lerp: 0.08, smoothWheel: true });
    const rafCb = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(rafCb);
    gsap.ticker.lagSmoothing(0);
    lenis.on("scroll", ScrollTrigger.update);
    return () => {
      gsap.ticker.remove(rafCb);
      lenis.destroy();
    };
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Fixed header ── */}
      <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 bg-background/85 backdrop-blur-md border-b border-border">
        <Link
          href="/"
          className="flex items-center gap-2 no-underline text-foreground"
        >
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <Shield size={16} className="text-primary-foreground" />
          </div>
          <span className="font-semibold text-sm tracking-tight">CertOps</span>
        </Link>

        <nav className="flex items-center gap-6">
          {NAV_ITEMS.map(item => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm font-medium text-muted-foreground hover:text-foreground no-underline"
            >
              {item.label}
            </Link>
          ))}
          <button
            onClick={() => setIsDialogOpen(true)}
            className="text-sm font-semibold px-4 py-2 rounded-md bg-primary text-primary-foreground hover:opacity-90"
          >
            Log in
          </button>
        </nav>
      </header>

      {/* ── Hero ── */}
      <section
        className="lp-hero"
        style={{
          position: "relative",
          minHeight: "100dvh",
          display: "flex",
          alignItems: "center",
          overflow: "hidden",
        }}
      >
        {/* Animated dot field background */}
        <DotField />

        {/* Hero content (above the canvas) */}
        <div
          className="lp-hero-inner"
          style={{
            position: "relative",
            zIndex: 1,
            maxWidth: "1100px",
            margin: "0 auto",
            padding: "6rem 2.5rem 4rem",
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "3rem",
            flexWrap: "wrap",
          }}
        >
          {/* Left: headline + CTA */}
          <div style={{ flex: "1 1 0", minWidth: 0, maxWidth: "540px" }}>
            <h1
              style={{
                fontSize: "clamp(2.5rem, 6vw, 4.25rem)",
                fontWeight: 800,
                letterSpacing: "-0.035em",
                lineHeight: 1.05,
                margin: "0 0 1.25rem",
              }}
              className="text-foreground"
            >
              CertOps
            </h1>
            <p
              style={{
                fontSize: "clamp(1rem, 2vw, 1.2rem)",
                lineHeight: 1.65,
                margin: "0 0 2.25rem",
                maxWidth: "46ch",
              }}
              className="text-muted-foreground"
            >
              Vault-to-CA automation bridge. Manage certificate lifecycles
              across secret stores and hosts without exposing private keys.
            </p>
            <div style={{ display: "flex", gap: "0.875rem", flexWrap: "wrap" }}>
              <button
                onClick={() => setIsDialogOpen(true)}
                className="bg-primary text-primary-foreground hover:opacity-90 active:scale-95 rounded-md px-6 py-3 text-sm font-semibold"
              >
                Get Started
              </button>
              <Link
                href="/pricing"
                className="inline-flex items-center border border-border text-muted-foreground hover:text-foreground hover:border-primary rounded-md px-6 py-3 text-sm font-medium no-underline"
              >
                View Pricing
              </Link>
            </div>
          </div>

          {/* Right: 3D vault */}
          <div
            style={{
              flex: "0 0 auto",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "340px",
              height: "340px",
            }}
          >
            <Vault3D />
          </div>
        </div>
      </section>

      <LoginDialog
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
        onSuccess={() => navigate("/dashboard")}
      />

      {/* ── Features (ScrollStack) ── */}
      <ScrollStack />

      {/* ── Wordmark reveal (end-of-scroll) ── */}
      <section
        style={{
          minHeight: "60vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "4rem 2rem",
        }}
        className="bg-background"
      >
        <ScrollFloat
          animationDuration={1.2}
          ease="power3.inOut"
          scrollStart="center bottom+=50%"
          scrollEnd="bottom bottom-=40%"
          stagger={0.04}
        >
          CertOps
        </ScrollFloat>
      </section>

      {/* ── Footer ── */}
      <LandingFooter onLoginClick={() => setIsDialogOpen(true)} />
    </div>
  );
}
