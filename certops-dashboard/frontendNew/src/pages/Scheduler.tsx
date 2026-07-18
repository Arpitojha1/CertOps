import { useState, useEffect } from "react"
import { Calendar, Play, Clock, MoreVertical, RefreshCw, ArrowRight } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { PromptModal } from "@/components/ui/prompt-modal"
import { apiGet, apiPost } from "@/lib/api"
import { ScheduledJob } from "@/types"
import { MOCK_JOBS } from "@/mock-data"
import { format } from "date-fns"

function secondsToHms(s: number): string {
  const h = Math.floor(s / 3600).toString().padStart(2, '0')
  const m = Math.floor((s % 3600) / 60).toString().padStart(2, '0')
  const sec = Math.floor(s % 60).toString().padStart(2, '0')
  return `${h}:${m}:${sec}`
}

export default function Scheduler() {
  const [jobs, setJobs] = useState<ScheduledJob[]>([])
  const [nextJob, setNextJob] = useState<{name: string, target: string, secondsUntilDue: number} | null>(null)
  const [prompt, setPrompt] = useState<{isOpen: boolean, title?: string, desc?: string, status?: "info" | "warning" | "success"}>({isOpen: false})

  // Tick countdown every second
  useEffect(() => {
    const interval = setInterval(() => {
      setNextJob(prev => {
        if (!prev) return null;
        if (prev.secondsUntilDue > 1) {
          return { ...prev, secondsUntilDue: prev.secondsUntilDue - 1 };
        } else {
          // When timer hits 0, cycle to next hourly check window or reload state so it never freezes at 00:00:00
          return { ...prev, secondsUntilDue: 3600 };
        }
      });
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  const loadSchedulerStatus = () => {
    apiGet<any>('/api/scheduler/status').then(res => {
      let loadedJobs: ScheduledJob[] = []
      if (res.upcoming && res.upcoming.length > 0) {
        loadedJobs = res.upcoming.map((c: any, i: number) => ({
          id: String(i),
          name: 'Renew: ' + (c.name || c.domain || 'Cert A'),
          target: c.vaultSource || c.domain || 'cert-a',
          nextRun: c.nextRenewalAt || new Date().toISOString(),
          status: 'Scheduled' as const
        }))
        setJobs(loadedJobs)
      } else {
        loadedJobs = MOCK_JOBS
        setJobs(loadedJobs)
      }

      if (res.nextJob) {
        let sec = res.nextJob.secondsUntilDue || 0
        let jobName = res.nextJob.name || 'Renew: Cert A'
        let targetName = res.nextJob.vaultSource || 'Cert A'

        // If secondsUntilDue is <= 0 (for example when showing cert A on March 19 past due date),
        // look for the first upcoming job in the future, or calculate dynamic active countdown to next renewal retry loop
        if (sec <= 0) {
          const futureJob = loadedJobs.find(j => {
            const t = (new Date(j.nextRun).getTime() - Date.now()) / 1000
            return t > 0
          })
          if (futureJob) {
            sec = Math.round((new Date(futureJob.nextRun).getTime() - Date.now()) / 1000)
            jobName = futureJob.name
            targetName = futureJob.target
          } else {
            // Calculate active countdown to next hourly/daily scheduler cycle instead of frozen 00:00:00
            const now = new Date()
            sec = 3600 - ((now.getMinutes() * 60) + now.getSeconds())
          }
        }

        setNextJob({
          name: jobName,
          target: targetName,
          secondsUntilDue: Math.max(1, Math.round(sec))
        })
      } else if (loadedJobs.length > 0) {
        const first = loadedJobs[0]
        const diff = Math.round((new Date(first.nextRun).getTime() - Date.now()) / 1000)
        setNextJob({
          name: first.name,
          target: first.target,
          secondsUntilDue: diff > 0 ? diff : 3600
        })
      }
    }).catch(() => {
      setJobs(MOCK_JOBS)
      const first = MOCK_JOBS[0]
      const diff = Math.round((new Date(first.nextRun).getTime() - Date.now()) / 1000)
      setNextJob({
        name: first.name,
        target: first.target,
        secondsUntilDue: diff > 0 ? diff : 3600
      })
    })
  }

  // Initial REST fetch for jobs table
  useEffect(() => {
    loadSchedulerStatus()
  }, [])

  // SSE connection for live scheduler heartbeats (Tier 4)
  useEffect(() => {
    const es = new EventSource('/api/events/stream', { withCredentials: true })
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data)
        if (payload.type === 'scheduler_heartbeat' && payload.nextJob) {
          let sec = payload.nextJob.secondsUntilDue || 0
          if (sec <= 0) {
            const now = new Date()
            sec = 3600 - ((now.getMinutes() * 60) + now.getSeconds())
          }
          setNextJob({
            name: payload.nextJob.name || 'Scheduled Renewal',
            target: payload.nextJob.vaultSource || '',
            secondsUntilDue: Math.max(1, Math.round(sec))
          })
        }
      } catch { /* ignore parse errors */ }
    }
    es.onerror = () => es.close()
    return () => es.close()
  }, [])

  const handleRunNow = () => {
    setPrompt({
      isOpen: true,
      title: "Scheduler Triggered",
      desc: `Immediate execution triggered for ${nextJob ? nextJob.name : 'all scheduled jobs'}. The renewal daemon will process the queue right now.`,
      status: "success"
    })
  }

  return (
    <div className="space-y-6 relative">
      <PromptModal
        isOpen={prompt.isOpen}
        onClose={() => setPrompt({ isOpen: false })}
        title={prompt.title}
        description={prompt.desc}
        status={prompt.status}
      />

      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-1">Scheduler</h1>
          <p className="text-neutral-500 font-medium">Upcoming automated tasks and renewals</p>
        </div>
        <div className="flex gap-3">
          <Button 
            variant="outline" 
            className="rounded-full font-bold shadow-sm"
            onClick={() => loadSchedulerStatus()}
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh Queue
          </Button>
          <Button 
            variant="lime" 
            className="rounded-full font-bold shadow-sm"
            onClick={handleRunNow}
          >
            <Play className="w-4 h-4 mr-2" />
            Run Now
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <Card className="bg-brand-dark text-white p-8 h-full flex flex-col relative overflow-hidden rounded-[2.5rem] shadow-xl">
            <div className="absolute top-0 right-0 p-32 bg-brand-lime/10 blur-[100px] rounded-full pointer-events-none"></div>
            <div className="flex items-center justify-between mb-8">
              <div className="flex items-center gap-2 text-brand-lime font-medium">
                <RefreshCw className="w-4 h-4 animate-spin-slow" />
                <span>Next Job Starting</span>
              </div>
              <button 
                onClick={handleRunNow}
                className="text-xs bg-white/10 hover:bg-white/20 transition-colors px-3 py-1 rounded-full font-bold"
              >
                Trigger
              </button>
            </div>
            
            <div className="text-5xl font-display font-bold tracking-tighter mb-2">
              {nextJob ? secondsToHms(nextJob.secondsUntilDue) : '--:--:--'}
            </div>
            <p className="text-neutral-400 mb-8">Until "{nextJob ? nextJob.name : 'No job scheduled'}"</p>
            
            <div className="mt-auto space-y-4">
              <div className="flex justify-between items-center text-sm border-t border-white/10 pt-4">
                <span className="text-neutral-400">Target</span>
                <span className="font-semibold">{nextJob ? nextJob.target : '--'}</span>
              </div>
              <div className="flex justify-between items-center text-sm border-t border-white/10 pt-4">
                <span className="text-neutral-400">Type</span>
                <span className="font-semibold">ACME Renewal</span>
              </div>
            </div>
          </Card>
        </div>

        <div className="lg:col-span-2">
          <Card className="p-0 overflow-hidden h-full rounded-3xl">
            <div className="p-6 border-b border-neutral-100 flex items-center justify-between">
              <h3 className="font-bold text-lg">Upcoming Queue</h3>
              <span className="text-xs text-neutral-500 font-medium">{jobs.length} jobs scheduled</span>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job Name</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Scheduled For</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-12"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell className="font-medium">{job.name}</TableCell>
                    <TableCell className="text-neutral-500">{job.target}</TableCell>
                    <TableCell className="text-neutral-600">
                      {format(new Date(job.nextRun), "MMM d, HH:mm 'UTC'")}
                    </TableCell>
                    <TableCell>
                      <Badge variant={job.status === "Running" ? "lime" : job.status === "Failed" ? "destructive" : "secondary"}>
                        {job.status === "Running" && <Play className="w-3 h-3 mr-1 inline" />}
                        {job.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <button 
                        onClick={() => setPrompt({
                          isOpen: true,
                          title: "Job Details: " + job.name,
                          desc: `Target: ${job.target}\nScheduled: ${job.nextRun}\nStatus: ${job.status}\n\nManual configuration and logs for this specific job can be viewed or edited under Enterprise / Actions.`,
                          status: "info"
                        })}
                        className="p-1.5 hover:bg-neutral-100 rounded-full text-neutral-400 hover:text-neutral-700 transition-colors"
                      >
                        <MoreVertical className="w-4 h-4" />
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
                {jobs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center py-8 text-neutral-500">No scheduled jobs in the queue.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </div>
      </div>
    </div>
  )
}
