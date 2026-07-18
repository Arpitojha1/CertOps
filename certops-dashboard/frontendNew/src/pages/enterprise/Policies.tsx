import { useState } from "react"
import { Users, Plus, Shield, ShieldCheck } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { PromptModal } from "@/components/ui/prompt-modal"
import { EnterpriseTabs } from "@/components/ui/enterprise-tabs"
import { MOCK_GROUPS } from "@/mock-data"
import { MOCK_CA_POLICIES as ENT_CA_POLICIES } from "@/mock-data-enterprise"

export default function Policies() {
  const [tab, setTab] = useState("Groups")
  const [prompt, setPrompt] = useState<{isOpen: boolean, title?: string, desc?: string}>({isOpen: false})

  return (
    <div className="space-y-6 relative">
      <PromptModal
        isOpen={prompt.isOpen}
        onClose={() => setPrompt({ isOpen: false })}
        title={prompt.title}
        description={prompt.desc}
      />

      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Groups & Policies</h1>
          <p className="text-neutral-500 font-medium">Manage environment segregation and rules</p>
        </div>
        <Button 
          variant="lime" 
          className="rounded-full font-bold shadow-sm"
          onClick={() => setPrompt({
            isOpen: true,
            title: tab === "Groups" ? "Create Access Group" : "Add CA Policy",
            desc: tab === "Groups" 
              ? "The Create Access Group wizard is not implemented yet."
              : "The Certificate Authority policy builder and rule enforcement configuration is not implemented yet."
          })}
        >
          <Plus className="w-4 h-4 mr-2" />
          {tab === "Groups" ? "Create Group" : "Add Policy"}
        </Button>
      </div>

      <EnterpriseTabs />

      <div className="flex border-b border-neutral-200 mb-6 gap-6">
        <button 
          onClick={() => setTab("Groups")}
          className={`pb-2 text-sm font-bold border-b-2 transition-colors ${tab === "Groups" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-400 hover:text-neutral-700"}`}
        >
          Access Groups
        </button>
        <button 
          onClick={() => setTab("CA")}
          className={`pb-2 text-sm font-bold border-b-2 transition-colors ${tab === "CA" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-400 hover:text-neutral-700"}`}
        >
          CA Policies
        </button>
      </div>

      {tab === "Groups" ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {MOCK_GROUPS.map(group => (
            <Card key={group.id} className="p-6 rounded-3xl">
              <div className="flex justify-between items-start mb-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-brand-purple/20 text-brand-purple flex items-center justify-center">
                    <Users className="w-5 h-5" />
                  </div>
                  <h3 className="font-bold text-xl">{group.name}</h3>
                </div>
                <Badge variant="outline" className="rounded-full">{group.id}</Badge>
              </div>
              
              <div className="space-y-4">
                <div className="flex items-start gap-4 p-4 rounded-3xl bg-neutral-50">
                  <div>
                    <div className="text-xs font-bold text-neutral-400 uppercase tracking-widest mb-1">Maintenance Window</div>
                    <div className="text-sm font-semibold">{group.maintenanceWindow}</div>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="p-0 overflow-hidden rounded-3xl">
          <div className="p-6 border-b border-neutral-50 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-brand-lime" />
            <h3 className="font-bold text-sm">Certificate Authority Rules</h3>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-none">
                <TableHead>Target Group</TableHead>
                <TableHead>Allowed CAs</TableHead>
                <TableHead>Threshold</TableHead>
                <TableHead>Auto-Renew</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ENT_CA_POLICIES.map(policy => (
                <TableRow key={policy.id}>
                  <TableCell className="font-bold">{policy.group}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {policy.allowedCAs.map((ca, index) => (
                        <Badge key={ca || index} variant="secondary" className="font-medium bg-neutral-100 rounded-full">{ca}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-neutral-500 font-medium">{policy.renewalThreshold} days</TableCell>
                  <TableCell>
                    <Badge variant={policy.autoRenew ? "lime" : "secondary"} className="rounded-full">
                      {policy.autoRenew ? "Enabled" : "Manual"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
