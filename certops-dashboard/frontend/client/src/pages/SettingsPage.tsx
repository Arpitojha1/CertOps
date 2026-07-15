import { useState } from "react";
import { groups as initialGroups } from "@/lib/mockData";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Settings, Save } from "lucide-react";
import { toast } from "sonner";

export default function SettingsPage() {
  const [groups, setGroups] = useState(initialGroups);
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);

  const handleThresholdChange = (
    groupId: string,
    field: "renewalThreshold" | "notificationThreshold",
    value: number
  ) => {
    setGroups(
      groups.map(g => (g.id === groupId ? { ...g, [field]: value } : g))
    );
  };

  const handleSaveGroup = (groupId: string) => {
    toast.success("Group settings updated (local state only)");
    setEditingGroupId(null);
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto p-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-2">
            <Settings className="w-8 h-8" />
            Settings
          </h1>
          <p className="text-muted-foreground">
            Manage renewal policies and notification thresholds
          </p>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="policies" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="policies">Renewal Policies</TabsTrigger>
            <TabsTrigger value="notifications">Notifications</TabsTrigger>
          </TabsList>

          {/* Policies tab */}
          <TabsContent value="policies" className="space-y-6">
            <div className="text-sm text-muted-foreground mb-6">
              Edit renewal thresholds for each group. Certificates will be
              renewed when days remaining falls below this threshold.
            </div>

            <div className="space-y-4">
              {groups.map(group => (
                <Card key={group.id} className="p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="font-semibold text-foreground">
                        {group.name}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1">
                        {group.certIds.length} certificates
                      </p>
                    </div>
                    {editingGroupId === group.id ? (
                      <Button
                        size="sm"
                        onClick={() => handleSaveGroup(group.id)}
                        className="gap-2"
                      >
                        <Save className="w-4 h-4" />
                        Save
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingGroupId(group.id)}
                      >
                        Edit
                      </Button>
                    )}
                  </div>

                  {editingGroupId === group.id ? (
                    <div className="space-y-4">
                      <div>
                        <Label
                          htmlFor={`renewal-${group.id}`}
                          className="text-sm"
                        >
                          Renewal threshold (days)
                        </Label>
                        <Input
                          id={`renewal-${group.id}`}
                          type="number"
                          value={group.renewalThreshold}
                          onChange={e =>
                            handleThresholdChange(
                              group.id,
                              "renewalThreshold",
                              parseInt(e.target.value) || 0
                            )
                          }
                          className="mt-1"
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                          Renew when {group.renewalThreshold} days or fewer
                          remain
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-muted/50 rounded p-3">
                      <p className="text-xs text-muted-foreground mb-1">
                        Renewal threshold
                      </p>
                      <p className="font-mono font-semibold text-foreground">
                        {group.renewalThreshold} days
                      </p>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* Notifications tab */}
          <TabsContent value="notifications" className="space-y-6">
            <div className="text-sm text-muted-foreground mb-6">
              Edit notification thresholds for each group. You'll receive alerts
              when days remaining falls below this threshold.
            </div>

            <div className="space-y-4">
              {groups.map(group => (
                <Card key={group.id} className="p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="font-semibold text-foreground">
                        {group.name}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1">
                        {group.certIds.length} certificates
                      </p>
                    </div>
                    {editingGroupId === group.id ? (
                      <Button
                        size="sm"
                        onClick={() => handleSaveGroup(group.id)}
                        className="gap-2"
                      >
                        <Save className="w-4 h-4" />
                        Save
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingGroupId(group.id)}
                      >
                        Edit
                      </Button>
                    )}
                  </div>

                  {editingGroupId === group.id ? (
                    <div className="space-y-4">
                      <div>
                        <Label
                          htmlFor={`notification-${group.id}`}
                          className="text-sm"
                        >
                          Notification threshold (days)
                        </Label>
                        <Input
                          id={`notification-${group.id}`}
                          type="number"
                          value={group.notificationThreshold}
                          onChange={e =>
                            handleThresholdChange(
                              group.id,
                              "notificationThreshold",
                              parseInt(e.target.value) || 0
                            )
                          }
                          className="mt-1"
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                          Alert when {group.notificationThreshold} days or fewer
                          remain
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-muted/50 rounded p-3">
                      <p className="text-xs text-muted-foreground mb-1">
                        Notification threshold
                      </p>
                      <p className="font-mono font-semibold text-foreground">
                        {group.notificationThreshold} days
                      </p>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          </TabsContent>
        </Tabs>

        {/* Note */}
        <Card className="mt-8 p-4 bg-blue-50 border-blue-200">
          <p className="text-sm text-blue-900">
            ℹ️ Changes are stored in local state only. In a production
            environment, these settings would sync to your backend.
          </p>
        </Card>
      </div>
    </div>
  );
}
