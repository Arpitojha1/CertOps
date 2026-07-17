import { useEffect, useState } from "react";
import { getStatusLabel, getStatusColor } from "@/lib/mockData";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { ApiCert } from "@/pages/CertificatesPage";

interface RenewalLog {
  id: number;
  cert_id: string;
  event_type: string;
  timestamp: string;
  success: boolean | number;
  detail?: string;
  old_expiry?: string;
  new_expiry?: string;
}

export default function CertificateDetailModal({
  cert,
  onClose,
}: {
  cert: ApiCert;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [logs, setLogs] = useState<RenewalLog[]>([]);
  const [isConfirmingReload, setIsConfirmingReload] = useState(false);

  useEffect(() => {
    api
      .get<RenewalLog[]>(
        `/api/renewal-log?cert_id=${encodeURIComponent(cert.name)}`
      )
      .then(res => setLogs(res.data))
      .catch(() => {});
  }, [cert.name]);

  const isHostCert = cert.source.connectorType === "host";
  const isPendingReload = cert.status === "deployed_pending_reload";

  const handleConfirmReload = async () => {
    setIsConfirmingReload(true);
    try {
      await api.post("/api/host/confirm-reload", {
        connector_name: cert.vaultSource,
        cert_id: cert.name,
      });
      toast.success(`Reload confirmed for ${cert.domain}`);
      onClose();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Reload failed.");
      setIsConfirmingReload(false);
    }
  };

  const hasEvent = (type: string) =>
    logs.some(l => l.event_type === type && Boolean(l.success));

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-mono">{cert.domain}</DialogTitle>
          <DialogDescription>{cert.source.connectorName}</DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Metadata */}
          <div className="grid grid-cols-2 gap-4">
            <Card className="p-4 bg-muted/50">
              <p className="text-xs text-muted-foreground mb-1">Status</p>
              <Badge className={getStatusColor(cert.status as any)}>
                {getStatusLabel(cert.status as any)}
              </Badge>
            </Card>
            <Card className="p-4 bg-muted/50">
              <p className="text-xs text-muted-foreground mb-1">
                Days remaining
              </p>
              <p className="text-2xl font-bold text-foreground">
                {Math.round(cert.daysRemaining)}d
              </p>
            </Card>
            <Card className="p-4 bg-muted/50">
              <p className="text-xs text-muted-foreground mb-1">Expiry date</p>
              <p className="font-mono text-sm">
                {new Date(cert.expiryDate).toLocaleDateString()}
              </p>
            </Card>
            <Card className="p-4 bg-muted/50">
              <p className="text-xs text-muted-foreground mb-1">
                Next renewal scheduled
              </p>
              <p className="font-mono text-sm">
                {cert.nextRenewalAt
                  ? new Date(cert.nextRenewalAt).toLocaleDateString()
                  : "—"}
              </p>
            </Card>
            {cert.group && (
              <Card className="p-4 bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">Group</p>
                <p className="text-sm">{cert.group}</p>
              </Card>
            )}
            {cert.renewalThresholdDays != null && (
              <Card className="p-4 bg-muted/50">
                <p className="text-xs text-muted-foreground mb-1">
                  Renewal threshold
                </p>
                <p className="font-mono text-sm">
                  {cert.renewalThresholdDays}d
                </p>
              </Card>
            )}
          </div>

          {/* Host cert pipeline */}
          {isHostCert && (
            <div className="border-t pt-6">
              <h3 className="font-semibold text-foreground mb-4">
                Renewal Pipeline
              </h3>
              <div className="flex gap-4 mb-4">
                {[
                  { label: "Renewed", type: "renewal_started" },
                  { label: "Deployed", type: "deployed" },
                  { label: "Reload", type: "reload_confirmed" },
                ].map((step, i, arr) => (
                  <>
                    <div
                      key={step.label}
                      className="flex flex-col items-center"
                    >
                      <div
                        className={`w-10 h-10 rounded-full flex items-center justify-center ${
                          hasEvent(step.type)
                            ? "bg-green-100"
                            : isPendingReload && i === 2
                              ? "bg-amber-100"
                              : "bg-gray-100"
                        }`}
                      >
                        {hasEvent(step.type) ? (
                          <CheckCircle2 className="w-6 h-6 text-green-600" />
                        ) : isPendingReload && i === 2 ? (
                          <Clock className="w-6 h-6 text-amber-600" />
                        ) : (
                          <AlertCircle className="w-6 h-6 text-gray-400" />
                        )}
                      </div>
                      <p className="text-xs font-semibold mt-2 text-center">
                        {step.label}
                      </p>
                    </div>
                    {i < arr.length - 1 && (
                      <div
                        key={`connector-${i}`}
                        className="flex-1 flex items-center"
                      >
                        <div className="h-1 w-full bg-gray-200" />
                      </div>
                    )}
                  </>
                ))}
              </div>

              {isPendingReload && isAdmin && (
                <Button
                  onClick={handleConfirmReload}
                  disabled={isConfirmingReload}
                  className="w-full bg-amber-600 hover:bg-amber-700"
                >
                  {isConfirmingReload ? "Confirming…" : "Confirm Reload"}
                </Button>
              )}
              {isPendingReload && !isAdmin && (
                <p className="text-xs text-muted-foreground text-center">
                  Admin access required to confirm reload.
                </p>
              )}
            </div>
          )}

          {/* Renewal log */}
          <div className="border-t pt-6">
            <h3 className="font-semibold text-foreground mb-4">
              Renewal History
            </h3>
            {logs.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No renewal history yet.
              </p>
            ) : (
              <div className="space-y-3 max-h-48 overflow-y-auto">
                {[...logs].reverse().map(log => (
                  <div key={log.id} className="flex gap-4 text-sm">
                    <div className="w-32 text-muted-foreground shrink-0 font-mono text-xs">
                      {new Date(log.timestamp).toLocaleString()}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-foreground capitalize">
                          {log.event_type.replace(/_/g, " ")}
                        </p>
                        {!log.success && (
                          <Badge className="bg-red-50 text-red-700 border-red-200 text-xs">
                            failed
                          </Badge>
                        )}
                      </div>
                      {log.detail && (
                        <p className="text-xs text-muted-foreground">
                          {log.detail}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
