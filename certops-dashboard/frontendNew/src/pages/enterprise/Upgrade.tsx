import { Building2, ShieldCheck, Search, ActivitySquare } from "lucide-react"
import { useAppStore } from "@/lib/store"
import { useNavigate } from "react-router-dom"

export default function Upgrade() {
  const { setPlan } = useAppStore()
  const navigate = useNavigate()

  return (
    <div className="h-full flex items-center justify-center">
      <div className="max-w-2xl w-full bg-brand-dark text-white rounded-full p-12 text-center shadow-xl relative overflow-hidden">
        <div className="absolute -right-20 -top-20 w-64 h-64 bg-brand-lime/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -left-20 -bottom-20 w-64 h-64 bg-brand-purple/20 rounded-full blur-3xl pointer-events-none" />
        
        <Building2 className="w-16 h-16 text-brand-lime mx-auto mb-6 relative z-10" />
        <h2 className="text-3xl font-bold mb-4 relative z-10 tracking-tight">Enterprise Dashboard is available on the Enterprise plan</h2>
        <p className="text-neutral-400 mb-10 max-w-lg mx-auto relative z-10">
          Unlock advanced features designed for large-scale certificate management, policy enforcement, and fleet-wide visibility.
        </p>

        <div className="grid grid-cols-2 gap-6 text-left mb-10 relative z-10">
          <div className="bg-white/5 p-4 rounded-full border border-white/10 flex gap-3">
            <Search className="w-5 h-5 text-brand-lime shrink-0" />
            <div>
              <div className="font-bold text-sm">Bulk Discovery</div>
              <div className="text-xs text-neutral-400 mt-1">Scan entire networks for rogue certificates.</div>
            </div>
          </div>
          <div className="bg-white/5 p-4 rounded-full border border-white/10 flex gap-3">
            <ActivitySquare className="w-5 h-5 text-brand-lime shrink-0" />
            <div>
              <div className="font-bold text-sm">Health & Analytics</div>
              <div className="text-xs text-neutral-400 mt-1">Monitor CA uptime and issuance error rates.</div>
            </div>
          </div>
          <div className="bg-white/5 p-4 rounded-full border border-white/10 flex gap-3">
            <ShieldCheck className="w-5 h-5 text-brand-lime shrink-0" />
            <div>
              <div className="font-bold text-sm">CA Policies</div>
              <div className="text-xs text-neutral-400 mt-1">Enforce allowed Certificate Authorities by group.</div>
            </div>
          </div>
          <div className="bg-white/5 p-4 rounded-full border border-white/10 flex gap-3">
            <Building2 className="w-5 h-5 text-brand-lime shrink-0" />
            <div>
              <div className="font-bold text-sm">Global Actions</div>
              <div className="text-xs text-neutral-400 mt-1">Mass renew, revoke, or reissue certificates.</div>
            </div>
          </div>
        </div>

        <button 
          onClick={() => {
            navigate("/pricing")
          }}
          className="bg-brand-lime text-brand-dark px-8 py-3 rounded-full font-bold text-sm hover:bg-[#c4df42] transition-colors relative z-10"
        >
          View Enterprise Pricing
        </button>
      </div>
    </div>
  )
}
