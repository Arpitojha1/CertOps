import { useState } from "react"
import { Shield, ShieldAlert, FileSearch, XCircle, MoreVertical, ChevronDown } from "lucide-react"
import { Card } from "@/components/ui/card"
import { EnterpriseTabs } from "@/components/ui/enterprise-tabs"
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from "recharts"
import { MOCK_CHART_MONTHLY_VOLUME } from "@/mock-data"

export default function Insights() {
  const [timeframe, setTimeframe] = useState<"Monthly" | "Weekly">("Monthly")

  const weeklyData = [
    { month: 'W1', issued: 300, expired: 20 },
    { month: 'W2', issued: 450, expired: 50 },
    { month: 'W3', issued: 200, expired: 10 },
    { month: 'W4', issued: 600, expired: 80 },
  ]
  
  const chartData = timeframe === "Monthly" ? MOCK_CHART_MONTHLY_VOLUME.map(d => ({...d, issued: d.issued * 10})) : weeklyData

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-8 gap-4">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Enterprise Insights</h1>
          <p className="text-neutral-500 font-medium">Global view of all certificates across environments</p>
        </div>
        
        <div className="relative inline-block">
          <select 
            className="appearance-none h-10 rounded-full border border-neutral-200 bg-white px-4 py-2 pr-10 text-sm font-bold text-neutral-700 shadow-sm focus:ring-2 focus:ring-brand-lime focus:outline-none cursor-pointer"
          >
            <option>Last 30 Days</option>
            <option>Last 90 Days</option>
            <option>Year to Date</option>
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
        </div>
      </div>

      <EnterpriseTabs />

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Shield} label="Total Managed" value="12,482" delta="+12%" />
        <StatCard icon={ShieldAlert} label="Expiring (30d)" value="412" delta="-4%" trend="down" />
        <StatCard icon={FileSearch} label="Discovery Coverage" value="94%" delta="+2%" trend="up" />
        <StatCard icon={XCircle} label="Failed Actions (7d)" value="18" delta="+1%" trend="up" alert />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Col: Bubble Chart & Progress Bars */}
        <div className="lg:col-span-1 space-y-6">
          <Card className="h-64 flex flex-col justify-between p-6 rounded-3xl">
            <h3 className="font-bold text-lg">CA Distribution</h3>
            <div className="flex-1 flex items-center justify-center relative">
               <div className="relative w-full h-full max-w-[200px] max-h-[200px]">
                  <div className="absolute top-[10%] left-[5%] w-[110px] h-[110px] rounded-full bg-brand-lime flex items-center justify-center font-bold text-brand-dark shadow-sm transform hover:scale-105 transition-transform">6,240<br/><span className="text-[10px] uppercase absolute bottom-4">L. Encrypt</span></div>
                  <div className="absolute bottom-[5%] right-[5%] w-[90px] h-[90px] rounded-full bg-brand-purple flex items-center justify-center font-bold text-white shadow-sm hover:scale-105 transition-transform">3,120<br/><span className="text-[10px] uppercase absolute bottom-3">DigiCert</span></div>
                  <div className="absolute top-[5%] right-[0%] w-[60px] h-[60px] rounded-full bg-brand-dark text-white flex items-center justify-center font-bold text-sm shadow-sm hover:scale-105 transition-transform">2,000</div>
                  <div className="absolute bottom-[10%] left-[0%] w-[50px] h-[50px] rounded-full bg-neutral-200 text-brand-dark flex items-center justify-center font-bold text-xs shadow-sm">1,122</div>
               </div>
            </div>
          </Card>
          <Card className="p-6 rounded-3xl">
            <h3 className="font-bold text-lg mb-6">Status Breakdown</h3>
            <div className="space-y-5">
              <ProgressBar label="Active" percentage={88} color="bg-brand-lime" />
              <ProgressBar label="Expiring Soon" percentage={8} color="bg-brand-purple" />
              <ProgressBar label="Expired" percentage={3} color="bg-red-400" />
              <ProgressBar label="Revoked" percentage={1} color="bg-brand-dark" />
            </div>
          </Card>
        </div>

        {/* Right Col: Dark Feature Card */}
        <div className="lg:col-span-2">
          <Card className="h-full bg-brand-dark text-white p-8 flex flex-col rounded-3xl shadow-xl">
            <div className="flex justify-between items-start mb-10">
              <div className="flex gap-12">
                <div>
                  <div className="text-4xl font-display font-bold mb-1">{timeframe === "Monthly" ? "1,248" : "600"}</div>
                  <div className="text-xs font-bold text-neutral-400 uppercase tracking-widest">Issued this {timeframe === "Monthly" ? "month" : "week"}</div>
                </div>
                <div>
                  <div className="text-4xl font-display font-bold mb-1">{timeframe === "Monthly" ? "384" : "80"}</div>
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
                <BarChart data={chartData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
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
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={index === chartData.length - 1 ? '#D6F24C' : 'rgba(255,255,255,0.2)'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, delta, alert }: any) {
  return (
    <Card className="p-5 flex flex-col relative overflow-hidden group rounded-3xl hover:shadow-lg transition-shadow">
      <div className="flex justify-between items-start mb-4">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center ${alert ? 'bg-red-50 text-red-600' : 'bg-brand-purple/20 text-brand-purple'}`}>
          <Icon className="w-5 h-5" />
        </div>
        <button className="text-neutral-300 hover:text-brand-dark transition-colors"><MoreVertical className="w-4 h-4" /></button>
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
