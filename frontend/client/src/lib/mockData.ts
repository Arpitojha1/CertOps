// Mock data for CertOps Dashboard
// Realistic certificate lifecycle data with mixed statuses

export type ConnectorType = "vault" | "host";
export type ConnectorCategory = "secret_store" | "host";
export type CertStatus =
  | "healthy"
  | "due_soon"
  | "overdue"
  | "renewed"
  | "deployed_pending_reload"
  | "reload_confirmed";
export type ServiceType = "nginx" | "iis" | "apache" | "custom";

export interface Connector {
  id: string;
  name: string;
  type: ConnectorType;
  category: ConnectorCategory;
  status: "healthy" | "unreachable";
  certCount: number;
  url?: string;
  hostname?: string;
  service?: ServiceType;
  lastSync?: string;
}

export interface Certificate {
  id: string;
  domain: string;
  source: {
    connectorId: string;
    connectorName: string;
    connectorType: ConnectorType;
  };
  expiryDate: string;
  issuedDate: string;
  daysRemaining: number;
  status: CertStatus;
  serviceToReload?: ServiceType;
  renewalHistory: RenewalEvent[];
  group?: string;
  issuer: string;
}

export interface RenewalEvent {
  id: string;
  timestamp: string;
  action: "renewed" | "deployed" | "reload_confirmed" | "failed";
  details: string;
  certId: string;
}

export interface Group {
  id: string;
  name: string;
  certIds: string[];
  renewalThreshold: number; // days before expiry
  notificationThreshold: number; // days before expiry
}

// Connectors
export const connectors: Connector[] = [
  {
    id: "vault-prod",
    name: "HashiCorp Vault (Production)",
    type: "vault",
    category: "secret_store",
    status: "healthy",
    certCount: 12,
    url: "https://vault.prod.internal:8200",
    lastSync: "2026-07-10T15:32:00Z",
  },
  {
    id: "vault-staging",
    name: "HashiCorp Vault (Staging)",
    type: "vault",
    category: "secret_store",
    status: "healthy",
    certCount: 8,
    url: "https://vault.staging.internal:8200",
    lastSync: "2026-07-10T15:35:00Z",
  },
  {
    id: "azure-keyvault",
    name: "Azure Key Vault",
    type: "vault",
    category: "secret_store",
    status: "healthy",
    certCount: 5,
    url: "https://certops-kv.vault.azure.net/",
    lastSync: "2026-07-10T15:28:00Z",
  },
  {
    id: "host-prod-web-1",
    name: "prod-web-1",
    type: "host",
    category: "host",
    status: "healthy",
    certCount: 3,
    hostname: "prod-web-1.internal",
    service: "nginx",
    lastSync: "2026-07-10T15:40:00Z",
  },
  {
    id: "host-prod-web-2",
    name: "prod-web-2",
    type: "host",
    category: "host",
    status: "healthy",
    certCount: 3,
    hostname: "prod-web-2.internal",
    service: "nginx",
    lastSync: "2026-07-10T15:42:00Z",
  },
  {
    id: "host-prod-api",
    name: "prod-api-1",
    type: "host",
    category: "host",
    status: "unreachable",
    certCount: 2,
    hostname: "prod-api-1.internal",
    service: "nginx",
    lastSync: "2026-07-09T22:15:00Z",
  },
];

// Certificates
export const certificates: Certificate[] = [
  // Vault certs - simple renewal pipeline
  {
    id: "cert-api-prod",
    domain: "api.prod.example.com",
    source: {
      connectorId: "vault-prod",
      connectorName: "HashiCorp Vault (Production)",
      connectorType: "vault",
    },
    expiryDate: "2026-09-15T00:00:00Z",
    issuedDate: "2025-09-15T00:00:00Z",
    daysRemaining: 67,
    status: "healthy",
    issuer: "Let's Encrypt",
    renewalHistory: [
      {
        id: "renewal-1",
        timestamp: "2026-07-08T14:22:00Z",
        action: "renewed",
        details: "Renewed via ACME",
        certId: "cert-api-prod",
      },
      {
        id: "renewal-2",
        timestamp: "2026-07-08T14:23:00Z",
        action: "deployed",
        details: "Written back to Vault",
        certId: "cert-api-prod",
      },
    ],
    group: "production-api",
  },
  {
    id: "cert-web-prod",
    domain: "www.example.com",
    source: {
      connectorId: "vault-prod",
      connectorName: "HashiCorp Vault (Production)",
      connectorType: "vault",
    },
    expiryDate: "2026-08-20T00:00:00Z",
    issuedDate: "2025-08-20T00:00:00Z",
    daysRemaining: 41,
    status: "due_soon",
    issuer: "Let's Encrypt",
    renewalHistory: [
      {
        id: "renewal-3",
        timestamp: "2026-07-05T09:15:00Z",
        action: "renewed",
        details: "Renewed via ACME",
        certId: "cert-web-prod",
      },
      {
        id: "renewal-4",
        timestamp: "2026-07-05T09:16:00Z",
        action: "deployed",
        details: "Written back to Vault",
        certId: "cert-web-prod",
      },
    ],
    group: "production-web",
  },
  {
    id: "cert-internal-api",
    domain: "internal-api.example.com",
    source: {
      connectorId: "vault-prod",
      connectorName: "HashiCorp Vault (Production)",
      connectorType: "vault",
    },
    expiryDate: "2026-07-25T00:00:00Z",
    issuedDate: "2025-07-25T00:00:00Z",
    daysRemaining: 15,
    status: "due_soon",
    issuer: "Internal CA",
    renewalHistory: [],
    group: "production-api",
  },
  {
    id: "cert-cdn-prod",
    domain: "cdn.example.com",
    source: {
      connectorId: "vault-prod",
      connectorName: "HashiCorp Vault (Production)",
      connectorType: "vault",
    },
    expiryDate: "2026-07-12T00:00:00Z",
    issuedDate: "2025-07-12T00:00:00Z",
    daysRemaining: 2,
    status: "overdue",
    issuer: "Let's Encrypt",
    renewalHistory: [
      {
        id: "renewal-5",
        timestamp: "2026-07-10T10:00:00Z",
        action: "renewed",
        details: "Renewed via ACME",
        certId: "cert-cdn-prod",
      },
      {
        id: "renewal-6",
        timestamp: "2026-07-10T10:01:00Z",
        action: "deployed",
        details: "Written back to Vault",
        certId: "cert-cdn-prod",
      },
    ],
    group: "production-cdn",
  },
  {
    id: "cert-staging-api",
    domain: "api.staging.example.com",
    source: {
      connectorId: "vault-staging",
      connectorName: "HashiCorp Vault (Staging)",
      connectorType: "vault",
    },
    expiryDate: "2026-10-01T00:00:00Z",
    issuedDate: "2025-10-01T00:00:00Z",
    daysRemaining: 83,
    status: "healthy",
    issuer: "Let's Encrypt",
    renewalHistory: [],
    group: "staging",
  },
  {
    id: "cert-azure-app",
    domain: "app.azure.example.com",
    source: {
      connectorId: "azure-keyvault",
      connectorName: "Azure Key Vault",
      connectorType: "vault",
    },
    expiryDate: "2026-09-30T00:00:00Z",
    issuedDate: "2025-09-30T00:00:00Z",
    daysRemaining: 82,
    status: "healthy",
    issuer: "DigiCert",
    renewalHistory: [],
    group: "azure",
  },
  // Host certs - complex renewal pipeline with reload
  {
    id: "cert-web1-main",
    domain: "web1.prod.internal",
    source: {
      connectorId: "host-prod-web-1",
      connectorName: "prod-web-1",
      connectorType: "host",
    },
    expiryDate: "2026-09-10T00:00:00Z",
    issuedDate: "2025-09-10T00:00:00Z",
    daysRemaining: 62,
    status: "healthy",
    serviceToReload: "nginx",
    issuer: "Internal CA",
    renewalHistory: [],
    group: "production-web",
  },
  {
    id: "cert-web1-alt",
    domain: "*.prod.internal",
    source: {
      connectorId: "host-prod-web-1",
      connectorName: "prod-web-1",
      connectorType: "host",
    },
    expiryDate: "2026-08-15T00:00:00Z",
    issuedDate: "2025-08-15T00:00:00Z",
    daysRemaining: 36,
    status: "due_soon",
    serviceToReload: "nginx",
    issuer: "Internal CA",
    renewalHistory: [],
    group: "production-web",
  },
  {
    id: "cert-web2-main",
    domain: "web2.prod.internal",
    source: {
      connectorId: "host-prod-web-2",
      connectorName: "prod-web-2",
      connectorType: "host",
    },
    expiryDate: "2026-07-18T00:00:00Z",
    issuedDate: "2025-07-18T00:00:00Z",
    daysRemaining: 8,
    status: "due_soon",
    serviceToReload: "nginx",
    issuer: "Internal CA",
    renewalHistory: [],
    group: "production-web",
  },
  {
    id: "cert-web2-renewed",
    domain: "api-gateway.prod.internal",
    source: {
      connectorId: "host-prod-web-2",
      connectorName: "prod-web-2",
      connectorType: "host",
    },
    expiryDate: "2026-09-20T00:00:00Z",
    issuedDate: "2025-09-20T00:00:00Z",
    daysRemaining: 72,
    status: "deployed_pending_reload",
    serviceToReload: "nginx",
    issuer: "Internal CA",
    renewalHistory: [
      {
        id: "renewal-7",
        timestamp: "2026-07-10T12:00:00Z",
        action: "renewed",
        details: "Renewed via Internal CA",
        certId: "cert-web2-renewed",
      },
      {
        id: "renewal-8",
        timestamp: "2026-07-10T12:01:00Z",
        action: "deployed",
        details: "Deployed to /etc/nginx/certs/",
        certId: "cert-web2-renewed",
      },
    ],
    group: "production-web",
  },
  {
    id: "cert-api-renewed",
    domain: "api.prod.internal",
    source: {
      connectorId: "host-prod-api",
      connectorName: "prod-api-1",
      connectorType: "host",
    },
    expiryDate: "2026-09-05T00:00:00Z",
    issuedDate: "2025-09-05T00:00:00Z",
    daysRemaining: 57,
    status: "reload_confirmed",
    serviceToReload: "nginx",
    issuer: "Internal CA",
    renewalHistory: [
      {
        id: "renewal-9",
        timestamp: "2026-07-08T14:30:00Z",
        action: "renewed",
        details: "Renewed via Internal CA",
        certId: "cert-api-renewed",
      },
      {
        id: "renewal-10",
        timestamp: "2026-07-08T14:31:00Z",
        action: "deployed",
        details: "Deployed to /etc/nginx/certs/",
        certId: "cert-api-renewed",
      },
      {
        id: "renewal-11",
        timestamp: "2026-07-09T08:15:00Z",
        action: "reload_confirmed",
        details: "nginx reloaded successfully",
        certId: "cert-api-renewed",
      },
    ],
    group: "production-api",
  },
];

// Groups
export const groups: Group[] = [
  {
    id: "group-prod-api",
    name: "production-api",
    certIds: ["cert-api-prod", "cert-internal-api", "cert-api-renewed"],
    renewalThreshold: 30,
    notificationThreshold: 45,
  },
  {
    id: "group-prod-web",
    name: "production-web",
    certIds: [
      "cert-web-prod",
      "cert-web1-main",
      "cert-web1-alt",
      "cert-web2-main",
      "cert-web2-renewed",
    ],
    renewalThreshold: 30,
    notificationThreshold: 45,
  },
  {
    id: "group-prod-cdn",
    name: "production-cdn",
    certIds: ["cert-cdn-prod"],
    renewalThreshold: 14,
    notificationThreshold: 21,
  },
  {
    id: "group-staging",
    name: "staging",
    certIds: ["cert-staging-api"],
    renewalThreshold: 30,
    notificationThreshold: 45,
  },
  {
    id: "group-azure",
    name: "azure",
    certIds: ["cert-azure-app"],
    renewalThreshold: 45,
    notificationThreshold: 60,
  },
];

// Activity log - recent renewal events
export const activityLog: RenewalEvent[] = [
  {
    id: "event-1",
    timestamp: "2026-07-10T15:45:00Z",
    action: "renewed",
    details: "api.prod.example.com renewed via ACME",
    certId: "cert-api-prod",
  },
  {
    id: "event-2",
    timestamp: "2026-07-10T15:46:00Z",
    action: "deployed",
    details: "api.prod.example.com deployed to Vault",
    certId: "cert-api-prod",
  },
  {
    id: "event-3",
    timestamp: "2026-07-10T14:20:00Z",
    action: "renewed",
    details: "api-gateway.prod.internal renewed via Internal CA",
    certId: "cert-web2-renewed",
  },
  {
    id: "event-4",
    timestamp: "2026-07-10T14:21:00Z",
    action: "deployed",
    details: "api-gateway.prod.internal deployed to prod-web-2",
    certId: "cert-web2-renewed",
  },
  {
    id: "event-5",
    timestamp: "2026-07-09T08:15:00Z",
    action: "reload_confirmed",
    details: "nginx reloaded on prod-api-1 for api.prod.internal",
    certId: "cert-api-renewed",
  },
  {
    id: "event-6",
    timestamp: "2026-07-08T14:22:00Z",
    action: "renewed",
    details: "api.prod.example.com renewed via ACME",
    certId: "cert-api-prod",
  },
  {
    id: "event-7",
    timestamp: "2026-07-05T09:15:00Z",
    action: "renewed",
    details: "www.example.com renewed via ACME",
    certId: "cert-web-prod",
  },
];

// Helper functions
export function getCertificatesByConnector(connectorId: string): Certificate[] {
  return certificates.filter(cert => cert.source.connectorId === connectorId);
}

export function getConnectorById(id: string): Connector | undefined {
  return connectors.find(c => c.id === id);
}

export function getCertificateById(id: string): Certificate | undefined {
  return certificates.find(c => c.id === id);
}

export function getGroupById(id: string): Group | undefined {
  return groups.find(g => g.id === id);
}

export function getStatusColor(status: CertStatus): string {
  switch (status) {
    case "healthy":
      return "bg-green-50 text-green-700 border-green-200";
    case "due_soon":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "overdue":
      return "bg-red-50 text-red-700 border-red-200";
    case "renewed":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "deployed_pending_reload":
      return "bg-slate-50 text-slate-700 border-slate-200";
    case "reload_confirmed":
      return "bg-green-50 text-green-700 border-green-200";
    default:
      return "bg-gray-50 text-gray-700 border-gray-200";
  }
}

export function getStatusLabel(status: CertStatus): string {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "due_soon":
      return "Due soon";
    case "overdue":
      return "Overdue";
    case "renewed":
      return "Renewed";
    case "deployed_pending_reload":
      return "Pending reload";
    case "reload_confirmed":
      return "Reload confirmed";
    default:
      return "Unknown";
  }
}

export function getDaysRemainingColor(daysRemaining: number): string {
  if (daysRemaining > 30) return "text-green-700";
  if (daysRemaining > 7) return "text-amber-700";
  return "text-red-700";
}
