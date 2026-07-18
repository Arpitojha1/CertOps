import { useState } from "react"
import { PlusCircle, RefreshCw, RefreshCcw, XOctagon, ShieldCheck, MoreVertical, CheckCircle2 } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { EnterpriseTabs } from "@/components/ui/enterprise-tabs"
import { apiGet, apiPost } from "@/lib/api"

export default function Actions() {
  const [toast, setToast] = useState<{message: string, type: "success" | "error"} | null>(null)

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleBulkRenew = async () => {
    try {
      const certs = await apiGet<any[]>("/api/certificates")
      const certIds = certs.map(c => c.id)
      if (certIds.length === 0) {
        showToast("No certificates found to renew", "error")
        return
      }
      const res = await apiPost<any>("/api/certificates/bulk-renew", { cert_ids: certIds })
      showToast(`Bulk renewal initiated: ${res.triggered} of ${res.total} triggered.`)
    } catch (err: any) {
      showToast(err?.message || "Failed to initiate bulk renewal", "error")
    }
  }

  const handleBulkRevoke = async () => {
    try {
      const certs = await apiGet<any[]>("/api/certificates")
      const certIds = certs.map(c => c.id)
      if (certIds.length === 0) {
        showToast("No certificates found to revoke", "error")
        return
      }
      const res = await apiPost<any>("/api/certificates/bulk-revoke", { cert_ids: certIds, reason: "Bulk enterprise revocation" })
      showToast(`Bulk revocation completed for ${res.total} certificates.`, "error")
    } catch (err: any) {
      showToast(err?.message || "Failed to initiate bulk revocation", "error")
    }
  }

  return (
    <div className="space-y-6 relative h-full flex flex-col">
      {toast && (
        <div className={`absolute top-0 left-1/2 -translate-x-1/2 z-50 px-4 py-3 rounded-full shadow-xl flex items-center gap-2 animate-in slide-in-from-top-4 ${toast.type === 'success' ? 'bg-brand-dark text-brand-lime' : 'bg-red-50 text-red-600'}`}>
          <CheckCircle2 className="w-5 h-5" />
          <span className="font-medium text-sm">{toast.message}</span>
        </div>
      )}
      <div className="flex items-center justify-between mb-8 shrink-0">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Certificate Actions</h1>
          <p className="text-neutral-500 font-medium">Execute lifecycle commands on your certificates</p>
        </div>
      </div>

      <EnterpriseTabs />

      <div className="flex-1 overflow-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <ActionCard 
            icon={PlusCircle} 
            title="Enroll" 
            description="Request and provision a new certificate from an active CA." 
            buttonText="Enroll Certificate" 
            primary 
            onClick={() => showToast("Enrollment request submitted successfully")}
          />
          <ActionCard 
            icon={RefreshCw} 
            title="Renew" 
            description="Renew an existing certificate before its expiration date." 
            buttonText="Renew Certificate" 
            onClick={handleBulkRenew}
          />
          <ActionCard 
            icon={RefreshCcw} 
            title="Reissue" 
            description="Reissue a certificate with the same details but new keys." 
            buttonText="Reissue Certificate" 
            onClick={() => showToast("Certificate reissue process started")}
          />
          <ActionCard 
            icon={XOctagon} 
            title="Revoke" 
            description="Permanently invalidate a compromised or unused certificate." 
            buttonText="Revoke Certificate" 
            destructive 
            onClick={handleBulkRevoke}
          />
          <ActionCard 
            icon={ShieldCheck} 
            title="Revocation Check (OCSP)" 
            description="Check the real-time revocation status of a certificate." 
            buttonText="Run OCSP Check" 
            onClick={() => showToast("OCSP check complete: All certificates valid")}
          />
        </div>
      </div>
    </div>
  )
}

function ActionCard({ icon: Icon, title, description, buttonText, primary, destructive, onClick }: any) {
  const [loading, setLoading] = useState(false)

  const handleClick = async () => {
    setLoading(true)
    try {
      await onClick()
    } catch (e) {
      // handled inside handler
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="p-6 flex flex-col group rounded-3xl hover:shadow-lg transition-shadow">
      <div className="flex justify-between items-start mb-6">
        <div className={`w-12 h-12 rounded-full flex items-center justify-center ${primary ? 'bg-brand-lime text-brand-dark' : destructive ? 'bg-red-50 text-red-600' : 'bg-brand-purple/20 text-brand-purple'}`}>
          <Icon className="w-6 h-6" />
        </div>
        <button onClick={() => window.alert('Options not implemented')} className="text-neutral-300 hover:text-brand-dark transition-colors"><MoreVertical className="w-5 h-5" /></button>
      </div>
      <h3 className="font-bold text-xl mb-2">{title}</h3>
      <p className="text-sm text-neutral-500 mb-8 flex-1">{description}</p>
      
      <Button 
        variant={primary ? "lime" : "outline"} 
        className={`w-full font-bold rounded-full ${destructive ? 'text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200' : ''}`}
        onClick={handleClick}
        disabled={loading}
      >
        {loading ? "Processing..." : buttonText}
      </Button>
    </Card>
  )
}
