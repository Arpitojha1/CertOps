import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Clock,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import api from "@/lib/api";

interface UpcomingJob {
  vaultSource: string;
  name: string;
  nextRenewalAt: string;
  secondsUntilDue: number;
}

interface RenewalEvent {
  id: number;
  vault_source?: string;
  cert_id?: string;
  timestamp: string;
  event_type: string;
  success: boolean | number;
  detail?: string;
}

interface SchedulerStatus {
  nextJob: UpcomingJob | null;
  upcoming: UpcomingJob[];
  recentEvents: RenewalEvent[];
}

function formatDuration(seconds: number): string {
  if (seconds <= 0) return "overdue";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function getEventIcon(event_type: string, success: boolean | number) {
  const ok = Boolean(success);
  if (!ok || event_type === "error")
    return <XCircle className="w-4 h-4 text-red-600" />;
  if (event_type === "renewal_started")
    return <RefreshCw className="w-4 h-4 text-blue-600" />;
  if (event_type === "reload_confirmed")
    return <CheckCircle2 className="w-4 h-4 text-green-600" />;
  return <CheckCircle2 className="w-4 h-4 text-green-600" />;
}

export default function SchedulerPage() {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<SchedulerStatus>("/api/scheduler/status")
      .then(res => setStatus(res.data))
      .catch(() => setError("Failed to load scheduler status."))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">Scheduler</h1>
          <p className="text-muted-foreground">
            Pending renewal jobs and recent scheduler activity. Jobs fire when{" "}
            <span className="font-mono text-foreground">next_renewal_at</span>{" "}
            is reached.
          </p>
        </div>

        {isLoading && <p className="text-muted-foreground">Loading…</p>}
        {error && <p className="text-red-600">{error}</p>}

        {status && (
          <>
            {/* Next job */}
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-foreground mb-4">
                Next Job
              </h2>
              {status.nextJob ? (
                <Card className="p-6">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                      <Clock className="w-5 h-5 text-blue-600" />
                    </div>
                    <div className="flex-1">
                      <p className="font-mono text-sm font-semibold text-foreground">
                        {status.nextJob.name}
                      </p>
                      <p className="text-xs text-muted-foreground mb-2">
                        {status.nextJob.vaultSource}
                      </p>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-muted-foreground">
                          Scheduled:{" "}
                          <span className="font-mono text-foreground">
                            {new Date(
                              status.nextJob.nextRenewalAt
                            ).toLocaleString()}
                          </span>
                        </span>
                        <Badge
                          className={
                            status.nextJob.secondsUntilDue <= 0
                              ? "bg-red-50 text-red-700 border-red-200"
                              : status.nextJob.secondsUntilDue < 86400
                                ? "bg-amber-50 text-amber-700 border-amber-200"
                                : "bg-slate-50 text-slate-700 border-slate-200"
                          }
                        >
                          {formatDuration(status.nextJob.secondsUntilDue)}
                        </Badge>
                      </div>
                    </div>
                  </div>
                </Card>
              ) : (
                <Card className="p-6 text-center">
                  <CheckCircle2 className="w-8 h-8 text-green-600 mx-auto mb-2" />
                  <p className="text-muted-foreground text-sm">
                    No jobs scheduled. All certificates are up to date.
                  </p>
                </Card>
              )}
            </section>

            {/* Upcoming queue */}
            {status.upcoming.length > 0 && (
              <section className="mb-8">
                <h2 className="text-lg font-semibold text-foreground mb-4">
                  Upcoming Jobs ({status.upcoming.length})
                </h2>
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-muted border-b border-border">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-foreground">
                          Certificate
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-foreground">
                          Source
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-foreground">
                          Scheduled at
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-foreground">
                          In
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {status.upcoming.map((job, i) => (
                        <tr
                          key={i}
                          className="border-b border-border hover:bg-muted/50"
                        >
                          <td className="px-4 py-3 font-mono text-sm text-foreground">
                            {job.name}
                          </td>
                          <td className="px-4 py-3 text-sm text-muted-foreground">
                            {job.vaultSource}
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                            {new Date(job.nextRenewalAt).toLocaleString()}
                          </td>
                          <td className="px-4 py-3">
                            <Badge
                              className={
                                job.secondsUntilDue <= 0
                                  ? "bg-red-50 text-red-700 border-red-200"
                                  : job.secondsUntilDue < 86400
                                    ? "bg-amber-50 text-amber-700 border-amber-200"
                                    : "bg-slate-50 text-slate-700 border-slate-200"
                              }
                            >
                              {formatDuration(job.secondsUntilDue)}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Recent events */}
            <section>
              <h2 className="text-lg font-semibold text-foreground mb-4">
                Recent Activity
              </h2>
              {status.recentEvents.length === 0 ? (
                <div className="text-center py-8 border border-dashed border-border rounded-lg">
                  <AlertCircle className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-muted-foreground text-sm">
                    No recent scheduler events.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {[...status.recentEvents].reverse().map(ev => (
                    <div
                      key={ev.id}
                      className="flex items-start gap-3 p-3 bg-muted/50 rounded border border-border"
                    >
                      <div className="shrink-0 mt-0.5">
                        {getEventIcon(ev.event_type, ev.success)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="font-mono text-xs text-foreground truncate">
                            {ev.cert_id ?? "—"}
                          </p>
                          <Badge className="text-xs bg-slate-50 text-slate-700 border-slate-200">
                            {ev.event_type.replace(/_/g, " ")}
                          </Badge>
                        </div>
                        {ev.detail && (
                          <p className="text-xs text-muted-foreground truncate mt-0.5">
                            {ev.detail}
                          </p>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground shrink-0">
                        {new Date(ev.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
