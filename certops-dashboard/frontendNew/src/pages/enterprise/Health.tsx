import { MoreVertical, Server, Activity } from "lucide-react"
import { Card } from "@/components/ui/card"
import { SelectPill } from "@/components/ui/select-pill"
import { EnterpriseTabs } from "@/components/ui/enterprise-tabs"
import { AreaChart, Area, BarChart, Bar, XAxis, Tooltip, ResponsiveContainer } from "recharts"
import { MOCK_CA_HEALTH, MOCK_CHART_FAILURE_RATE, MOCK_CHART_DISCOVERY_HISTORY } from "@/mock-data-enterprise"

export default function Health() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Health & Analytics</h1>
          <p className="text-neutral-500 font-medium">Performance and reliability metrics for your CLM infrastructure</p>
        </div>
        <SelectPill value="Last 7 Days" />
      </div>

      <EnterpriseTabs />

      <h2 className="text-xl font-bold mb-4">CA Availability</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {MOCK_CA_HEALTH.map(ca => (
          <Card key={ca.id} className="p-5 flex flex-col relative overflow-hidden rounded-full">
            <div className="flex justify-between items-start mb-4">
              <div className="w-10 h-10 rounded-full flex items-center justify-center bg-neutral-100 text-brand-dark">
                <Server className="w-5 h-5" />
              </div>
              <div className={`w-2.5 h-2.5 rounded-full ${ca.status === 'Healthy' ? 'bg-brand-lime' : ca.status === 'Degraded' ? 'bg-orange-400' : 'bg-red-500'}`}></div>
            </div>
            <div className="text-xs font-bold text-neutral-400 uppercase tracking-widest mb-1">{ca.name}</div>
            <div className="text-2xl font-display font-bold leading-none mb-1">{ca.uptime}%</div>
            <div className="text-[10px] text-neutral-500 font-medium uppercase">Uptime • Error Rate: {ca.errorRate}%</div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="p-6 rounded-3xl">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-brand-purple" />
              <h3 className="font-bold text-lg">Action Failure Rate</h3>
            </div>
            <button onClick={() => window.alert('More options not implemented')} className="text-neutral-300 hover:text-brand-dark transition-colors"><MoreVertical className="w-5 h-5" /></button>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={MOCK_CHART_FAILURE_RATE} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#B4A6F0" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#B4A6F0" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <XAxis dataKey="timestamp" axisLine={false} tickLine={false} tick={{ fill: '#888', fontSize: 10, fontWeight: 'bold' }} dy={10} />
                <Tooltip cursor={{stroke: 'rgba(0,0,0,0.1)'}} contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }} />
                <Area type="monotone" dataKey="value" stroke="#B4A6F0" strokeWidth={3} fillOpacity={1} fill="url(#colorValue)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6 rounded-3xl">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-brand-lime" />
              <h3 className="font-bold text-lg">Discovery Efficiency</h3>
            </div>
            <button onClick={() => window.alert('More options not implemented')} className="text-neutral-300 hover:text-brand-dark transition-colors"><MoreVertical className="w-5 h-5" /></button>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={MOCK_CHART_DISCOVERY_HISTORY} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="run" axisLine={false} tickLine={false} tick={{ fill: '#888', fontSize: 10, fontWeight: 'bold' }} dy={10} />
                <Tooltip cursor={{fill: 'rgba(0,0,0,0.02)'}} contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px rgba(0,0,0,0.08)' }} />
                <Bar dataKey="found" fill="#D6F24C" radius={[4, 4, 0, 0]} />
                <Bar dataKey="scanned" fill="#F5F6ED" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6 rounded-3xl lg:col-span-2">
          <div className="text-xs font-bold text-neutral-400 uppercase tracking-widest mb-1">Expiry Risk Distribution</div>
          <div className="text-2xl font-display font-bold mb-6">99.8% Healthy</div>
          
          <div className="grid grid-cols-12 md:grid-cols-24 gap-1.5 h-32 content-start">
            {Array.from({ length: 96 }).map((_, i) => {
              const opacity = i < 5 ? 0.2 : i < 15 ? 0.4 : i < 30 ? 0.6 : i < 60 ? 0.8 : 1;
              const color = i < 5 ? 'bg-red-400' : i < 15 ? 'bg-brand-purple' : 'bg-brand-lime';
              return (
                <div key={i} className={`w-full aspect-square ${color} rounded-full`} style={{ opacity }}></div>
              )
            })}
          </div>
          <div className="flex justify-between mt-4 text-[10px] font-bold text-neutral-400 uppercase tracking-widest">
            <span>Critical (0-7 Days)</span>
            <span>Warning (7-30 Days)</span>
            <span>Healthy (30+ Days)</span>
          </div>
        </Card>
      </div>
    </div>
  )
}
