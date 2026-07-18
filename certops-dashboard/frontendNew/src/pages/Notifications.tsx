import { useState, useEffect } from "react"
import { Bell, Plus, Mail, MessageSquare, AlertTriangle } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { PromptModal } from "@/components/ui/prompt-modal"
import { apiGet } from "@/lib/api"
import { NotificationPolicy } from "@/types"
import { MOCK_NOTIFICATIONS } from "@/mock-data"

export default function Notifications() {
  const [policies, setPolicies] = useState<NotificationPolicy[]>([])
  const [prompt, setPrompt] = useState<{isOpen: boolean, title?: string, desc?: string}>({isOpen: false})

  useEffect(() => {
    Promise.all([
      apiGet<any[]>('/api/notification-policies'),
      apiGet<any[]>('/api/groups')
    ]).then(([rawPolicies, groups]) => {
      const adapted = rawPolicies.map(p => ({
        id: String(p.id),
        group: groups.find(g => g.id === p.group_id)?.name || String(p.group_id),
        threshold: p.threshold_days ? p.threshold_days + ' days' : '30 days',
        channel: p.channel || 'Email',
        status: p.is_active === false ? 'Disabled' as const : 'Active' as const,
      }))
      setPolicies(adapted.length > 0 ? adapted : MOCK_NOTIFICATIONS)
    }).catch(() => {
      setPolicies(MOCK_NOTIFICATIONS)
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
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Notifications</h1>
          <p className="text-neutral-500 font-medium">Configure alerting and communication channels</p>
        </div>
        <Button 
          variant="lime" 
          className="rounded-full font-bold shadow-sm"
          onClick={() => setPrompt({
            isOpen: true,
            title: "Add Notification Policy",
            desc: "The Add Policy form for Slack, PagerDuty, and Email integration is not implemented yet."
          })}
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Policy
        </Button>
      </div>

      <Card className="p-0 overflow-hidden rounded-3xl">
        <Table>
          <TableHeader>
            <TableRow className="border-none">
              <TableHead>Target Group</TableHead>
              <TableHead>Thresholds</TableHead>
              <TableHead>Channels</TableHead>
              <TableHead>Status</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {policies.map((notif) => (
              <TableRow key={notif.id}>
                <TableCell className="font-bold">{notif.group}</TableCell>
                <TableCell className="text-neutral-500">{notif.threshold}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    {notif.channel.includes("Email") && <Mail className="w-4 h-4 text-neutral-400" />}
                    {notif.channel.includes("Slack") && <MessageSquare className="w-4 h-4 text-neutral-400" />}
                    {notif.channel.includes("PagerDuty") && <AlertTriangle className="w-4 h-4 text-red-400" />}
                    <span className="text-sm text-neutral-600">{notif.channel}</span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={notif.status === "Active" ? "lime" : "secondary"} className="rounded-full">{notif.status}</Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    className="rounded-full font-bold"
                    onClick={() => setPrompt({
                      isOpen: true,
                      title: `Edit Policy (${notif.group})`,
                      desc: `Channel and threshold adjustments for ${notif.group} are not implemented yet.`
                    })}
                  >
                    Edit
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {policies.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-neutral-500">No notification policies configured.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}
