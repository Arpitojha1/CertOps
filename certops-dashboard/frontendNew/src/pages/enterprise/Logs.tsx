import { useState } from "react"
import { Activity, Bell } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { EnterpriseTabs } from "@/components/ui/enterprise-tabs"
import { MOCK_EVENTS, MOCK_NOTIFICATIONS } from "@/mock-data"

export default function Logs() {
  const [tab, setTab] = useState("Logs")

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Alerts & Logs</h1>
          <p className="text-neutral-500 font-medium">System audit trails and alerting configurations</p>
        </div>
      </div>

      <EnterpriseTabs />

      <div className="flex border-b border-neutral-200 mb-6 gap-6">
        <button 
          onClick={() => setTab("Logs")}
          className={`pb-2 text-sm font-bold border-b-2 transition-colors ${tab === "Logs" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-400 hover:text-neutral-700"}`}
        >
          Certificate Logs
        </button>
        <button 
          onClick={() => setTab("Alerts")}
          className={`pb-2 text-sm font-bold border-b-2 transition-colors ${tab === "Alerts" ? "border-brand-dark text-brand-dark" : "border-transparent text-neutral-400 hover:text-neutral-700"}`}
        >
          Alert Rules
        </button>
      </div>

      {tab === "Logs" ? (
        <Card className="p-0 overflow-hidden rounded-3xl">
          <div className="p-6 border-b border-neutral-50 bg-neutral-50/50">
            <h3 className="font-bold text-xs text-neutral-500 uppercase tracking-widest">Recent Events</h3>
          </div>
          <div className="divide-y divide-neutral-50">
            {MOCK_EVENTS.map((event) => (
              <div key={event.id} className="p-6 flex items-start gap-4 hover:bg-neutral-50 transition-colors">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-brand-dark">{event.type}</span>
                    <span className="w-1 h-1 rounded-full bg-neutral-300"></span>
                    <span className="text-sm text-neutral-400">{new Date(event.timestamp).toLocaleString()}</span>
                  </div>
                  <p className="text-neutral-600 font-medium text-sm">{event.description}</p>
                </div>
                <div className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-500 uppercase tracking-widest">
                  {event.status}
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden rounded-3xl">
          <Table>
            <TableHeader>
              <TableRow className="border-none">
                <TableHead>Target Group</TableHead>
                <TableHead>Thresholds</TableHead>
                <TableHead>Channels</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_NOTIFICATIONS.map((notif) => (
                <TableRow key={notif.id}>
                  <TableCell className="font-bold">{notif.group}</TableCell>
                  <TableCell className="text-neutral-500 font-medium">{notif.threshold}</TableCell>
                  <TableCell className="text-neutral-500 font-medium">{notif.channel}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
