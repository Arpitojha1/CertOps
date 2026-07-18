export type CertStatus = "Active" | "Expiring Soon" | "Revoked" | "Expired" | "Pending";

export interface Certificate {
  id: string;
  domain: string;
  connector: string;
  ca: string;
  expiryDate: string;
  daysRemaining: number;
  status: CertStatus;
  group: string;
}

export interface EntCertificate extends Certificate {
  type: "Server" | "Client";
  owner: string;
}

export interface Connector {
  id: string;
  name: string;
  category: "Secret Store" | "Host" | "Certificate Authority";
  renewalThreshold: number;
  status: "Connected" | "Error" | "Pending";
}

export interface EventLog {
  id: string;
  type: "Renewal" | "Failure" | "Config" | "Login" | "Discovery" | "Revocation" | "Issuance";
  description: string;
  timestamp: string;
  status: "Success" | "Failed" | "Info";
}

export interface GroupPolicy {
  id: string;
  name: string;
  maintenanceWindow: string;
  notificationPolicy: string;
}

export interface NotificationPolicy {
  id: string;
  group: string;
  threshold: string;
  channel: string;
  status: "Active" | "Disabled";
}

export interface ScheduledJob {
  id: string;
  name: string;
  target: string;
  nextRun: string;
  status: "Scheduled" | "Running" | "Failed";
}

export interface ChartDataPoint {
  name: string;
  value: number;
}

export interface DiscoveryRule {
  id: string;
  name: string;
  target: string;
  schedule: string;
  status: "Active" | "Disabled";
}

export interface DiscoveryJob {
  id: string;
  name: string;
  type: "On Demand" | "Scheduled";
  nextRun?: string;
  lastRun?: string;
  status: "Idle" | "Running" | "Scheduled";
}

export interface ExcludedCert {
  id: string;
  domain: string;
  reason: string;
  dateExcluded: string;
}

export interface NetworkRange {
  id: string;
  cidr: string;
  description: string;
  lastScan: string;
  status: "Scanned" | "Pending" | "Error";
}

export interface CAPolicy {
  id: string;
  group: string;
  allowedCAs: string[];
  renewalThreshold: number;
  autoRenew: boolean;
}

export interface CAHealth {
  id: string;
  name: string;
  uptime: number;
  lastIssuance: string;
  errorRate: number;
  status: "Healthy" | "Degraded" | "Down";
}

export interface TimeSeriesDataPoint {
  timestamp: string;
  value: number;
  [key: string]: any;
}
