import { useState, useEffect } from "react"
import { Activity as ActivityIcon, CheckCircle2, XCircle, Info, Settings, ChevronDown } from "lucide-react"
import { Card } from "@/components/ui/card"
import { apiGet } from "@/lib/api"
import { adaptEventLog, RawEventLog } from "@/lib/adapters"
import { EventLog } from "@/types"
import { format } from "date-fns"

export default function Activity() {
  const [allEvents, setAllEvents] = useState<EventLog[]>([])
  const [typeFilter, setTypeFilter] = useState("All")
  const [dateFilter, setDateFilter] = useState("Last 7 Days")
  const [page, setPage] = useState(1)
  const itemsPerPage = 5

  useEffect(() => {
    let startDate: string | undefined = undefined;
    const now = new Date();
    if (dateFilter === "Today") {
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      startDate = today.toISOString();
    } else if (dateFilter === "Last 7 Days") {
      const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      startDate = sevenDaysAgo.toISOString();
    } else if (dateFilter === "Last 30 Days") {
      const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      startDate = thirtyDaysAgo.toISOString();
    }

    const params: any = { limit: 100 };
    if (startDate) {
      params.start_date = startDate;
    }

    apiGet<{items: RawEventLog[], total: number}>('/api/activity-log', params)
      .then(res => setAllEvents(res.items.map(adaptEventLog)))
      .catch(() => {})
  }, [dateFilter])

  const getIcon = (type: string, status: string) => {
    if (status === "Failed") return <XCircle className="w-5 h-5 text-red-500" />
    if (status === "Success") return <CheckCircle2 className="w-5 h-5 text-brand-lime" />
    if (type === "Config") return <Settings className="w-5 h-5 text-neutral-500" />
    return <Info className="w-5 h-5 text-brand-purple" />
  }

  const filteredEvents = allEvents.filter(event => {
    if (typeFilter !== "All" && event.type !== typeFilter) return false
    return true
  })

  const visibleEvents = filteredEvents.slice(0, page * itemsPerPage)
  const hasMore = visibleEvents.length < filteredEvents.length

  const uniqueTypes = ["All", ...Array.from(new Set(allEvents.map(e => e.type)))]

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-8 gap-4">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Activity Log</h1>
          <p className="text-neutral-500 font-medium">System events and audit trail</p>
        </div>
        <div className="flex gap-2">
          <div className="relative inline-block">
            <select 
              className="appearance-none h-10 rounded-full border border-neutral-200 bg-white px-4 py-2 pr-10 text-sm font-bold text-neutral-700 shadow-sm focus:ring-2 focus:ring-brand-lime focus:outline-none cursor-pointer"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
            >
              {uniqueTypes.map(t => <option key={t} value={t}>Type: {t}</option>)}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
          </div>
          <div className="relative inline-block">
            <select 
              className="appearance-none h-10 rounded-full border border-neutral-200 bg-white px-4 py-2 pr-10 text-sm font-bold text-neutral-700 shadow-sm focus:ring-2 focus:ring-brand-lime focus:outline-none cursor-pointer"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
            >
              <option>Today</option>
              <option>Last 7 Days</option>
              <option>Last 30 Days</option>
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
          </div>
        </div>
      </div>

      <Card className="p-0 overflow-hidden rounded-3xl">
        <div className="p-6 border-b border-neutral-100 bg-neutral-50/50">
          <h3 className="font-bold text-sm text-neutral-500 uppercase tracking-wider">{dateFilter}</h3>
        </div>
        <div className="divide-y divide-neutral-100">
          {visibleEvents.map((event) => (
            <div key={event.id} className="p-6 flex items-start gap-4 hover:bg-neutral-50 transition-colors">
              <div className="mt-1 flex-shrink-0">
                {getIcon(event.type, event.status)}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-bold text-brand-dark">{event.type}</span>
                  <span className="w-1 h-1 rounded-full bg-neutral-300"></span>
                  <span className="text-sm text-neutral-400">{format(new Date(event.timestamp), "HH:mm:ss 'UTC'")}</span>
                </div>
                <p className="text-neutral-600">{event.description}</p>
              </div>
              <div className="text-xs font-medium px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-600">
                {event.id}
              </div>
            </div>
          ))}
          {visibleEvents.length === 0 && (
            <div className="p-12 text-center text-neutral-500">No activity logs found.</div>
          )}
        </div>
      </Card>
      
      {hasMore && (
        <div className="flex justify-center mt-6">
          <button 
            onClick={() => setPage(p => p + 1)}
            className="px-6 py-2 rounded-full border border-neutral-200 text-sm font-medium hover:bg-neutral-50 transition-colors bg-white shadow-sm"
          >
            Load More
          </button>
        </div>
      )}
    </div>
  )
}
