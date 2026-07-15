import { useState, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, AlertCircle, Bell, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

interface Group {
  id: number;
  name: string;
}

interface NotificationPolicy {
  id: number;
  group_id: number;
  threshold_days: number;
}

interface NotificationLog {
  id: number;
  vault_source?: string;
  cert_id: string;
  policy_id: number;
  sent_at: string;
}

function AddPolicyDialog({
  groups,
  onCreated,
}: {
  groups: Group[];
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [groupId, setGroupId] = useState<string>("");
  const [threshold, setThreshold] = useState("");
  const [error, setError] = useState("");

  const submit = async () => {
    const days = parseFloat(threshold);
    if (!groupId) {
      setError("Select a group.");
      return;
    }
    if (isNaN(days) || days <= 0) {
      setError("Enter a positive number of days.");
      return;
    }
    try {
      await api.post("/api/notification-policies", {
        group_id: parseInt(groupId),
        threshold_days: days,
      });
      setOpen(false);
      setGroupId("");
      setThreshold("");
      setError("");
      onCreated();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to create policy.");
    }
  };

  return (
    <>
      <Button className="gap-2" onClick={() => setOpen(true)}>
        <Plus className="w-4 h-4" />
        New Policy
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Notification Policy</DialogTitle>
            <DialogDescription>
              Trigger a notification when a certificate in the selected group is
              within N days of expiry.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Group</Label>
              <Select value={groupId} onValueChange={setGroupId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a group" />
                </SelectTrigger>
                <SelectContent>
                  {groups.map(g => (
                    <SelectItem key={g.id} value={String(g.id)}>
                      {g.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Threshold (days before expiry)</Label>
              <Input
                type="number"
                placeholder="30"
                value={threshold}
                onChange={e => setThreshold(e.target.value)}
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button className="w-full" onClick={submit}>
              Create Policy
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function NotificationsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [groups, setGroups] = useState<Group[]>([]);
  const [policies, setPolicies] = useState<NotificationPolicy[]>([]);
  const [notifLog, setNotifLog] = useState<NotificationLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [g, p, n] = await Promise.all([
        api.get<Group[]>("/api/groups"),
        api.get<NotificationPolicy[]>("/api/notification-policies"),
        api.get<NotificationLog[]>("/api/notification-log"),
      ]);
      setGroups(g.data);
      setPolicies(p.data);
      setNotifLog(n.data.slice().reverse());
    } catch {
      setError("Failed to load notifications.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const deletePolicy = async (id: number) => {
    try {
      await api.delete(`/api/notification-policies/${id}`);
      load();
    } catch {
      /* ignore */
    }
  };

  const groupName = (gid: number) =>
    groups.find(g => g.id === gid)?.name ?? `Group ${gid}`;

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto p-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-foreground mb-2">
              Notifications
            </h1>
            <p className="text-muted-foreground">
              Notification policies and delivery history
            </p>
          </div>
          {isAdmin && <AddPolicyDialog groups={groups} onCreated={load} />}
        </div>

        {isLoading && <p className="text-muted-foreground">Loading…</p>}
        {error && <p className="text-red-600">{error}</p>}

        {/* Policies */}
        <section className="mb-10">
          <h2 className="text-lg font-semibold text-foreground mb-4">
            Policies
          </h2>
          {policies.length === 0 && !isLoading ? (
            <div className="text-center py-8 border border-dashed border-border rounded-lg">
              <Bell className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-muted-foreground text-sm">
                No notification policies yet.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {policies.map(p => (
                <Card
                  key={p.id}
                  className="p-4 flex items-center justify-between"
                >
                  <div className="flex items-center gap-4">
                    <Bell className="w-4 h-4 text-blue-600 shrink-0" />
                    <div>
                      <p className="text-sm font-semibold text-foreground">
                        {groupName(p.group_id)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Notify when ≤ {p.threshold_days} days remain
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge className="bg-blue-50 text-blue-700 border-blue-200">
                      {p.threshold_days}d threshold
                    </Badge>
                    {isAdmin && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        onClick={() => deletePolicy(p.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </section>

        {/* Notification history */}
        <section>
          <h2 className="text-lg font-semibold text-foreground mb-4">
            Notification History
          </h2>
          {notifLog.length === 0 && !isLoading ? (
            <div className="text-center py-8 border border-dashed border-border rounded-lg">
              <AlertCircle className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-muted-foreground text-sm">
                No notifications sent yet.
              </p>
            </div>
          ) : (
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
                      Policy
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-foreground">
                      Sent at
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {notifLog.map(n => {
                    const policy = policies.find(p => p.id === n.policy_id);
                    return (
                      <tr
                        key={n.id}
                        className="border-b border-border hover:bg-muted/50"
                      >
                        <td className="px-4 py-3 font-mono text-sm text-foreground">
                          {n.cert_id}
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {n.vault_source ?? "—"}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          {policy ? (
                            <span className="text-muted-foreground">
                              {groupName(policy.group_id)} —{" "}
                              {policy.threshold_days}d
                            </span>
                          ) : (
                            <span className="text-muted-foreground">
                              Policy #{n.policy_id}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground font-mono">
                          {new Date(n.sent_at).toLocaleString()}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
