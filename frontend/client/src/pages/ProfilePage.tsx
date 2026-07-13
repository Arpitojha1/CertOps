import { connectors } from "@/lib/mockData";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Database, Server, AlertCircle, CheckCircle2 } from "lucide-react";

export default function ProfilePage() {
  const { user } = useAuth();

  const secretStores = connectors.filter(c => c.category === "secret_store");
  const hosts = connectors.filter(c => c.category === "host");

  // IMPORTANT: This page shows status only — NEVER raw secret values or env var contents
  const mockEnvVars = [
    { name: "VAULT_ADDR", configured: true },
    { name: "AZURE_SUBSCRIPTION_ID", configured: true },
    { name: "RENEWAL_WEBHOOK_URL", configured: false },
    { name: "SLACK_WEBHOOK", configured: true },
  ];

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto p-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">Profile</h1>
          <p className="text-muted-foreground">
            Your account and access inventory
          </p>
        </div>

        {/* User info */}
        <Card className="p-6 mb-8">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-slate-200 flex items-center justify-center text-lg font-semibold text-slate-700">
              {user?.email.charAt(0).toUpperCase()}
            </div>
            <div>
              <p className="font-semibold text-foreground">
                {user?.email.split("@")[0]}
              </p>
              <p className="text-sm text-muted-foreground">{user?.email}</p>
            </div>
          </div>
        </Card>

        {/* Secret Stores */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold text-foreground mb-4 flex items-center gap-2">
            <Database className="w-5 h-5" />
            Secret Stores
          </h2>
          <div className="space-y-4">
            {secretStores.map(connector => (
              <Card key={connector.id} className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className="font-semibold text-foreground">
                      {connector.name}
                    </p>
                    <p className="text-xs text-muted-foreground font-mono mt-1 break-all">
                      {connector.url}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground mb-1">
                        Status
                      </p>
                      <Badge
                        className={
                          connector.status === "healthy"
                            ? "bg-green-50 text-green-700 border-green-200"
                            : "bg-red-50 text-red-700 border-red-200"
                        }
                      >
                        {connector.status === "healthy" ? (
                          <>
                            <CheckCircle2 className="w-3 h-3 mr-1" />
                            Healthy
                          </>
                        ) : (
                          <>
                            <AlertCircle className="w-3 h-3 mr-1" />
                            Unreachable
                          </>
                        )}
                      </Badge>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground mb-1">
                        Certificates
                      </p>
                      <p className="font-mono font-semibold text-foreground">
                        {connector.certCount}
                      </p>
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* Hosts */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold text-foreground mb-4 flex items-center gap-2">
            <Server className="w-5 h-5" />
            Hosts
          </h2>
          <div className="space-y-4">
            {hosts.map(connector => (
              <Card key={connector.id} className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className="font-semibold text-foreground">
                      {connector.name}
                    </p>
                    <p className="text-xs text-muted-foreground font-mono mt-1 break-all">
                      {connector.hostname}
                    </p>
                    {connector.service && (
                      <p className="text-xs text-muted-foreground mt-2">
                        Service:{" "}
                        <span className="font-mono">{connector.service}</span>
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground mb-1">
                        Status
                      </p>
                      <Badge
                        className={
                          connector.status === "healthy"
                            ? "bg-green-50 text-green-700 border-green-200"
                            : "bg-red-50 text-red-700 border-red-200"
                        }
                      >
                        {connector.status === "healthy" ? (
                          <>
                            <CheckCircle2 className="w-3 h-3 mr-1" />
                            Healthy
                          </>
                        ) : (
                          <>
                            <AlertCircle className="w-3 h-3 mr-1" />
                            Unreachable
                          </>
                        )}
                      </Badge>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground mb-1">
                        Certificates
                      </p>
                      <p className="font-mono font-semibold text-foreground">
                        {connector.certCount}
                      </p>
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* Environment Variables */}
        <div>
          <h2 className="text-xl font-semibold text-foreground mb-4">
            Environment Variables
          </h2>
          <div className="space-y-2">
            {mockEnvVars.map(envVar => (
              <Card
                key={envVar.name}
                className="p-4 flex items-center justify-between"
              >
                <p className="font-mono text-sm text-foreground break-all">
                  {envVar.name}
                </p>
                <Badge
                  variant="outline"
                  className={
                    envVar.configured
                      ? "bg-green-50 text-green-700 border-green-200"
                      : "bg-gray-50 text-gray-700 border-gray-200"
                  }
                >
                  {envVar.configured ? "Configured" : "Not configured"}
                </Badge>
              </Card>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-4">
            ⓘ Environment variable values are never displayed for security
            reasons.
          </p>
        </div>
      </div>
    </div>
  );
}
