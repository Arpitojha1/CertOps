import { useState, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CheckCircle2,
  AlertCircle,
  Clock,
  XCircle,
  RefreshCw,
  Shield,
  UserPlus,
  LogIn,
  Server,
  ServerCrash,
  Users,
  Bell,
  BellOff,
} from "lucide-react";
import api from "@/lib/api";

interface ActivityEntry {
  id: number;
  event_type: string;
  actor_user_id: number | null;
  actor_email: string | null;
  target: string | null;
  details: string | null;
  timestamp: string;
}

interface ActivityLogResponse {
  items: ActivityEntry[];
  total: number;
}

const EVENT_ICONS: Record<string, React.ReactNode> = {
  certificate_renewed: <CheckCircle2 className="w-5 h-5 text-green-600" />,
  certificate_renewal_failed: <XCircle className="w-5 h-5 text-red-600" />,
  connector_created: <Server className="w-5 h-5 text-blue-600" />,
  connector_updated: <Server className="w-5 h-5 text-slate-500" />,
  connector_deleted: <ServerCrash className="w-5 h-5 text-orange-600" />,
  connector_tested: <CheckCircle2 className="w-5 h-5 text-cyan-600" />,
  group_created: <Users className="w-5 h-5 text-violet-600" />,
  group_assigned: <Users className="w-5 h-5 text-violet-400" />,
  maintenance_window_created: <Clock className="w-5 h-5 text-amber-600" />,
  notification_policy_created: <Bell className="w-5 h-5 text-pink-600" />,
  notification_policy_deleted: <BellOff className="w-5 h-5 text-pink-400" />,
  user_login: <LogIn className="w-5 h-5 text-indigo-600" />,
  invite_generated: <UserPlus className="w-5 h-5 text-indigo-400" />,
  invite_redeemed: <UserPlus className="w-5 h-5 text-indigo-500" />,
};

const EVENT_BADGES: Record<string, string> = {
  certificate_renewed: "bg-green-50 text-green-700 border-green-200",
  certificate_renewal_failed: "bg-red-50 text-red-700 border-red-200",
  connector_created: "bg-blue-50 text-blue-700 border-blue-200",
  connector_updated: "bg-slate-50 text-slate-700 border-slate-200",
  connector_deleted: "bg-orange-50 text-orange-700 border-orange-200",
  connector_tested: "bg-cyan-50 text-cyan-700 border-cyan-200",
  group_created: "bg-violet-50 text-violet-700 border-violet-200",
  group_assigned: "bg-violet-50 text-violet-600 border-violet-200",
  maintenance_window_created: "bg-amber-50 text-amber-700 border-amber-200",
  notification_policy_created: "bg-pink-50 text-pink-700 border-pink-200",
  notification_policy_deleted: "bg-pink-50 text-pink-600 border-pink-200",
  user_login: "bg-indigo-50 text-indigo-700 border-indigo-200",
  invite_generated: "bg-indigo-50 text-indigo-600 border-indigo-200",
  invite_redeemed: "bg-indigo-50 text-indigo-500 border-indigo-200",
};

const EVENT_TYPE_OPTIONS = [
  { value: "all", label: "All events" },
  { value: "certificate_renewed", label: "Certificate renewed" },
  { value: "certificate_renewal_failed", label: "Renewal failed" },
  { value: "connector_created", label: "Connector created" },
  { value: "connector_updated", label: "Connector updated" },
  { value: "connector_deleted", label: "Connector deleted" },
  { value: "connector_tested", label: "Connector tested" },
  { value: "group_created", label: "Group created" },
  { value: "group_assigned", label: "Cert assigned to group" },
  { value: "maintenance_window_created", label: "Maintenance window" },
  { value: "notification_policy_created", label: "Notification policy created" },
  { value: "notification_policy_deleted", label: "Notification policy deleted" },
  { value: "user_login", label: "User login" },
  { value: "invite_generated", label: "Invite generated" },
  { value: "invite_redeemed", label: "Invite redeemed" },
];

function formatEventType(event_type: string): string {
  return event_type.replace(/_/g, " ");
}

function formatDetails(details: string | null): string | null {
  if (!details) return null;
  try {
    const parsed = JSON.parse(details);
    const parts: string[] = [];
    if (parsed.name) parts.push(parsed.name);
    if (parsed.email && !parts.includes(parsed.email)) parts.push(parsed.email);
    if (parsed.category) parts.push(parsed.category);
    if (parsed.threshold_days) parts.push(`${parsed.threshold_days}d threshold`);
    if (parsed.role) parts.push(`role: ${parsed.role}`);
    if (parsed.group_id !== undefined) parts.push(`group #${parsed.group_id}`);
    return parts.length > 0 ? parts.join(" - ") : null;
  } catch {
    return details;
  }
}

const PAGE_SIZE = 50;

export default function ActivityPage() {
  const [items, setItems] = useState<ActivityEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState("all");
  const [offset, setOffset] = useState(0);

  const fetchLogs = useCallback(
    async (currentOffset: number, append: boolean) => {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(currentOffset),
      });
      if (eventTypeFilter !== "all") params.set("event_type", eventTypeFilter);

      try {
        const res = await api.get<ActivityLogResponse>(
          `/api/activity-log?${params.toString()}`
        );
        if (append) {
          setItems(prev => [...prev, ...res.data.items]);
        } else {
          setItems(res.data.items);
        }
        setTotal(res.data.total);
      } catch {
        setError("Failed to load activity log.");
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [eventTypeFilter]
  );

  useEffect(() => {
    setIsLoading(true);
    setOffset(0);
    fetchLogs(0, false);
  }, [fetchLogs]);

  const loadMore = () => {
    const nextOffset = offset + PAGE_SIZE;
    setIsLoadingMore(true);
    setOffset(nextOffset);
    fetchLogs(nextOffset, true);
  };

  const hasMore = items.length < total;

  // Group by day
  const groupedByDay = items.reduce(
    (acc, event) => {
      const date = new Date(event.timestamp).toLocaleDateString();
      if (!acc[date]) acc[date] = [];
      acc[date].push(event);
      return acc;
    },
    {} as Record<string, ActivityEntry[]>
  );

  const days = Object.keys(groupedByDay).sort(
    (a, b) => new Date(b).getTime() - new Date(a).getTime()
  );

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">Activity</h1>
          <p className="text-muted-foreground">
            System events, certificate lifecycle changes, and user actions
          </p>
          {total > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              Showing {items.length} of {total} events
            </p>
          )}
        </div>

        {/* Filters */}
        <div className="flex gap-4 mb-6">
          <Select value={eventTypeFilter} onValueChange={setEventTypeFilter}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {EVENT_TYPE_OPTIONS.map(o => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {isLoading && <p className="text-muted-foreground">Loading...</p>}
        {error && <p className="text-red-600">{error}</p>}

        <div className="space-y-8">
          {days.map(day => (
            <div key={day}>
              <h2 className="text-sm font-semibold text-muted-foreground mb-4 uppercase tracking-wide">
                {new Date(day).toLocaleDateString("en-US", {
                  weekday: "long",
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })}
              </h2>

              <div className="space-y-3">
                {groupedByDay[day].map(event => (
                  <Card
                    key={event.id}
                    className="p-4 hover:shadow-md transition-shadow"
                  >
                    <div className="flex gap-4">
                      <div className="flex-shrink-0 pt-1">
                        {EVENT_ICONS[event.event_type] || (
                          <Shield className="w-5 h-5 text-muted-foreground" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-4 mb-2">
                          <div>
                            <p className="font-semibold text-foreground font-mono text-sm">
                              {event.target ?? "system"}
                            </p>
                            {event.actor_email && (
                              <p className="text-xs text-muted-foreground">
                                by {event.actor_email}
                              </p>
                            )}
                            {formatDetails(event.details) && (
                              <p className="text-xs text-muted-foreground mt-1 truncate max-w-md">
                                {formatDetails(event.details)}
                              </p>
                            )}
                          </div>
                          <Badge
                            className={`flex-shrink-0 ${EVENT_BADGES[event.event_type] || "bg-slate-50 text-slate-700 border-slate-200"}`}
                          >
                            {formatEventType(event.event_type)}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {new Date(event.timestamp).toLocaleTimeString()}
                        </p>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>

        {hasMore && !isLoading && (
          <div className="mt-6 text-center">
            <Button
              variant="outline"
              onClick={loadMore}
              disabled={isLoadingMore}
            >
              {isLoadingMore ? "Loading..." : `Load more (${items.length} of ${total})`}
            </Button>
          </div>
        )}

        {!isLoading && items.length === 0 && (
          <div className="text-center py-12">
            <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">No activity recorded yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
