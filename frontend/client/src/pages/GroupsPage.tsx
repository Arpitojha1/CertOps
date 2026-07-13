import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Clock,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

interface Group {
  id: number;
  name: string;
  description: string;
}

interface MaintenanceWindow {
  id: number;
  group_id: number;
  start_time: string;
  end_time: string;
  recurrence: string;
}

interface NotificationPolicy {
  id: number;
  group_id: number;
  threshold_days: number;
}

function CreateGroupDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const submit = async () => {
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    try {
      await api.post("/api/groups", {
        name: name.trim(),
        description: description.trim(),
      });
      setOpen(false);
      setName("");
      setDescription("");
      setError("");
      onCreated();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to create group.");
    }
  };

  return (
    <>
      <Button className="gap-2" onClick={() => setOpen(true)}>
        <Plus className="w-4 h-4" />
        New Group
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Group</DialogTitle>
            <DialogDescription>
              Group certificates to apply shared renewal and notification
              policies.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Group Name</Label>
              <Input
                placeholder="e.g. production-api"
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>
            <div>
              <Label>Description (optional)</Label>
              <Input
                placeholder="Brief description"
                value={description}
                onChange={e => setDescription(e.target.value)}
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button className="w-full" onClick={submit}>
              Create Group
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function AddWindowDialog({
  groupId,
  onCreated,
}: {
  groupId: number;
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [recurrence, setRecurrence] = useState("once");
  const [error, setError] = useState("");

  const submit = async () => {
    if (!start || !end) {
      setError("Start and end are required.");
      return;
    }
    try {
      await api.post("/api/maintenance-windows", {
        group_id: groupId,
        start_time: new Date(start).toISOString(),
        end_time: new Date(end).toISOString(),
        recurrence,
      });
      setOpen(false);
      setStart("");
      setEnd("");
      setError("");
      onCreated();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to create window.");
    }
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="gap-1"
        onClick={() => setOpen(true)}
      >
        <Plus className="w-3 h-3" />
        Window
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Maintenance Window</DialogTitle>
            <DialogDescription>
              Define when this group is allowed to receive deployments.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Start</Label>
              <Input
                type="datetime-local"
                value={start}
                onChange={e => setStart(e.target.value)}
              />
            </div>
            <div>
              <Label>End</Label>
              <Input
                type="datetime-local"
                value={end}
                onChange={e => setEnd(e.target.value)}
              />
            </div>
            <div>
              <Label>Recurrence</Label>
              <select
                className="w-full border border-border rounded-md p-2 text-sm bg-background"
                value={recurrence}
                onChange={e => setRecurrence(e.target.value)}
              >
                <option value="once">Once</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button className="w-full" onClick={submit}>
              Add Window
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function AddPolicyDialog({
  groupId,
  onCreated,
}: {
  groupId: number;
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [threshold, setThreshold] = useState("");
  const [error, setError] = useState("");

  const submit = async () => {
    const days = parseFloat(threshold);
    if (isNaN(days) || days <= 0) {
      setError("Enter a positive number.");
      return;
    }
    try {
      await api.post("/api/notification-policies", {
        group_id: groupId,
        threshold_days: days,
      });
      setOpen(false);
      setThreshold("");
      setError("");
      onCreated();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to create policy.");
    }
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="gap-1"
        onClick={() => setOpen(true)}
      >
        <Plus className="w-3 h-3" />
        Policy
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Notification Policy</DialogTitle>
            <DialogDescription>
              Notify when a certificate in this group is within N days of
              expiry.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
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
              Add Policy
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function GroupCard({
  group,
  windows,
  policies,
  isAdmin,
  onRefresh,
}: {
  group: Group;
  windows: MaintenanceWindow[];
  policies: NotificationPolicy[];
  isAdmin: boolean;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <button
          className="flex items-center gap-2 text-left"
          onClick={() => setExpanded(e => !e)}
        >
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
          <h2 className="text-lg font-semibold text-foreground">
            {group.name}
          </h2>
        </button>
        {isAdmin && (
          <div className="flex gap-2">
            <AddWindowDialog groupId={group.id} onCreated={onRefresh} />
            <AddPolicyDialog groupId={group.id} onCreated={onRefresh} />
          </div>
        )}
      </div>

      {group.description && (
        <p className="text-sm text-muted-foreground mb-4 ml-6">
          {group.description}
        </p>
      )}

      {expanded && (
        <div className="ml-6 space-y-4 mt-4">
          {/* Maintenance windows */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase mb-2">
              Maintenance Windows
            </p>
            {windows.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                None — deployments allowed anytime.
              </p>
            ) : (
              <div className="space-y-2">
                {windows.map(w => (
                  <div
                    key={w.id}
                    className="flex items-center gap-3 p-2 bg-muted/50 rounded border border-border text-sm"
                  >
                    <Clock className="w-4 h-4 text-slate-500 shrink-0" />
                    <span className="font-mono text-xs">
                      {new Date(w.start_time).toLocaleString()} →{" "}
                      {new Date(w.end_time).toLocaleString()}
                    </span>
                    <Badge variant="secondary" className="text-xs">
                      {w.recurrence}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Notification policies */}
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase mb-2">
              Notification Policies
            </p>
            {policies.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No notification policies.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {policies.map(p => (
                  <Badge
                    key={p.id}
                    className="bg-blue-50 text-blue-700 border-blue-200"
                  >
                    Notify at {p.threshold_days}d
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

export default function GroupsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [groups, setGroups] = useState<Group[]>([]);
  const [windows, setWindows] = useState<MaintenanceWindow[]>([]);
  const [policies, setPolicies] = useState<NotificationPolicy[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [g, w, p] = await Promise.all([
        api.get<Group[]>("/api/groups"),
        api.get<MaintenanceWindow[]>("/api/maintenance-windows"),
        api.get<NotificationPolicy[]>("/api/notification-policies"),
      ]);
      setGroups(g.data);
      setWindows(w.data);
      setPolicies(p.data);
    } catch {
      setError("Failed to load groups.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto p-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-foreground mb-2">
              Groups &amp; Policies
            </h1>
            <p className="text-muted-foreground">
              Organize certificates and set renewal / notification thresholds
            </p>
          </div>
          {isAdmin && <CreateGroupDialog onCreated={load} />}
        </div>

        {isLoading && <p className="text-muted-foreground">Loading…</p>}
        {error && <p className="text-red-600">{error}</p>}

        <div className="space-y-4">
          {groups.map(g => (
            <GroupCard
              key={g.id}
              group={g}
              windows={windows.filter(w => w.group_id === g.id)}
              policies={policies.filter(p => p.group_id === g.id)}
              isAdmin={isAdmin}
              onRefresh={load}
            />
          ))}
        </div>

        {!isLoading && groups.length === 0 && (
          <div className="text-center py-12">
            <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground mb-4">No groups yet.</p>
            {isAdmin && <CreateGroupDialog onCreated={load} />}
          </div>
        )}
      </div>
    </div>
  );
}
