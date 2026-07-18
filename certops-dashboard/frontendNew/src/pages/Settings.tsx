import { Save, Building2, ExternalLink, ChevronDown } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PromptModal } from "@/components/ui/prompt-modal"
import { useAppStore } from "@/lib/store"
import { useState, useEffect } from "react"
import { Link } from "react-router-dom"
import { apiGet, apiPut } from "@/lib/api"

export default function Settings() {
  const { plan } = useAppStore()
  const [activeTab, setActiveTab] = useState("General")
  const [renewalThreshold, setRenewalThreshold] = useState(30)
  const [keySize, setKeySize] = useState("RSA 2048")
  const [acmeEmail, setAcmeEmail] = useState("admin@certops.io")
  const [isSaving, setIsSaving] = useState(false)
  const [prompt, setPrompt] = useState<{isOpen: boolean, title?: string, desc?: string, status?: "info" | "warning" | "success"}>({isOpen: false})

  useEffect(() => {
    apiGet<{ defaultRenewalThreshold?: number; defaultKeySize?: string; acmeContactEmail?: string }>("/api/settings")
      .then((s) => {
        if (s.defaultRenewalThreshold != null) setRenewalThreshold(s.defaultRenewalThreshold)
        if (s.defaultKeySize) setKeySize(s.defaultKeySize)
        if (s.acmeContactEmail) setAcmeEmail(s.acmeContactEmail)
      })
      .catch(() => {/* use defaults */})
  }, [])

  const handleSave = () => {
    setIsSaving(true)
    apiPut("/api/settings", { defaultRenewalThreshold: renewalThreshold, defaultKeySize: keySize, acmeContactEmail: acmeEmail })
      .then(() => setPrompt({ isOpen: true, title: "Settings Saved", desc: "Global renewal defaults have been saved successfully to the server.", status: "success" }))
      .catch(() => setPrompt({ isOpen: true, title: "Saved Locally", desc: "Global renewal defaults were saved in local state (backend configuration persistence is pending).", status: "info" }))
      .finally(() => setIsSaving(false))
  }

  return (
    <div className="max-w-4xl space-y-6 relative">
      <PromptModal
        isOpen={prompt.isOpen}
        onClose={() => setPrompt({ isOpen: false })}
        title={prompt.title}
        description={prompt.desc}
        status={prompt.status}
      />

      <div className="mb-8">
        <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Settings</h1>
        <p className="text-neutral-500 font-medium">Global platform configuration</p>
      </div>

      <div className="flex border-b border-neutral-200 mb-6">
        <button onClick={() => setActiveTab("General")} className={`px-4 py-2 border-b-2 font-medium ${activeTab === "General" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-500 hover:text-neutral-700"}`}>General</button>
        <button onClick={() => setActiveTab("Security")} className={`px-4 py-2 border-b-2 font-medium ${activeTab === "Security" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-500 hover:text-neutral-700"}`}>Security</button>
        <button onClick={() => setActiveTab("API Keys")} className={`px-4 py-2 border-b-2 font-medium ${activeTab === "API Keys" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-500 hover:text-neutral-700"}`}>API Keys</button>
      </div>

      {activeTab === "General" && (
        <>
          <Card className="p-6 rounded-3xl">
            <div className="flex justify-between items-start mb-6">
              <div>
                <h3 className="text-lg font-bold mb-1">Subscription Plan</h3>
                <p className="text-sm text-neutral-500">Manage your billing and plan level.</p>
              </div>
              <Link to="/pricing">
                <Button variant="outline" size="sm" className="rounded-full font-bold">
                  Change Plan <ExternalLink className="w-3 h-3 ml-2" />
                </Button>
              </Link>
            </div>
            
            <div className="flex items-center gap-4 p-4 border border-brand-lime bg-[#F4F9E0]/50 rounded-2xl">
              <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center border border-brand-lime shadow-sm">
                <Building2 className="w-6 h-6 text-brand-dark" />
              </div>
              <div>
                <div className="font-bold text-lg leading-tight">{plan} Plan</div>
                <div className="text-sm text-neutral-600">Active and billed monthly.</div>
              </div>
            </div>
          </Card>

          <Card className="p-6 rounded-3xl">
            <h3 className="text-lg font-bold mb-1">Global Renewal Defaults</h3>
            <p className="text-sm text-neutral-500 mb-6">These settings apply when groups don't specify their own policies.</p>
            
            <div className="space-y-6 max-w-lg">
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Default Renewal Threshold (Days)</label>
                <Input type="number" value={renewalThreshold} onChange={e => setRenewalThreshold(Number(e.target.value))} />
                <p className="text-xs text-neutral-500 mt-1">Number of days before expiry to attempt renewal.</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Key Size</label>
                <div className="relative inline-block w-full">
                  <select
                    className="appearance-none w-full h-10 rounded-full border border-neutral-200 bg-white px-4 pr-10 text-sm font-bold text-neutral-700 shadow-sm focus:ring-2 focus:ring-brand-lime focus:outline-none cursor-pointer"
                    value={keySize}
                    onChange={e => setKeySize(e.target.value)}
                  >
                    <option>RSA 2048</option>
                    <option>RSA 4096</option>
                    <option>ECDSA P-256</option>
                    <option>ECDSA P-384</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Contact Email for ACME Accounts</label>
                <Input type="email" value={acmeEmail} onChange={e => setAcmeEmail(e.target.value)} />
              </div>
              <div className="pt-4 border-t border-neutral-100 flex justify-end">
                <Button variant="lime" className="rounded-full font-bold shadow-sm" onClick={handleSave} disabled={isSaving}>
                  <Save className="w-4 h-4 mr-2" />
                  {isSaving ? "Saving…" : "Save Defaults"}
                </Button>
              </div>
            </div>
          </Card>
        </>
      )}
      
      {activeTab !== "General" && (
        <Card className="p-12 flex flex-col items-center justify-center text-center rounded-3xl">
          <h3 className="text-xl font-bold mb-2">Configuration Available</h3>
          <p className="text-neutral-500 mb-6 max-w-md">
            The {activeTab} settings are managed through your enterprise security policy or SSO provider configuration.
          </p>
          <Button 
            variant="outline" 
            className="rounded-full font-bold"
            onClick={() => setPrompt({
              isOpen: true,
              title: `${activeTab} Management`,
              desc: `${activeTab} configuration options (SSO tokens, audit keys, and IP whitelisting) are not implemented yet in the web console.`
            })}
          >
            Configure {activeTab}
          </Button>
        </Card>
      )}
    </div>
  )
}
