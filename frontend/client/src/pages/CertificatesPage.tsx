import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search, Shield, Server, AlertCircle } from "lucide-react";
import api from "@/lib/api";
import {
  getStatusLabel,
  getStatusColor,
  getDaysRemainingColor,
} from "@/lib/mockData";
import CertificateDetailModal from "@/components/CertificateDetailModal";

export interface ApiCert {
  id: string;
  vaultSource: string;
  name: string;
  domain: string;
  source: { connectorId: string; connectorName: string; connectorType: string };
  expiryDate: string;
  daysRemaining: number;
  status: string;
  pipelineStage?: string;
  group?: string;
  groupId?: number;
  renewalThresholdDays?: number;
  nextRenewalAt?: string;
}

export default function CertificatesPage() {
  const [certs, setCerts] = useState<ApiCert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedCert, setSelectedCert] = useState<ApiCert | null>(null);

  useEffect(() => {
    api
      .get<ApiCert[]>("/api/certificates")
      .then(res => setCerts(res.data))
      .catch(() => setError("Failed to load certificates."))
      .finally(() => setIsLoading(false));
  }, []);

  const filtered = certs.filter(cert => {
    const matchesSearch =
      cert.domain.toLowerCase().includes(searchTerm.toLowerCase()) ||
      cert.source.connectorName
        .toLowerCase()
        .includes(searchTerm.toLowerCase());
    const matchesStatus =
      statusFilter === "all" || cert.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const stats = {
    total: certs.length,
    healthy: certs.filter(c => c.status === "healthy").length,
    dueSoon: certs.filter(c => c.status === "due_soon").length,
    overdue: certs.filter(c => c.status === "overdue").length,
    pendingReload: certs.filter(c => c.status === "deployed_pending_reload")
      .length,
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto p-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">
            Certificates
          </h1>
          <p className="text-muted-foreground">
            Manage and monitor all certificates across your infrastructure
          </p>
        </div>

        {isLoading && <p className="text-muted-foreground mb-4">Loading…</p>}
        {error && <p className="text-red-600 mb-4">{error}</p>}

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
          <div className="bg-card border border-border rounded-md p-4">
            <p className="text-xs text-muted-foreground mb-1">Total</p>
            <p className="text-2xl font-bold font-mono text-foreground">
              {stats.total}
            </p>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-md p-4">
            <p className="text-xs text-green-700 mb-1">Healthy</p>
            <p className="text-2xl font-bold font-mono text-green-700">
              {stats.healthy}
            </p>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-md p-4">
            <p className="text-xs text-amber-700 mb-1">Due soon</p>
            <p className="text-2xl font-bold font-mono text-amber-700">
              {stats.dueSoon}
            </p>
          </div>
          <div className="bg-red-50 border border-red-200 rounded-md p-4">
            <p className="text-xs text-red-700 mb-1">Overdue</p>
            <p className="text-2xl font-bold font-mono text-red-700">
              {stats.overdue}
            </p>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-md p-4">
            <p className="text-xs text-slate-700 mb-1">Pending reload</p>
            <p className="text-2xl font-bold font-mono text-slate-700">
              {stats.pendingReload}
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-col md:flex-row gap-4 mb-6">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search domains or connectors…"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-full md:w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="healthy">Healthy</SelectItem>
              <SelectItem value="due_soon">Due soon</SelectItem>
              <SelectItem value="overdue">Overdue</SelectItem>
              <SelectItem value="renewed">Renewed</SelectItem>
              <SelectItem value="deployed_pending_reload">
                Pending reload
              </SelectItem>
              <SelectItem value="reload_confirmed">Reload confirmed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-muted border-b border-border">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-semibold text-foreground">
                  Domain
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-foreground">
                  Source
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-foreground">
                  Expiry
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-foreground">
                  Days left
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-foreground">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-foreground">
                  Group
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold text-foreground">
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(cert => (
                <tr
                  key={cert.id}
                  className="border-b border-border hover:bg-muted/50 transition-colors cursor-pointer"
                  onClick={() => setSelectedCert(cert)}
                >
                  <td className="px-6 py-4">
                    <p className="font-mono text-sm font-semibold text-foreground">
                      {cert.domain}
                    </p>
                    <p className="text-xs text-muted-foreground">{cert.name}</p>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      {cert.source.connectorType === "vault" ? (
                        <Shield className="w-4 h-4 text-slate-600" />
                      ) : (
                        <Server className="w-4 h-4 text-slate-600" />
                      )}
                      <span className="text-sm text-foreground">
                        {cert.source.connectorName}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <p className="font-mono text-sm text-foreground">
                      {new Date(cert.expiryDate).toLocaleDateString()}
                    </p>
                  </td>
                  <td className="px-6 py-4">
                    <p
                      className={`font-mono text-sm font-semibold ${getDaysRemainingColor(cert.daysRemaining)}`}
                    >
                      {Math.round(cert.daysRemaining)}d
                    </p>
                  </td>
                  <td className="px-6 py-4">
                    <Badge className={getStatusColor(cert.status as any)}>
                      {getStatusLabel(cert.status as any)}
                    </Badge>
                  </td>
                  <td className="px-6 py-4">
                    {cert.group ? (
                      <span className="text-xs text-muted-foreground font-mono">
                        {cert.group}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={e => {
                        e.stopPropagation();
                        setSelectedCert(cert);
                      }}
                    >
                      View
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!isLoading && filtered.length === 0 && (
          <div className="text-center py-12">
            <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              {certs.length === 0
                ? "No certificates tracked yet."
                : "No certificates match your filters."}
            </p>
          </div>
        )}
      </div>

      {selectedCert && (
        <CertificateDetailModal
          cert={selectedCert}
          onClose={() => setSelectedCert(null)}
        />
      )}
    </div>
  );
}
