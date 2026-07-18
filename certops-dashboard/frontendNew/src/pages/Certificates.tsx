import React, { useState, useEffect } from "react"
import { Search, Filter, Download, MoreHorizontal, AlertTriangle, CheckCircle2, Clock, X, ArrowRight, ChevronDown } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { SelectPill } from "@/components/ui/select-pill"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiGet, apiPost, apiDelete } from "@/lib/api"
import { adaptCertificate, RawCertificate } from "@/lib/adapters"
import { Certificate, CertStatus } from "@/types"
import { PromptModal } from "@/components/ui/prompt-modal"

function StatusBadge({ status }: { status: CertStatus }) {
  switch (status) {
    case "Active": return <Badge variant="success" className="rounded-full"><CheckCircle2 className="w-3 h-3 mr-1" /> Active</Badge>
    case "Expiring Soon": return <Badge variant="warning" className="rounded-full"><Clock className="w-3 h-3 mr-1" /> Expiring Soon</Badge>
    case "Revoked": return <Badge variant="destructive" className="rounded-full"><AlertTriangle className="w-3 h-3 mr-1" /> Revoked</Badge>
    case "Expired": return <Badge variant="secondary" className="rounded-full">Expired</Badge>
    case "Pending": return <Badge variant="outline" className="rounded-full">Pending</Badge>
    default: return null
  }
}

export default function Certificates() {
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("All")
  const [caFilter, setCaFilter] = useState<string>("All")
  const [certs, setCerts] = useState<Certificate[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [selectedCert, setSelectedCert] = useState<Certificate | null>(null)
  const [pipelineStep, setPipelineStep] = useState(1) // 1: Renewed, 2: Deployed, 3: Reload
  const [promptState, setPromptState] = useState<{
    isOpen: boolean;
    title?: string;
    desc?: string;
    status?: "info" | "warning" | "success";
  }>({ isOpen: false })

  useEffect(() => {
    apiGet<RawCertificate[]>('/api/certificates')
      .then(raw => setCerts(raw.map(adaptCertificate)))
      .catch(() => {})
      .finally(() => setIsLoading(false))
  }, [])

  const filteredCerts = certs.filter(c => {
    if (search && !c.domain.toLowerCase().includes(search.toLowerCase())) return false
    if (statusFilter !== "All" && c.status !== statusFilter) return false
    if (caFilter !== "All" && c.ca !== caFilter) return false
    return true
  })

  const uniqueCAs = ["All", ...Array.from(new Set(certs.map(c => c.ca)))]
  const uniqueStatuses = ["All", "Active", "Expiring Soon", "Revoked", "Expired", "Pending"]

  const forceRenewal = () => {
    if (!selectedCert) return
    // Optimistic update
    setCerts(certs.map(c => c.id === selectedCert.id ? { ...c, status: "Active", daysRemaining: 90 } : c))
    setSelectedCert({ ...selectedCert, status: "Active", daysRemaining: 90 })
    setPipelineStep(1)
    const [vault, ...rest] = selectedCert.id.split(':')
    apiPost('/api/trigger_renewal', { vault_source: vault, cert_name: rest.join(':') })
      .catch(() => {})
    setPromptState({
      isOpen: true,
      title: "Force Renewal Initiated",
      desc: `Force renewal has been triggered for ${selectedCert.domain}. The automated renewal pipeline is running.`,
      status: "success"
    })
  }

  const deleteCert = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setCerts(certs.filter(c => c.id !== id))
    apiDelete('/api/certificates/' + id).catch(() => {})
  }

  return (
    <div className="max-w-[1400px] h-full flex flex-col relative">
      <PromptModal
        isOpen={promptState.isOpen}
        onClose={() => setPromptState({ isOpen: false })}
        title={promptState.title}
        description={promptState.desc}
        status={promptState.status}
      />

      <div className="flex items-center justify-between mb-8 shrink-0">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Certificates</h1>
          <p className="text-neutral-500 font-medium">Manage and monitor your certificate fleet</p>
        </div>
        <Button variant="lime" className="rounded-full" onClick={() => setPromptState({
            isOpen: true,
            title: "Request Certificate",
            desc: "The Request Certificate enrollment form is not implemented yet.",
            status: "info"
          })}>Request Certificate</Button>
      </div>

      <Card className="flex-1 flex flex-col min-h-0 rounded-3xl">
        <div className="p-4 flex flex-col sm:flex-row gap-4 justify-between border-b border-neutral-100">
          <div className="flex items-center gap-3">
            <div className="relative w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
              <Input 
                 placeholder="Search domains..." 
                 className="pl-9 bg-neutral-50 border-none rounded-full"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
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
          </div>
          <Button onClick={() => setPromptState({
              isOpen: true,
              title: "Export Certificates",
              desc: "Exporting certificate inventory data is not implemented yet.",
              status: "info"
            })} variant="outline" size="sm" className="h-10 text-neutral-600 bg-white border-neutral-200 shadow-sm rounded-full">
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
        </div>
        
        <div className="flex-1 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-neutral-100">
                <TableHead>Domain</TableHead>
                <TableHead>Source / Connector</TableHead>
                <TableHead>CA</TableHead>
                <TableHead>Group</TableHead>
                <TableHead>Expiry</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12"></TableHead>
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
                  <TableCell className="text-neutral-500">{cert.connector}</TableCell>
                  <TableCell className="text-neutral-500">{cert.ca}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="font-medium bg-neutral-50 text-neutral-600 border-neutral-200 rounded-full">{cert.group}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="font-medium">{cert.expiryDate}</span>
                      <span className={`text-[10px] font-bold tracking-wide uppercase ${cert.daysRemaining < 30 ? "text-red-500" : "text-neutral-400"}`}>
                        {cert.daysRemaining} days left
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={cert.status} />
                  </TableCell>
                  <TableCell>
                    <div className="relative group">
                      <button className="p-2 text-neutral-400 hover:text-brand-dark rounded-full hover:bg-neutral-200 transition-colors">
                        <MoreHorizontal className="w-5 h-5" />
                      </button>
                      <div className="absolute right-0 top-full mt-1 bg-white border border-neutral-200 shadow-lg rounded-xl py-1 hidden group-hover:block z-10 w-32">
                        <button onClick={(e) => { e.stopPropagation(); setSelectedCert(cert); }} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50">View Details</button>
                        <button onClick={(e) => deleteCert(e, cert.id)} className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50">Delete</button>
                      </div>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {filteredCerts.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-neutral-500">No certificates found matching your criteria.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Detail Drawer Overlay */}
      {selectedCert && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-brand-dark/20 backdrop-blur-sm" onClick={() => setSelectedCert(null)} />
          <div className="relative w-full max-w-lg bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
            <div className="p-8 border-b border-neutral-100 bg-neutral-50/50 flex items-start justify-between">
              <div>
                <h2 className="text-2xl font-bold font-display mb-2">{selectedCert.domain}</h2>
                <div className="flex items-center gap-3">
                  <StatusBadge status={selectedCert.status} />
                  <span className="text-sm font-medium text-neutral-500">ID: {selectedCert.id}</span>
                </div>
              </div>
              <button onClick={() => setSelectedCert(null)} className="w-10 h-10 rounded-full bg-white border border-neutral-200 flex items-center justify-center text-neutral-500 hover:text-brand-dark hover:bg-neutral-100 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-8 space-y-10">
              {/* Metadata */}
              <section>
                <h3 className="font-bold text-lg mb-4">Metadata</h3>
                <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Source / Connector</div>
                    <div className="font-semibold text-sm">{selectedCert.connector}</div>
                  </div>
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Certificate Authority</div>
                    <div className="font-semibold text-sm">{selectedCert.ca}</div>
                  </div>
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Expiry Date</div>
                    <div className="font-semibold text-sm">{selectedCert.expiryDate}</div>
                  </div>
                  <div>
                    <div className="text-sm text-neutral-500 mb-1">Target Group</div>
                    <div className="font-semibold text-sm">{selectedCert.group}</div>
                  </div>
                </div>
              </section>

              {/* Pipeline */}
              <section>
                <h3 className="font-bold text-lg mb-4">Pipeline Status (Click to advance)</h3>
                <div className="flex items-center justify-between p-6 bg-brand-dark text-white rounded-2xl cursor-pointer select-none" onClick={() => setPipelineStep((p) => p < 3 ? p + 1 : 1)}>
                  <div className={`flex flex-col items-center ${pipelineStep >= 1 ? '' : 'opacity-50'}`}>
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${pipelineStep >= 1 ? 'bg-brand-lime text-brand-dark' : 'border-2 border-white/20'}`}>
                      {pipelineStep >= 1 ? <CheckCircle2 className="w-6 h-6" /> : <div className="w-2 h-2 rounded-full bg-white"></div>}
                    </div>
                    <span className="text-xs font-medium">Renewed</span>
                  </div>
                  <div className="flex-1 h-px bg-white/20 mx-4"></div>
                  
                  <div className={`flex flex-col items-center ${pipelineStep >= 2 ? '' : 'opacity-50'}`}>
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${pipelineStep >= 2 ? 'bg-brand-lime text-brand-dark' : 'border-2 border-white/20'}`}>
                      {pipelineStep >= 2 ? <CheckCircle2 className="w-6 h-6" /> : <div className="w-2 h-2 rounded-full bg-white"></div>}
                    </div>
                    <span className="text-xs font-medium">Deployed</span>
                  </div>
                  <div className="flex-1 h-px bg-white/20 mx-4"></div>
                  
                  <div className={`flex flex-col items-center ${pipelineStep >= 3 ? '' : 'opacity-50'}`}>
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center mb-2 ${pipelineStep >= 3 ? 'bg-brand-lime text-brand-dark' : 'border-2 border-white/20'}`}>
                      {pipelineStep >= 3 ? <CheckCircle2 className="w-6 h-6" /> : <div className="w-2 h-2 rounded-full bg-white"></div>}
                    </div>
                    <span className="text-xs font-medium">Reload</span>
                  </div>
                </div>
              </section>
            </div>
            
            <div className="p-8 border-t border-neutral-100 bg-white">
              <Button className="w-full rounded-full" onClick={forceRenewal}>Force Renewal <ArrowRight className="w-4 h-4 ml-2" /></Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
