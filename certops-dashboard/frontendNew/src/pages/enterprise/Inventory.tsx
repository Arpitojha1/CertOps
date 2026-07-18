import { useState } from "react"
import { Search, Download, CheckCircle2, X, AlertTriangle, Clock, MoreHorizontal, ArrowRight, ChevronDown } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { SelectPill } from "@/components/ui/select-pill"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { PromptModal } from "@/components/ui/prompt-modal"
import { MOCK_ENT_CERTIFICATES } from "@/mock-data-enterprise"
import { EnterpriseTabs } from "@/components/ui/enterprise-tabs"
import { EntCertificate, CertStatus } from "@/types"

export default function Inventory() {
  const [search, setSearch] = useState("")
  const [certs, setCerts] = useState<EntCertificate[]>(MOCK_ENT_CERTIFICATES)
  const [selectedCert, setSelectedCert] = useState<EntCertificate | null>(null)
  const [caFilter, setCaFilter] = useState("All")
  const [statusFilter, setStatusFilter] = useState("All")
  const [pipelineStep, setPipelineStep] = useState(1)
  const [prompt, setPrompt] = useState<{isOpen: boolean, title?: string, desc?: string, status?: "info" | "warning" | "success"}>({isOpen: false})

  const StatusBadge = ({ status }: { status: CertStatus }) => {
    switch (status) {
      case "Active": return <Badge variant="success" className="rounded-full"><CheckCircle2 className="w-3 h-3 mr-1" /> Active</Badge>
      case "Expiring Soon": return <Badge variant="warning" className="rounded-full"><Clock className="w-3 h-3 mr-1" /> Expiring Soon</Badge>
      case "Revoked": return <Badge variant="destructive" className="rounded-full"><AlertTriangle className="w-3 h-3 mr-1" /> Revoked</Badge>
      case "Expired": return <Badge variant="secondary" className="rounded-full">Expired</Badge>
      case "Pending": return <Badge variant="outline" className="rounded-full">Pending</Badge>
      default: return null
    }
  }

  const filteredCerts = certs.filter(c => {
    if (search && !c.domain.toLowerCase().includes(search.toLowerCase())) return false
    if (statusFilter !== "All" && c.status !== statusFilter) return false
    if (caFilter !== "All" && c.ca !== caFilter) return false
    return true
  })

  const uniqueCAs = ["All", ...Array.from(new Set(certs.map(c => c.ca)))]
  const uniqueStatuses = ["All", "Active", "Expiring Soon", "Revoked", "Expired", "Pending"]

  return (
    <div className="space-y-6 relative h-full flex flex-col">
      <PromptModal
        isOpen={prompt.isOpen}
        onClose={() => setPrompt({ isOpen: false })}
        title={prompt.title}
        description={prompt.desc}
        status={prompt.status}
      />

      <div className="flex items-center justify-between mb-8 shrink-0">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Certificate Inventory</h1>
          <p className="text-neutral-500 font-medium">Enterprise-wide catalog of all discovered and managed certificates</p>
        </div>
        <Button 
          variant="lime" 
          className="rounded-full font-bold shadow-sm" 
          onClick={() => setPrompt({
            isOpen: true,
            title: "Enroll Certificate",
            desc: "The automated enrollment wizard and CSR generation flow is not implemented yet."
          })}
        >
          Enroll Certificate
        </Button>
      </div>

      <EnterpriseTabs />

      <Card className="flex-1 flex flex-col min-h-0 rounded-3xl">
        <div className="p-4 flex flex-col sm:flex-row gap-4 justify-between border-b border-neutral-100">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
              <Input 
                 placeholder="Search domains or IDs..." 
                 className="pl-9 bg-neutral-50 border-none rounded-full"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            
            <div className="relative inline-block">
              <select 
                className="appearance-none h-10 rounded-full border border-neutral-200 bg-white px-4 py-2 pr-10 text-sm font-bold text-neutral-700 shadow-sm focus:ring-2 focus:ring-brand-lime focus:outline-none cursor-pointer"
                value={caFilter}
                onChange={(e) => setCaFilter(e.target.value)}
              >
                {uniqueCAs.map(ca => <option key={ca} value={ca}>CA: {ca}</option>)}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
            </div>
            
            <div className="relative inline-block">
              <select 
                className="appearance-none h-10 rounded-full border border-neutral-200 bg-white px-4 py-2 pr-10 text-sm font-bold text-neutral-700 shadow-sm focus:ring-2 focus:ring-brand-lime focus:outline-none cursor-pointer"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                {uniqueStatuses.map(s => <option key={s} value={s}>Status: {s}</option>)}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
            </div>
            
          </div>
          <Button 
            variant="outline" 
            size="sm" 
            className="h-10 text-neutral-600 bg-white border-neutral-200 shadow-sm rounded-full shrink-0 font-bold" 
            onClick={() => setPrompt({
              isOpen: true,
              title: "Exporting CSV",
              desc: `Generating CSV export for ${filteredCerts.length} certificates. Your download will begin shortly in full production.`,
              status: "success"
            })}
          >
            <Download className="w-4 h-4 mr-2" />
            Export CSV
          </Button>
        </div>
        
        <div className="flex-1 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-none">
                <TableHead>Domain</TableHead>
                <TableHead>CA</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Expiry</TableHead>
                <TableHead>Days</TableHead>
                <TableHead className="text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredCerts.map((cert) => (
                <TableRow 
                  key={cert.id} 
                  className="cursor-pointer hover:bg-neutral-50/50"
                  onClick={() => {
                    setSelectedCert(cert)
                    setPipelineStep(1)
                  }}
                >
                  <TableCell className="font-bold">{cert.domain}</TableCell>
                  <TableCell className="text-neutral-500">{cert.ca}</TableCell>
                  <TableCell className="text-neutral-500">{cert.type}</TableCell>
                  <TableCell className="text-neutral-500">{cert.owner}</TableCell>
                  <TableCell>
                    <span className="font-medium">{cert.expiryDate}</span>
                  </TableCell>
                  <TableCell>
                    <span className={`text-[10px] font-bold tracking-wide uppercase ${cert.daysRemaining < 30 ? "text-red-500" : "text-neutral-400"}`}>
                      {cert.daysRemaining}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <StatusBadge status={cert.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Detail Drawer Overlay */}
      {selectedCert && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-brand-dark/20 backdrop-blur-sm" onClick={() => setSelectedCert(null)} />
          <div className="relative w-full max-w-lg bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-300 overflow-hidden">
            <div className="p-8 border-b border-neutral-100 bg-neutral-50/50 flex items-start justify-between">
              <div>
                <h2 className="text-2xl font-bold font-display mb-2">{selectedCert.domain}</h2>
                <div className="flex items-center gap-3">
                  <StatusBadge status={selectedCert.status} />
                  <span className="text-sm font-medium text-neutral-500">ID: {selectedCert.id}</span>
                </div>
              </div>
              <button onClick={() => setSelectedCert(null)} className="w-10 h-10 rounded-full bg-white border border-neutral-200 flex items-center justify-center text-neutral-500 hover:text-brand-dark hover:bg-neutral-50 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-8 space-y-10">
              <section>
                <h3 className="font-bold text-lg mb-4">Metadata</h3>
                <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Type</div>
                    <div className="font-semibold text-sm">{selectedCert.type}</div>
                  </div>
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Certificate Authority</div>
                    <div className="font-semibold text-sm">{selectedCert.ca}</div>
                  </div>
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Owner</div>
                    <div className="font-semibold text-sm">{selectedCert.owner}</div>
                  </div>
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Target Group</div>
                    <div className="font-semibold text-sm">{selectedCert.group}</div>
                  </div>
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Key Type</div>
                    <div className="font-semibold text-sm">RSA 2048</div>
                  </div>
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Expiry Date</div>
                    <div className="font-semibold text-sm">{selectedCert.expiryDate}</div>
                  </div>
                </div>
              </section>

              <section>
                <h3 className="font-bold text-lg mb-4">Pipeline Status (Click to advance)</h3>
                <div className="flex items-center justify-between p-6 bg-brand-dark text-white rounded-full cursor-pointer select-none" onClick={() => setPipelineStep(p => p < 3 ? p + 1 : 1)}>
                  <div className={`flex flex-col items-center ${pipelineStep >= 1 ? '' : 'opacity-50'}`}>
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${pipelineStep >= 1 ? 'bg-brand-lime text-brand-dark' : 'border-2 border-white/20'}`}>
                      {pipelineStep >= 1 ? <CheckCircle2 className="w-6 h-6" /> : <div className="w-2 h-2 rounded-full bg-white"></div>}
                    </div>
                    <span className="text-xs font-bold uppercase tracking-widest text-neutral-400">Renewed</span>
                  </div>
                  <div className="flex-1 h-px bg-white/20 mx-4"></div>
                  <div className={`flex flex-col items-center ${pipelineStep >= 2 ? '' : 'opacity-50'}`}>
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${pipelineStep >= 2 ? 'bg-brand-lime text-brand-dark' : 'border-2 border-white/20'}`}>
                      {pipelineStep >= 2 ? <CheckCircle2 className="w-6 h-6" /> : <div className="w-2 h-2 rounded-full bg-white"></div>}
                    </div>
                    <span className="text-xs font-bold uppercase tracking-widest text-neutral-400">Deployed</span>
                  </div>
                  <div className="flex-1 h-px bg-white/20 mx-4"></div>
                  <div className={`flex flex-col items-center ${pipelineStep >= 3 ? '' : 'opacity-50'}`}>
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${pipelineStep >= 3 ? 'bg-brand-lime text-brand-dark' : 'border-2 border-white/20'}`}>
                      {pipelineStep >= 3 ? <CheckCircle2 className="w-6 h-6" /> : <div className="w-2 h-2 rounded-full bg-white"></div>}
                    </div>
                    <span className="text-xs font-bold uppercase tracking-widest text-neutral-400">Reload</span>
                  </div>
                </div>
              </section>
            </div>
            
            <div className="p-8 border-t border-neutral-100 bg-white">
              <Button 
                variant="lime" 
                className="w-full rounded-full font-bold shadow-sm" 
                onClick={() => setPrompt({
                  isOpen: true,
                  title: `Action Details (${selectedCert.domain})`,
                  desc: `Detailed execution history and pipeline logs for ${selectedCert.domain} are not implemented yet.`
                })}
              >
                Action Details <ArrowRight className="w-4 h-4 ml-2"/>
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
