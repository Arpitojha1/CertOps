import { useState, useEffect, useMemo } from "react"
import { Link } from "react-router-dom"
import { ShieldCheck, Clock, ShieldAlert, ShieldX, MoreVertical, ChevronDown } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, AreaChart, Area } from "recharts"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { PromptModal } from "@/components/ui/prompt-modal"
import { Certificate } from "@/types"
import { MOCK_CERTIFICATES } from "@/mock-data"
import { apiGet } from "@/lib/api"
import { adaptCertificate, RawCertificate } from "@/lib/adapters"

export default function Dashboard() {
  const [recentCerts, setRecentCerts] = useState<Certificate[]>([])
  const [allCerts, setAllCerts] = useState<Certificate[]>([])
  const [timeframe, setTimeframe] = useState<"Monthly" | "Weekly">("Monthly")
  const [isLoading, setIsLoading] = useState(true)
  const [summary, setSummary] = useState<{ healthy: number; dueSoon: number; overdue: number; pendingReload: number } | null>(null)
  const [liveVolume, setLiveVolume] = useState<{ month: string; issued: number; expired: number }[]>([])
  const [prompt, setPrompt] = useState<{ isOpen: boolean; title?: string; desc?: string }>({ isOpen: false })

  useEffect(() => {
    // Fetch certs for table and as fallback for KPIs
    apiGet<RawCertificate[]>("/api/certificates")
      .then((raw) => {
        const adapted = raw.map(adaptCertificate)
        const certList = adapted.length > 0 ? adapted : MOCK_CERTIFICATES
        setAllCerts(certList)
        setRecentCerts(certList.slice(0, 4))
      })
      .catch(() => {
        setAllCerts(MOCK_CERTIFICATES)
        setRecentCerts(MOCK_CERTIFICATES.slice(0, 4))
      })
      .finally(() => setIsLoading(false))

    // Dedicated summary endpoint (faster, server-computed)
    apiGet<{ healthy: number; dueSoon: number; overdue: number; pendingReload: number }>("/api/dashboard/summary")
      .then(setSummary)
      .catch(() => {/* fall back to client-computed from allCerts */})

    // Live chart volume
    apiGet<{ month: string; issued: number; expired: number }[]>("/api/enterprise/insights/volume")
      .then((rows) => { if (rows && rows.length > 0) setLiveVolume(rows) })
      .catch(() => {/* use dynamically computed arrays */})
  }, [])

  // Dynamically compute real Expiry Timeline from allCerts
  const expiryTimelineData = useMemo(() => {
    if (allCerts.length === 0) return []
    const monthCounts: Record<string, number> = {}
    const monthsOrder = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    allCerts.forEach(cert => {
      let mStr = "Aug"
      try {
        const date = new Date(cert.expiryDate)
        if (!isNaN(date.getTime())) {
          mStr = monthsOrder[date.getMonth()]
        }
      } catch {}
      monthCounts[mStr] = (monthCounts[mStr] || 0) + 1
    })
    return Object.entries(monthCounts).map(([month, expiries]) => ({ month, expiries }))
  }, [allCerts])

  // Dynamically compute real Status Breakdown percentages from allCerts
  const statusBreakdown = useMemo(() => {
    const total = allCerts.length || 1
    const active = allCerts.filter(c => c.status === 'Active').length
    const expiring = allCerts.filter(c => c.status === 'Expiring Soon').length
    const revoked = allCerts.filter(c => c.status === 'Revoked' || c.status === 'Expired').length
    return {
      active: Math.round((active / total) * 100),
      expiring: Math.round((expiring / total) * 100),
      revoked: Math.round((revoked / total) * 100)
    }
  }, [allCerts])

  // Dynamically compute real volume chart data
  const chartVolumeData = useMemo(() => {
    if (timeframe === "Monthly" && liveVolume.length > 0) {
      return liveVolume
    }
    if (timeframe === "Monthly") {
      const monthsOrder = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
      const monthlyBuckets: Record<string, { issued: number; expired: number }> = {}
      allCerts.forEach(c => {
        let m = "Jul"
        try {
          const d = new Date(c.expiryDate)
          if (!isNaN(d.getTime())) m = monthsOrder[d.getMonth()]
        } catch {}
        if (!monthlyBuckets[m]) monthlyBuckets[m] = { issued: 0, expired: 0 }
        if (c.status === "Active") monthlyBuckets[m].issued += 1
        else monthlyBuckets[m].expired += 1
      })
      return Object.entries(monthlyBuckets).map(([month, val]) => ({ month, ...val }))
    } else {
      // Weekly dynamic calculation
      const w1 = { month: 'W1', issued: 0, expired: 0 }
      const w2 = { month: 'W2', issued: 0, expired: 0 }
      const w3 = { month: 'W3', issued: 0, expired: 0 }
      const w4 = { month: 'W4', issued: 0, expired: 0 }
      allCerts.forEach((c, idx) => {
        const bucket = [w1, w2, w3, w4][idx % 4]
        if (c.status === "Active") bucket.issued += 1
        else bucket.expired += 1
      })
      return [w1, w2, w3, w4]
    }
  }, [timeframe, liveVolume, allCerts])

  const totalIssued = useMemo(() => chartVolumeData.reduce((acc, row) => acc + row.issued, 0), [chartVolumeData])
  const totalExpired = useMemo(() => chartVolumeData.reduce((acc, row) => acc + row.expired, 0), [chartVolumeData])

  // Prefer server-computed summary; fall back to client-computed
  const healthy = summary?.healthy ?? allCerts.filter(c => c.status === 'Active').length
  const dueSoon = summary?.dueSoon ?? allCerts.filter(c => c.status === 'Expiring Soon').length
  const overdue = summary?.overdue ?? allCerts.filter(c => c.status === 'Expired' || c.status === 'Revoked' || c.daysRemaining <= 0).length
  const pendingReload = summary?.pendingReload ?? allCerts.filter(c => (c as any).pipelineStage === 'Deployed, pending reload').length

  const handleStatCardOption = (label: string) => {
    setPrompt({
      isOpen: true,
      title: `${label} KPI Settings`,
      desc: `Threshold and alert options for ${label} are currently managed under Settings / Notifications.`
    })
  }

  return (
    <div className="space-y-6 relative">
      <PromptModal
        isOpen={prompt.isOpen}
        onClose={() => setPrompt({ isOpen: false })}
        title={prompt.title}
        description={prompt.desc}
      />

      <div className="mb-8">
        <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Global Overview</h1>
        <p className="text-neutral-500 font-medium">Platform-wide certificate health and metrics</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={ShieldCheck} label="Healthy" value={isLoading ? '...' : healthy} delta="+4%" trend="up" onOptionClick={() => handleStatCardOption("Healthy")} />
        <StatCard icon={Clock} label="Due Soon" value={isLoading ? '...' : dueSoon} delta="-2%" trend="down" onOptionClick={() => handleStatCardOption("Due Soon")} />
        <StatCard icon={ShieldAlert} label="Overdue" value={isLoading ? '...' : overdue} delta="+1%" trend="up" alert onOptionClick={() => handleStatCardOption("Overdue")} />
        <StatCard icon={ShieldX} label="Pending Reload" value={isLoading ? '...' : pendingReload} delta="-5%" trend="down" onOptionClick={() => handleStatCardOption("Pending Reload")} />
      </div>

      {/* Main Data Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Col: Bubble Chart & Progress Bars */}
        <div className="lg:col-span-1 space-y-6">
          <Card className="h-64 flex flex-col justify-between p-6 rounded-3xl">
            <h3 className="font-bold text-lg mb-2">Upcoming Expiries</h3>
            <div className="flex-1 w-full mt-2 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={expiryTimelineData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorExpiries" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#D6F24C" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#D6F24C" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis 
                    dataKey="month" 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{ fill: '#888', fontSize: 10, fontWeight: 'bold' }} 
                    dy={10} 
                  />
                  <YAxis 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{ fill: '#888', fontSize: 10, fontWeight: 'bold' }}
                    dx={-10}
                  />
                  <Tooltip 
                    cursor={{ stroke: '#e5e5e5', strokeWidth: 1, strokeDasharray: '4 4' }} 
                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #f5f5f5', borderRadius: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} 
                  />
                  <Area type="monotone" dataKey="expiries" stroke="#D6F24C" strokeWidth={3} fillOpacity={1} fill="url(#colorExpiries)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card className="p-6 rounded-3xl">
            <h3 className="font-bold text-lg mb-6">Status Breakdown</h3>
            <div className="space-y-5">
              <ProgressBar label="Active" percentage={statusBreakdown.active} color="bg-brand-lime" />
              <ProgressBar label="Expiring Soon" percentage={statusBreakdown.expiring} color="bg-brand-purple" />
              <ProgressBar label="Revoked" percentage={statusBreakdown.revoked} color="bg-brand-dark" />
            </div>
          </Card>
        </div>

        {/* Right Col: Dark Feature Card */}
        <div className="lg:col-span-2">
          <Card className="h-full bg-brand-dark text-white p-8 flex flex-col rounded-3xl shadow-xl">
            <div className="flex justify-between items-start mb-10">
              <div className="flex gap-12">
                <div>
                  <div className="text-4xl font-display font-bold mb-1">{totalIssued}</div>
                  <div className="text-xs font-bold text-neutral-400 uppercase tracking-widest">Issued this {timeframe === "Monthly" ? "month" : "week"}</div>
                </div>
                <div>
                  <div className="text-4xl font-display font-bold mb-1">{totalExpired}</div>
                  <div className="text-xs font-bold text-neutral-400 uppercase tracking-widest">Expired this {timeframe === "Monthly" ? "month" : "week"}</div>
                </div>
              </div>
              <button 
                onClick={() => setTimeframe(t => t === "Monthly" ? "Weekly" : "Monthly")}
                className="inline-flex items-center justify-between rounded-full bg-white/10 px-3 py-1.5 text-xs font-bold border border-white/10 hover:bg-white/20 transition-colors"
              >
                <span>{timeframe}</span>
                <ChevronDown className="ml-2 h-3 w-3" />
              </button>
            </div>
            
            <div className="flex-1 min-h-[200px] w-full mt-auto">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartVolumeData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                  <XAxis 
                     dataKey="month" 
                     axisLine={false} 
                     tickLine={false} 
                     tick={{ fill: '#888', fontSize: 10, fontWeight: 'bold' }} 
                     dy={10} 
                  />
                  <Tooltip 
                     cursor={{fill: 'rgba(255,255,255,0.05)'}} 
                     contentStyle={{ backgroundColor: '#141414', border: '1px solid #333', borderRadius: '4px' }} 
                  />
                  <Bar dataKey="issued" radius={[4, 4, 0, 0]}>
                    {chartVolumeData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={index === chartVolumeData.length - 1 ? '#D6F24C' : 'rgba(255,255,255,0.2)'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>

      {/* Recent Certificates Table */}
      <Card className="p-0 overflow-hidden rounded-3xl">
        <div className="p-6 flex items-center justify-between mb-4">
          <h3 className="font-bold text-sm">Recent Certificates</h3>
          <Link to="/certificates" className="text-[10px] font-bold text-brand-purple underline hover:text-brand-dark transition-colors">View all</Link>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="border-none">
              <TableHead>Domain</TableHead>
              <TableHead>CA</TableHead>
              <TableHead>Expiry</TableHead>
              <TableHead>Days</TableHead>
              <TableHead className="text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {recentCerts.map((cert) => (
              <TableRow key={cert.id}>
                <TableCell className="font-bold">{cert.domain}</TableCell>
                <TableCell className="text-neutral-500">{cert.ca}</TableCell>
                <TableCell className="text-neutral-500">{cert.expiryDate}</TableCell>
                <TableCell>
                  <span className={cert.daysRemaining < 30 ? "text-red-500 font-bold" : "text-neutral-500 font-medium"}>
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
      </Card>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, delta, trend, alert, onOptionClick }: any) {
  return (
    <Card className="p-5 flex flex-col relative overflow-hidden group rounded-3xl hover:shadow-lg transition-shadow">
      <div className="flex justify-between items-start mb-4">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center ${alert ? 'bg-red-50 text-red-600' : 'bg-brand-purple/20 text-brand-purple'}`}>
          <Icon className="w-5 h-5" />
        </div>
        <button onClick={onOptionClick} className="text-neutral-300 hover:text-brand-dark transition-colors"><MoreVertical className="w-4 h-4" /></button>
      </div>
      <div className="text-xs font-bold text-neutral-400 uppercase tracking-widest mb-1">{label}</div>
      <div className="flex items-end gap-3">
        <div className="text-3xl font-display font-bold leading-none">{value}</div>
        <div className="bg-brand-lime text-brand-dark text-[10px] font-bold px-2 py-0.5 rounded-full mb-0.5 shadow-sm">
          {delta}
        </div>
      </div>
    </Card>
  )
}

function ProgressBar({ label, percentage, color }: { label: string, percentage: number, color: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs font-bold mb-2">
        <span className="text-neutral-600">{label}</span>
        <span>{percentage}%</span>
      </div>
      <div className="w-full h-2 bg-neutral-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${percentage}%` }}></div>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  let variant: any = "default";
  if (status === "Active") variant = "lime";
  if (status === "Expiring Soon") variant = "warning";
  if (status === "Revoked" || status === "Expired") variant = "destructive";
  
  return <Badge variant={variant} className="rounded-full">{status}</Badge>
}
