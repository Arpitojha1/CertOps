import React, { useState, useEffect } from "react";
import { Database, Plus, CheckCircle2, AlertCircle, Clock, Server, Key, ArrowRight, X, Loader2, ChevronDown } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { apiGet, apiPost, apiPut } from "@/lib/api"
import { adaptConnector, RawConnector } from "@/lib/adapters"
import { Connector } from "@/types"

export default function Connectors() {
  const [connectors, setConnectors] = useState<Connector[]>([])
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [newConnName, setNewConnName] = useState("")
  const [newConnCategory, setNewConnCategory] = useState<"Secret Store" | "Host">("Secret Store")
  const [testingId, setTestingId] = useState<string | null>(null)

  // Configure modal state
  const [editingConn, setEditingConn] = useState<Connector | null>(null)
  const [editConnName, setEditConnName] = useState("")
  const [editConnThreshold, setEditConnThreshold] = useState(30)

  useEffect(() => {
    apiGet<RawConnector[]>('/api/connectors')
      .then(raw => setConnectors(raw.map(adaptConnector)))
      .catch(() => {})
  }, [])

  const secretStores = connectors.filter(c => c.category === "Secret Store");
  const caHosts = connectors.filter(c => c.category !== "Secret Store");

  const handleAdd = () => {
    if (!newConnName) return;
    apiPost<RawConnector>('/api/connectors', {
      name: newConnName,
      category: newConnCategory.toLowerCase().replace(' ', '_'),
      renewal_threshold_days: 30,
      config: {},
      is_active: true
    })
      .then(raw => {
        setConnectors([...connectors, adaptConnector(raw)])
        setIsAddOpen(false)
        setNewConnName('')
      })
      .catch(err => window.alert('Failed to add connector: ' + (err?.response?.data?.detail || err.message)))
  }

  const handleTest = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setTestingId(id)
    apiPost('/api/connectors/' + id + '/test')
      .then((res: any) => {
        if (res.success) setConnectors(connectors.map(c => c.id === id ? { ...c, status: 'Connected' as const } : c))
        else setConnectors(connectors.map(c => c.id === id ? { ...c, status: 'Error' as const } : c))
      })
      .catch(() => setConnectors(connectors.map(c => c.id === id ? { ...c, status: 'Error' as const } : c)))
      .finally(() => setTestingId(null))
  }

  const handleConfigureClick = (conn: Connector, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingConn(conn)
    setEditConnName(conn.name)
    setEditConnThreshold(conn.renewalThreshold)
  }

  const handleSaveEdit = () => {
    if (!editingConn || !editConnName) return;
    apiPut<RawConnector>('/api/connectors/' + editingConn.id, {
      name: editConnName,
      renewal_threshold_days: editConnThreshold
    })
      .then(raw => {
        setConnectors(connectors.map(c => c.id === editingConn.id ? adaptConnector(raw) : c))
        setEditingConn(null)
      })
      .catch(err => window.alert('Failed to save configuration: ' + (err?.response?.data?.detail || err.message)))
  }

  return (
    <div className="space-y-10 relative">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Connectors</h1>
          <p className="text-neutral-500 font-medium">Manage integrations with secret stores and CAs</p>
        </div>
        <Button variant="lime" onClick={() => setIsAddOpen(true)} className="rounded-full">
          <Plus className="w-4 h-4 mr-2" />
          Add Connector
        </Button>
      </div>

      <section>
        <div className="flex items-center gap-2 mb-4">
          <Key className="w-5 h-5 text-brand-purple" />
          <h2 className="text-xl font-bold">Secret Stores</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {secretStores.map(conn => (
            <ConnectorCard key={conn.id} connector={conn} onConfigure={(e) => handleConfigureClick(conn, e)} onTest={(e) => handleTest(conn.id, e)} isTesting={testingId === conn.id} />
          ))}
          <AddCard label="Add Secret Store" onClick={() => { setNewConnCategory("Secret Store"); setIsAddOpen(true) }} />
        </div>
      </section>

      <section>
        <div className="flex items-center gap-2 mb-4">
          <Server className="w-5 h-5 text-brand-lime" />
          <h2 className="text-xl font-bold">Hosts & CAs</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {caHosts.map(conn => (
            <ConnectorCard key={conn.id} connector={conn} onConfigure={(e) => handleConfigureClick(conn, e)} onTest={(e) => handleTest(conn.id, e)} isTesting={testingId === conn.id} />
          ))}
          <AddCard label="Add Host or CA" onClick={() => { setNewConnCategory("Host"); setIsAddOpen(true) }} />
        </div>
      </section>

      {/* Add Modal */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-brand-dark/20 backdrop-blur-sm" onClick={() => setIsAddOpen(false)} />
          <Card className="relative w-full max-w-md p-6 rounded-3xl shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold">Add Connector</h2>
              <button onClick={() => setIsAddOpen(false)} className="p-2 text-neutral-400 hover:text-brand-dark rounded-full hover:bg-neutral-100">
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="space-y-4 mb-8">
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Connector Name</label>
                <Input value={newConnName} onChange={(e) => setNewConnName(e.target.value)} placeholder="e.g., Prod HashiCorp Vault" className="rounded-full" />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Category</label>
                <div className="relative inline-block w-full">
                  <select 
                    className="appearance-none w-full h-10 rounded-full border border-neutral-200 bg-white px-4 pr-10 text-sm font-bold text-neutral-700 shadow-sm focus:ring-2 focus:ring-brand-lime focus:outline-none cursor-pointer"
                    value={newConnCategory}
                    onChange={(e) => setNewConnCategory(e.target.value as any)}
                  >
                    <option value="Secret Store">Secret Store</option>
                    <option value="Host">Host</option>
                    <option value="Certificate Authority">Certificate Authority</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                </div>
              </div>
            </div>

            <Button variant="lime" className="w-full rounded-full" onClick={handleAdd}>
              Add Connector
            </Button>
          </Card>
        </div>
      )}

      {/* Edit Modal */}
      {editingConn && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-brand-dark/20 backdrop-blur-sm" onClick={() => setEditingConn(null)} />
          <Card className="relative w-full max-w-md p-6 rounded-3xl shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold">Configure Connector</h2>
              <button onClick={() => setEditingConn(null)} className="p-2 text-neutral-400 hover:text-brand-dark rounded-full hover:bg-neutral-100">
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="space-y-4 mb-8">
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Connector Name</label>
                <Input value={editConnName} onChange={(e) => setEditConnName(e.target.value)} className="rounded-full" />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Renewal Threshold (Days)</label>
                <Input type="number" value={editConnThreshold} onChange={(e) => setEditConnThreshold(Number(e.target.value))} className="rounded-full" />
              </div>
            </div>

            <Button variant="lime" className="w-full rounded-full" onClick={handleSaveEdit}>
              Save Configuration
            </Button>
          </Card>
        </div>
      )}
    </div>
  )
}

function ConnectorCard({ connector, onConfigure, onTest, isTesting }: { key?: React.Key, connector: Connector, onConfigure: (e: React.MouseEvent) => void, onTest: (e: React.MouseEvent) => void, isTesting: boolean }) {
  return (
    <Card className="p-6 flex flex-col hover:shadow-lg transition-shadow border border-neutral-100 hover:border-brand-lime/30 group rounded-3xl">
      <div className="flex justify-between items-start mb-6">
        <div className="w-12 h-12 rounded-full bg-neutral-100 flex items-center justify-center text-brand-dark group-hover:bg-brand-lime transition-colors">
          <Database className="w-6 h-6" />
        </div>
        <Badge variant={connector.status === "Connected" ? "lime" : connector.status === "Error" ? "destructive" : "warning"} className="rounded-full">
          {connector.status}
        </Badge>
      </div>
      <h3 className="font-bold text-lg mb-1">{connector.name}</h3>
      <p className="text-sm text-neutral-500 mb-6">Renewal threshold: {connector.renewalThreshold} days</p>
      
      <div className="mt-auto flex items-center gap-2">
        <Button variant="outline" size="sm" className="flex-1 font-medium bg-neutral-50 border-0 hover:bg-neutral-100 rounded-full" onClick={onConfigure}>Configure</Button>
        <Button 
          variant="outline" 
          size="sm" 
          className="flex-1 font-medium bg-neutral-50 border-0 hover:bg-neutral-100 rounded-full"
          onClick={onTest}
          disabled={isTesting}
        >
          {isTesting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Test"}
        </Button>
      </div>
    </Card>
  )
}

function AddCard({ label, onClick }: { label: string, onClick: () => void }) {
  return (
    <Card onClick={onClick} className="p-6 flex flex-col items-center justify-center text-neutral-400 hover:text-brand-dark hover:bg-brand-lime/10 transition-colors cursor-pointer border-2 border-dashed border-neutral-200 hover:border-brand-lime min-h-[220px] rounded-3xl">
      <Plus className="w-8 h-8 mb-3" />
      <span className="font-semibold">{label}</span>
    </Card>
  )
}

