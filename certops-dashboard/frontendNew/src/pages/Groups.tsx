import { useState, useEffect } from "react"
import { Users, Plus, Shield, Clock, Bell } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { PromptModal } from "@/components/ui/prompt-modal"
import { apiGet } from "@/lib/api"
import { GroupPolicy } from "@/types"
import { MOCK_GROUPS } from "@/mock-data"

export default function Groups() {
  const [groups, setGroups] = useState<GroupPolicy[]>([])
  const [prompt, setPrompt] = useState<{isOpen: boolean, title?: string, desc?: string}>({isOpen: false})

  useEffect(() => {
    Promise.all([
      apiGet<any[]>('/api/groups'),
      apiGet<any[]>('/api/maintenance-windows'),
      apiGet<any[]>('/api/notification-policies')
    ]).then(([grps, windows, policies]) => {
      const adapted: GroupPolicy[] = grps.map(g => ({
        id: String(g.id),
        name: g.name,
        maintenanceWindow: windows.find(w => w.group_id === g.id)
          ? (() => { const w = windows.find(w => w.group_id === g.id); return w.recurrence + ' ' + w.start_time + '-' + w.end_time })()
          : 'Not configured',
        notificationPolicy: policies.find(p => p.group_id === g.id)
          ? policies.find(p => p.group_id === g.id).threshold_days + ' days'
          : 'Default',
      }))
      setGroups(adapted.length > 0 ? adapted : MOCK_GROUPS)
    }).catch(() => {
      setGroups(MOCK_GROUPS)
    })
  }, [])

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
          onClick={() => setPrompt({
            isOpen: true,
            title: "Create Group",
            desc: "The Create Group and policy creation form is not implemented yet."
          })}
        >
          <Plus className="w-4 h-4 mr-2" />
          Create Group
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {groups.map(group => (
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
              <div className="flex items-start gap-4 p-4 rounded-2xl bg-neutral-50">
                <Clock className="w-5 h-5 text-neutral-400 mt-0.5" />
                <div>
                  <div className="text-sm font-semibold mb-1">Maintenance Window</div>
                  <div className="text-sm text-neutral-600">{group.maintenanceWindow}</div>
                </div>
              </div>
              <div className="flex items-start gap-4 p-4 rounded-2xl bg-neutral-50">
                <Bell className="w-5 h-5 text-neutral-400 mt-0.5" />
                <div>
                  <div className="text-sm font-semibold mb-1">Notification Policy</div>
                  <div className="text-sm text-neutral-600">{group.notificationPolicy}</div>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-6 border-t border-neutral-100 flex justify-end gap-2">
              <Button 
                variant="ghost" 
                size="sm" 
                className="rounded-full font-bold"
                onClick={() => setPrompt({
                  isOpen: true,
                  title: `Edit Policies (${group.name})`,
                  desc: `Policy editing and threshold assignment for ${group.name} is not implemented yet.`
                })}
              >
                Edit Policies
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                className="rounded-full font-bold"
                onClick={() => setPrompt({
                  isOpen: true,
                  title: `Manage Members (${group.name})`,
                  desc: `Member allocation and RBAC assignment for ${group.name} is not implemented yet.`
                })}
              >
                Manage Members
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
