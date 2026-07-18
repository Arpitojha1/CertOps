import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Check, X, ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAppStore } from "@/lib/store";
import { getPlans, subscribeToPlan } from "@/mock-data";

export default function Pricing() {
  const [isAnnual, setIsAnnual] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const { setPlan } = useAppStore();
  const navigate = useNavigate();
  const plans = getPlans();

  const handleSubscribeClick = (planId: string) => {
    if (planId === "Enterprise") {
      document.getElementById("compare")?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    setSelectedPlanId(planId);
    setModalOpen(true);
  };

  const handleConfirmSubscription = async () => {
    if (!selectedPlanId) return;
    setIsSubmitting(true);
    await subscribeToPlan(selectedPlanId);
    setPlan(selectedPlanId as any);
    setIsSubmitting(false);
    setModalOpen(false);
    navigate("/dashboard");
  };

  return (
    <div className="min-h-screen bg-brand-bg font-sans pb-24">
      {/* Header */}
      <div className="bg-brand-dark pt-12 pb-32 px-6 text-center text-white relative">
        <Link to="/" className="absolute top-8 left-8 text-neutral-400 hover:text-white transition-colors">
          <ArrowLeft className="w-6 h-6" />
        </Link>
        <h1 className="text-5xl font-display font-bold tracking-tight mb-4">Simple, transparent pricing</h1>
        <p className="text-neutral-400 text-lg mb-8 max-w-xl mx-auto">
          Choose the plan that fits your infrastructure needs. Automate your certificates today.
        </p>

        {/* Toggle */}
        <div className="flex items-center justify-center gap-4">
          <span className={`text-sm font-bold ${!isAnnual ? 'text-white' : 'text-neutral-500'}`}>Monthly</span>
          <button 
            className="w-16 h-8 rounded-full bg-white/10 relative flex items-center px-1"
            onClick={() => setIsAnnual(!isAnnual)}
          >
            <div className={`w-6 h-6 rounded-full bg-brand-lime transition-transform ${isAnnual ? 'translate-x-8' : 'translate-x-0'}`} />
          </button>
          <div className="flex items-center gap-2">
            <span className={`text-sm font-bold ${isAnnual ? 'text-white' : 'text-neutral-500'}`}>Annually</span>
            <span className="bg-brand-lime text-brand-dark text-[10px] font-bold px-2 py-0.5 rounded-full">Save 20%</span>
          </div>
        </div>
      </div>

      {/* Cards */}
      <div className="max-w-6xl mx-auto px-6 -mt-20">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {plans.map((p) => {
            const price = isAnnual ? p.annualPrice : p.monthlyPrice;
            const isPopular = p.id === "Professional";

            return (
              <Card key={p.id} className={`p-8 rounded-[32px] flex flex-col relative ${isPopular ? 'border-2 border-brand-lime shadow-xl transform md:-translate-y-4' : 'border-neutral-100 shadow-md'}`}>
                {isPopular && (
                  <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-brand-lime text-brand-dark text-xs font-bold px-4 py-1 rounded-full shadow-sm">
                    Most Popular
                  </div>
                )}
                <h3 className="text-2xl font-bold mb-2">{p.name}</h3>
                <p className="text-sm text-neutral-500 mb-6 min-h-[40px]">{p.description}</p>
                
                <div className="mb-6">
                  <span className="text-5xl font-display font-bold">${price}</span>
                  <span className="text-neutral-500 font-medium">/mo</span>
                </div>
                
                <Button 
                  variant={isPopular ? "lime" : "outline"} 
                  className="w-full rounded-full mb-8 font-bold text-md h-12"
                  onClick={() => handleSubscribeClick(p.id)}
                >
                  {p.id === "Enterprise" ? "Contact Sales" : "Subscribe"}
                </Button>

                <div className="space-y-4 flex-1">
                  <div className="text-sm font-bold mb-4">What's included:</div>
                  {p.features.map((feat, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <div className="w-5 h-5 rounded-full bg-brand-lime/20 text-brand-dark flex flex-shrink-0 items-center justify-center mt-0.5">
                        <Check className="w-3 h-3" />
                      </div>
                      <span className="text-sm font-medium text-neutral-700">{feat}</span>
                    </div>
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Comparison Table */}
      <div id="compare" className="max-w-5xl mx-auto px-6 mt-32">
        <h2 className="text-3xl font-display font-bold tracking-tight text-center mb-10">Compare Features</h2>
        <Card className="rounded-3xl overflow-hidden shadow-sm">
          <Table>
            <TableHeader className="bg-neutral-50">
              <TableRow>
                <TableHead className="font-bold w-1/3">Feature</TableHead>
                <TableHead className="font-bold text-center">Starter</TableHead>
                <TableHead className="font-bold text-center">Professional</TableHead>
                <TableHead className="font-bold text-center">Enterprise</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium">Certificates</TableCell>
                <TableCell className="text-center text-neutral-500">Up to 250</TableCell>
                <TableCell className="text-center text-neutral-500">Unlimited</TableCell>
                <TableCell className="text-center text-neutral-500">Unlimited</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Connectors</TableCell>
                <TableCell className="text-center text-neutral-500">Basic (AWS, Let's Encrypt)</TableCell>
                <TableCell className="text-center text-neutral-500">All</TableCell>
                <TableCell className="text-center text-neutral-500">All + Custom</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Notifications</TableCell>
                <TableCell className="text-center text-neutral-500">Email</TableCell>
                <TableCell className="text-center text-neutral-500">Slack, PagerDuty</TableCell>
                <TableCell className="text-center text-neutral-500">Custom Webhooks</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Enterprise Dashboard</TableCell>
                <TableCell className="text-center"><X className="w-4 h-4 text-neutral-300 mx-auto" /></TableCell>
                <TableCell className="text-center"><X className="w-4 h-4 text-neutral-300 mx-auto" /></TableCell>
                <TableCell className="text-center"><Check className="w-4 h-4 text-brand-lime mx-auto" /></TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">Support</TableCell>
                <TableCell className="text-center text-neutral-500">Community</TableCell>
                <TableCell className="text-center text-neutral-500">Priority</TableCell>
                <TableCell className="text-center text-neutral-500">24/7 Phone</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </div>

      {/* FAQ */}
      <div className="max-w-3xl mx-auto px-6 mt-32">
        <h2 className="text-3xl font-display font-bold tracking-tight text-center mb-10">Frequently Asked Questions</h2>
        <div className="space-y-4">
          <Card className="p-6 rounded-2xl shadow-sm">
            <h4 className="font-bold text-lg mb-2">Can I upgrade or downgrade anytime?</h4>
            <p className="text-neutral-500">Yes, your billing will be prorated automatically based on your usage in the current billing cycle.</p>
          </Card>
          <Card className="p-6 rounded-2xl shadow-sm">
            <h4 className="font-bold text-lg mb-2">What happens if I exceed my certificate limit on the Starter plan?</h4>
            <p className="text-neutral-500">We will notify you and give you a 7-day grace period to upgrade to Professional before pausing renewals.</p>
          </Card>
          <Card className="p-6 rounded-2xl shadow-sm">
            <h4 className="font-bold text-lg mb-2">Is there a free trial?</h4>
            <p className="text-neutral-500">No, but we offer a 30-day money-back guarantee for all new subscriptions.</p>
          </Card>
        </div>
      </div>

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-brand-dark/40 backdrop-blur-sm" onClick={() => !isSubmitting && setModalOpen(false)} />
          <Card className="relative w-full max-w-md p-8 rounded-3xl shadow-2xl animate-in zoom-in-95 duration-200">
            <h2 className="text-2xl font-bold font-display mb-2">Checkout</h2>
            <p className="text-sm text-neutral-500 mb-6">You are subscribing to the {selectedPlanId} plan. This is a mock payment interface.</p>
            
            <div className="space-y-4 mb-8">
               <div className="bg-neutral-50 p-4 rounded-xl border border-neutral-100 flex items-center gap-3">
                 <div className="w-10 h-10 rounded-full bg-brand-lime flex flex-shrink-0 items-center justify-center font-bold text-brand-dark">C</div>
                 <div>
                   <div className="font-bold text-sm">Credit Card</div>
                   <div className="text-xs text-neutral-500">**** **** **** 4242</div>
                 </div>
               </div>
            </div>

            <div className="flex gap-3">
              <Button variant="outline" className="flex-1 rounded-full h-12" onClick={() => setModalOpen(false)} disabled={isSubmitting}>Cancel</Button>
              <Button variant="lime" className="flex-1 rounded-full h-12 font-bold" onClick={handleConfirmSubscription} disabled={isSubmitting}>
                {isSubmitting ? <Loader2 className="w-5 h-5 animate-spin" /> : "Subscribe"}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
