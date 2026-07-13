import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowRight, AlertCircle, CheckCircle2, Clock } from "lucide-react";
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { getStatusColor, getStatusLabel } from "@/lib/mockData";

interface ApiCert {
  id: string;
  domain: string;
  source: { connectorId: string; connectorName: string; connectorType: string };
  expiryDate: string;
  daysRemaining: number;
  status: string;
  group?: string;
}

export default function DashboardHome() {
  const [certs, setCerts] = useState<ApiCert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<ApiCert[]>("/api/certificates")
      .then(res => setCerts(res.data))
      .catch(() => setError("Failed to load certificates."))
      .finally(() => setIsLoading(false));
  }, []);

  const stats = {
    total: certs.length,
    healthy: certs.filter(c => c.status === "healthy").length,
    dueSoon: certs.filter(c => c.status === "due_soon").length,
    overdue: certs.filter(c => c.status === "overdue").length,
    pendingReload: certs.filter(c => c.status === "deployed_pending_reload")
      .length,
  };

  // Derive connector stats from certificates
  const connectorMap = new Map<string, number>();
  certs.forEach(c => {
    connectorMap.set(
      c.source.connectorId,
      (connectorMap.get(c.source.connectorId) ?? 0) + 1
    );
  });
  const connectorCount = connectorMap.size;

  const recentCerts = certs.slice(0, 5);

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">Dashboard</h1>
          <p className="text-muted-foreground">
            Certificate lifecycle overview and quick access
          </p>
        </div>

        {isLoading && <p className="text-muted-foreground mb-8">Loading…</p>}
        {error && <p className="text-red-600 mb-8">{error}</p>}

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <Card className="p-4 bg-card border border-border">
            <p className="text-xs text-muted-foreground mb-1">Total Certs</p>
            <p className="text-2xl font-bold text-foreground">{stats.total}</p>
          </Card>
          <Card className="p-4 bg-green-50 border border-green-200">
            <p className="text-xs text-green-700 mb-1">Healthy</p>
            <p className="text-2xl font-bold text-green-700">{stats.healthy}</p>
          </Card>
          <Card className="p-4 bg-amber-50 border border-amber-200">
            <p className="text-xs text-amber-700 mb-1">Due soon</p>
            <p className="text-2xl font-bold text-amber-700">{stats.dueSoon}</p>
          </Card>
          <Card className="p-4 bg-red-50 border border-red-200">
            <p className="text-xs text-red-700 mb-1">Overdue</p>
            <p className="text-2xl font-bold text-red-700">{stats.overdue}</p>
          </Card>
          <Card className="p-4 bg-slate-50 border border-slate-200">
            <p className="text-xs text-slate-700 mb-1">Pending reload</p>
            <p className="text-2xl font-bold text-slate-700">
              {stats.pendingReload}
            </p>
          </Card>
        </div>

        {/* Second row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="p-6">
            <h3 className="font-semibold text-foreground mb-4">
              Connector Summary
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  Active connectors
                </span>
                <span className="font-mono font-semibold text-foreground">
                  {connectorCount}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  Total certs tracked
                </span>
                <span className="font-mono font-semibold text-foreground">
                  {stats.total}
                </span>
              </div>
            </div>
            <Link href="/connectors">
              <a>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full mt-4 gap-2"
                >
                  View Connectors
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </a>
            </Link>
          </Card>

          <Card className="p-6">
            <h3 className="font-semibold text-foreground mb-4">
              Quick Actions
            </h3>
            <div className="space-y-2">
              <Link href="/certificates">
                <a>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full justify-start gap-2"
                  >
                    <AlertCircle className="w-4 h-4" />
                    View all certs
                  </Button>
                </a>
              </Link>
              <Link href="/activity">
                <a>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full justify-start gap-2"
                  >
                    <Clock className="w-4 h-4" />
                    Activity log
                  </Button>
                </a>
              </Link>
              <Link href="/groups">
                <a>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full justify-start gap-2"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    Groups &amp; Policies
                  </Button>
                </a>
              </Link>
            </div>
          </Card>

          <Card className="p-6">
            <h3 className="font-semibold text-foreground mb-4">
              Status Summary
            </h3>
            <div className="space-y-2 text-sm">
              {stats.overdue > 0 && (
                <div className="flex items-center gap-2 p-2 bg-red-50 rounded border border-red-200">
                  <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                  <span className="text-red-700 font-semibold">
                    {stats.overdue} overdue
                  </span>
                </div>
              )}
              {stats.dueSoon > 0 && (
                <div className="flex items-center gap-2 p-2 bg-amber-50 rounded border border-amber-200">
                  <Clock className="w-4 h-4 text-amber-600 flex-shrink-0" />
                  <span className="text-amber-700 font-semibold">
                    {stats.dueSoon} due soon
                  </span>
                </div>
              )}
              {stats.pendingReload > 0 && (
                <div className="flex items-center gap-2 p-2 bg-slate-50 rounded border border-slate-200">
                  <AlertCircle className="w-4 h-4 text-slate-600 flex-shrink-0" />
                  <span className="text-slate-700 font-semibold">
                    {stats.pendingReload} pending reload
                  </span>
                </div>
              )}
              {!isLoading &&
                stats.overdue === 0 &&
                stats.dueSoon === 0 &&
                stats.pendingReload === 0 && (
                  <div className="flex items-center gap-2 p-2 bg-green-50 rounded border border-green-200">
                    <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0" />
                    <span className="text-green-700 font-semibold">
                      All clear
                    </span>
                  </div>
                )}
            </div>
          </Card>
        </div>

        {/* Recent certificates */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-foreground">
              Recent Certificates
            </h3>
            <Link href="/certificates">
              <a>
                <Button variant="ghost" size="sm">
                  View all
                </Button>
              </a>
            </Link>
          </div>

          {recentCerts.length === 0 && !isLoading && (
            <p className="text-sm text-muted-foreground">
              No certificates tracked yet.
            </p>
          )}

          <div className="space-y-3">
            {recentCerts.map(cert => (
              <div
                key={cert.id}
                className="flex items-center justify-between p-3 bg-muted/50 rounded border border-border"
              >
                <div>
                  <p className="font-mono text-sm font-semibold text-foreground">
                    {cert.domain}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {cert.source.connectorName}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-xs text-muted-foreground">
                    {Math.round(cert.daysRemaining)}d
                  </span>
                  <Badge className={getStatusColor(cert.status as any)}>
                    {getStatusLabel(cert.status as any)}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
