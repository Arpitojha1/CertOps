import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Check } from "lucide-react";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";

export default function PricingPage() {
  const { login } = useAuth();
  const [isLoginDialogOpen, setIsLoginDialogOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleLogin = () => {
    if (email) {
      login(email, password);
      setIsLoginDialogOpen(false);
      setEmail("");
      setPassword("");
    }
  };

  // PLACEHOLDER: Mock pricing tiers for demo purposes
  const tiers = [
    {
      name: "Free",
      price: "$0",
      description: "For small teams",
      features: [
        "Up to 10 certificates",
        "1 secret store connector",
        "Basic renewal alerts",
        "Community support",
      ],
      cta: "Get Started",
      highlighted: false,
    },
    {
      name: "Team",
      price: "$99",
      description: "For growing infrastructure",
      features: [
        "Up to 100 certificates",
        "5 connectors (stores + hosts)",
        "Advanced policy management",
        "Audit logs",
        "Email support",
        "Custom notification thresholds",
      ],
      cta: "Start Free Trial",
      highlighted: true,
    },
    {
      name: "Enterprise",
      price: "Custom",
      description: "For large-scale deployments",
      features: [
        "Unlimited certificates",
        "Unlimited connectors",
        "Advanced security controls",
        "SAML/SSO integration",
        "Dedicated support",
        "SLA guarantee",
        "Custom integrations",
      ],
      cta: "Contact Sales",
      highlighted: false,
    },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <section className="max-w-5xl mx-auto px-8 py-20">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-foreground mb-4">
            Transparent Pricing
          </h1>
          <p className="text-lg text-foreground max-w-2xl mx-auto">
            No hidden fees. No "contact sales" gatekeeping. Pick the tier that
            fits your team.
          </p>
        </div>
      </section>

      {/* Pricing cards */}
      <section className="max-w-5xl mx-auto px-8 pb-24">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {tiers.map(tier => (
            <Card
              key={tier.name}
              className={`p-8 flex flex-col ${
                tier.highlighted ? "ring-2 ring-primary" : ""
              }`}
            >
              {tier.highlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground px-3 py-1 rounded-md text-xs font-semibold">
                  Recommended
                </div>
              )}

              <h2 className="text-xl font-bold text-foreground mb-2">
                {tier.name}
              </h2>
              <p className="text-sm text-muted-foreground mb-6">
                {tier.description}
              </p>

              <div className="mb-8">
                <p className="text-4xl font-bold text-foreground">
                  {tier.price}
                  {tier.price !== "Custom" && (
                    <span className="text-sm text-muted-foreground">/mo</span>
                  )}
                </p>
              </div>

              <Dialog
                open={isLoginDialogOpen}
                onOpenChange={setIsLoginDialogOpen}
              >
                <DialogTrigger asChild>
                  <Button
                    className="w-full mb-8"
                    variant={tier.highlighted ? "default" : "outline"}
                  >
                    {tier.cta}
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Log In to CertOps</DialogTitle>
                    <DialogDescription>
                      Enter any email to access the demo dashboard
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="pricing-email">Email</Label>
                      <Input
                        id="pricing-email"
                        type="email"
                        placeholder="you@example.com"
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                      />
                    </div>
                    <div>
                      <Label htmlFor="pricing-password">Password</Label>
                      <Input
                        id="pricing-password"
                        type="password"
                        placeholder="••••••••"
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                      />
                    </div>
                    <Button onClick={handleLogin} className="w-full">
                      Log In
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>

              <div className="space-y-3">
                {tier.features.map(feature => (
                  <div key={feature} className="flex gap-3">
                    <Check className="w-5 h-5 text-primary flex-shrink-0" />
                    <span className="text-sm text-foreground">{feature}</span>
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section className="max-w-3xl mx-auto px-8 py-20 border-t border-border">
        <h2 className="text-2xl font-bold text-foreground mb-12">Questions</h2>
        <div className="space-y-8">
          <div>
            <h3 className="font-semibold text-foreground mb-2">
              Can I upgrade or downgrade anytime?
            </h3>
            <p className="text-foreground">
              Yes. Changes take effect immediately. We prorate any charges or
              credits.
            </p>
          </div>
          <div>
            <h3 className="font-semibold text-foreground mb-2">
              What happens to my data if I cancel?
            </h3>
            <p className="text-foreground">
              Your certificate inventory and logs remain accessible for 30 days.
              Export anytime.
            </p>
          </div>
          <div>
            <h3 className="font-semibold text-foreground mb-2">
              Do you offer discounts for annual billing?
            </h3>
            <p className="text-foreground">
              Yes. Annual plans get 20% off. Contact sales for details.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-12 mt-20">
        <div className="max-w-5xl mx-auto px-8 flex flex-col md:flex-row items-center justify-between text-sm text-muted-foreground">
          <p>© 2026 CertOps. All rights reserved.</p>
          <div className="flex gap-8 mt-4 md:mt-0">
            <Link href="/">
              <a className="hover:text-foreground transition-colors">Product</a>
            </Link>
            <Link href="/pricing">
              <a className="hover:text-foreground transition-colors">Pricing</a>
            </Link>
            <Link href="/contact">
              <a className="hover:text-foreground transition-colors">Contact</a>
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
