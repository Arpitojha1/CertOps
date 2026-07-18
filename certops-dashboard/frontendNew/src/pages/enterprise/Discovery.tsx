import { useState } from "react"
import { Search, Play, Plus, Server, Network, CheckCircle2 } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { PromptModal } from "@/components/ui/prompt-modal"
import { EnterpriseTabs } from "@/components/ui/enterprise-tabs"
import { MOCK_DISCOVERY_JOBS, MOCK_DISCOVERY_RULES, MOCK_NETWORK_INVENTORY, MOCK_EXCLUDED_CERTS } from "@/mock-data-enterprise"
import { apiPost } from "@/lib/api"

export default function Discovery() {
  const [tab, setTab] = useState("Status")
  const [isScanning, setIsScanning] = useState(false)
  const [toast, setToast] = useState<{message: string, type: "success" | "error"} | null>(null)
  const [prompt, setPrompt] = useState<{isOpen: boolean, title?: string, desc?: string}>({isOpen: false})

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleRunScan = async () => {
    setIsScanning(true)
    try {
      const res = await apiPost<{ message: string }>("/api/enterprise/discovery/scan", {})
      showToast(res.message || "Discovery scan triggered successfully.")
    } catch (err: any) {
      showToast("Failed to trigger scan: " + (err?.message || err), "error")
    } finally {
      setIsScanning(false)
    }
  }

  return (
    <div className="space-y-6 relative">
      <PromptModal
        isOpen={prompt.isOpen}
        onClose={() => setPrompt({ isOpen: false })}
        title={prompt.title}
        description={prompt.desc}
      />

      {toast && (
        <div className={`absolute top-0 left-1/2 -translate-x-1/2 z-50 px-4 py-3 rounded-full shadow-xl flex items-center gap-2 animate-in slide-in-from-top-4 ${toast.type === 'success' ? 'bg-brand-dark text-brand-lime' : 'bg-red-50 text-red-600'}`}>
          <CheckCircle2 className="w-5 h-5" />
          <span className="font-medium text-sm">{toast.message}</span>
        </div>
      )}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Discovery</h1>
          <p className="text-neutral-500 font-medium">Scan networks and integrations to find unmanaged certificates</p>
        </div>
        <Button 
          variant="lime" 
          className="rounded-full font-bold shadow-sm"
          onClick={() => setPrompt({
            isOpen: true,
            title: "New Discovery Rule",
            desc: "The custom CIDR scanning and discovery rule configuration form is not implemented yet."
          })}
        >
          <Plus className="w-4 h-4 mr-2" />
          New Rule
        </Button>
      </div>

      <EnterpriseTabs />

      <div className="flex border-b border-neutral-200 mb-6 gap-6">
        <button 
          onClick={() => setTab("Status")}
          className={`pb-2 text-sm font-bold border-b-2 transition-colors ${tab === "Status" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-400 hover:text-neutral-700"}`}
        >
          Discovery Status
        </button>
        <button 
          onClick={() => setTab("Config")}
          className={`pb-2 text-sm font-bold border-b-2 transition-colors ${tab === "Config" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-400 hover:text-neutral-700"}`}
        >
          Configuration
        </button>
      </div>

      {tab === "Status" ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="p-6 rounded-3xl bg-brand-dark text-white relative overflow-hidden">
              <div className="absolute -right-4 -top-4 w-32 h-32 bg-white/5 rounded-full blur-2xl pointer-events-none" />
              <div className="flex items-center gap-3 mb-6 text-brand-lime">
                <Search className="w-5 h-5" />
                <h3 className="font-bold text-lg text-white">On Demand Scan</h3>
              </div>
              <p className="text-neutral-400 text-sm mb-8">Manually trigger a discovery scan across all configured network ranges and active integrations.</p>
              <Button variant="lime" className="w-full" onClick={handleRunScan} disabled={isScanning}>
                <Play className="w-4 h-4 mr-2" /> {isScanning ? "Scanning..." : "Run Discovery Now"}
              </Button>
            </Card>

            <Card className="p-0 overflow-hidden rounded-3xl">
              <div className="p-6 border-b border-neutral-50">
                <h3 className="font-bold text-sm">Scheduled Jobs</h3>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="border-none">
                    <TableHead>Job Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {MOCK_DISCOVERY_JOBS.map(job => (
                    <TableRow key={job.id}>
                      <TableCell className="font-bold">{job.name}</TableCell>
                      <TableCell className="text-neutral-500">{job.type}</TableCell>
                      <TableCell>
                        <Badge variant={job.status === "Running" ? "lime" : "secondary"}>
                          {job.status === "Running" && <Play className="w-3 h-3 mr-1 inline" />}
                          {job.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </div>

          <Card className="p-0 overflow-hidden rounded-3xl">
            <div className="p-6 border-b border-neutral-50 flex justify-between items-center">
              <h3 className="font-bold text-sm">Discovery Rules</h3>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="border-none">
                  <TableHead>Rule Name</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Schedule</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MOCK_DISCOVERY_RULES.map(rule => (
                  <TableRow key={rule.id}>
                    <TableCell className="font-bold">{rule.name}</TableCell>
                    <TableCell className="text-neutral-500">{rule.target}</TableCell>
                    <TableCell className="text-neutral-500">{rule.schedule}</TableCell>
                    <TableCell>
                      <Badge variant={rule.status === "Active" ? "lime" : "secondary"}>{rule.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </div>
      ) : (
        <div className="space-y-6">
          <Card className="p-0 overflow-hidden rounded-3xl">
            <div className="p-6 border-b border-neutral-50 flex items-center gap-2">
              <Network className="w-5 h-5 text-brand-purple" />
              <h3 className="font-bold text-sm">Network Inventory</h3>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="border-none">
                  <TableHead>CIDR Range</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Last Scan</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MOCK_NETWORK_INVENTORY.map(net => (
                  <TableRow key={net.id}>
                    <TableCell className="font-bold">{net.cidr}</TableCell>
                    <TableCell className="text-neutral-500">{net.description}</TableCell>
                    <TableCell className="text-neutral-500">{net.lastScan}</TableCell>
                    <TableCell>
                      <Badge variant={net.status === "Scanned" ? "lime" : net.status === "Error" ? "destructive" : "secondary"}>
                        {net.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>

          <Card className="p-0 overflow-hidden rounded-3xl">
            <div className="p-6 border-b border-neutral-50 flex items-center gap-2">
              <Server className="w-5 h-5 text-neutral-400" />
              <h3 className="font-bold text-sm">Excluded Certificates</h3>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="border-none">
                  <TableHead>Domain</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Date Excluded</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MOCK_EXCLUDED_CERTS.map(cert => (
                  <TableRow key={cert.id}>
                    <TableCell className="font-bold">{cert.domain}</TableCell>
                    <TableCell className="text-neutral-500">{cert.reason}</TableCell>
                    <TableCell className="text-neutral-500">{cert.dateExcluded}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}
    </div>
  )
}
