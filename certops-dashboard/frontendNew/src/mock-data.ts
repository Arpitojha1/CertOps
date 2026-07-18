import { Certificate, Connector, EventLog, GroupPolicy, NotificationPolicy, ScheduledJob, ChartDataPoint } from "./types";

export const MOCK_CERTIFICATES: Certificate[] = [
  { id: "cert-1", domain: "api.certops.io", connector: "AWS Secrets Manager", ca: "Let's Encrypt", expiryDate: "2026-10-15", daysRemaining: 91, status: "Active", group: "Production API" },
  { id: "cert-2", domain: "auth.certops.io", connector: "HashiCorp Vault", ca: "DigiCert", expiryDate: "2026-08-01", daysRemaining: 16, status: "Expiring Soon", group: "Production API" },
  { id: "cert-3", domain: "dev.certops.io", connector: "Kubernetes Secret", ca: "Let's Encrypt", expiryDate: "2026-07-10", daysRemaining: -6, status: "Expired", group: "Development" },
  { id: "cert-4", domain: "metrics.certops.io", connector: "AWS Secrets Manager", ca: "Let's Encrypt", expiryDate: "2026-12-01", daysRemaining: 138, status: "Active", group: "Internal" },
  { id: "cert-5", domain: "staging.certops.io", connector: "Azure Key Vault", ca: "GlobalSign", expiryDate: "2026-07-25", daysRemaining: 9, status: "Expiring Soon", group: "Staging" },
  { id: "cert-6", domain: "legacy.certops.io", connector: "Manual", ca: "Symantec", expiryDate: "2026-05-15", daysRemaining: -62, status: "Revoked", group: "Legacy" },
  { id: "cert-7", domain: "vpn.certops.io", connector: "HashiCorp Vault", ca: "DigiCert", expiryDate: "2027-01-20", daysRemaining: 188, status: "Active", group: "Network" },
];

export const MOCK_CONNECTORS: Connector[] = [
  { id: "conn-1", name: "AWS Production (us-east-1)", category: "Secret Store", renewalThreshold: 30, status: "Connected" },
  { id: "conn-2", name: "Vault Primary", category: "Secret Store", renewalThreshold: 15, status: "Connected" },
  { id: "conn-3", name: "Azure Staging", category: "Secret Store", renewalThreshold: 30, status: "Error" },
  { id: "conn-4", name: "Let's Encrypt Prod", category: "Certificate Authority", renewalThreshold: 30, status: "Connected" },
  { id: "conn-5", name: "DigiCert Enterprise", category: "Certificate Authority", renewalThreshold: 45, status: "Connected" },
  { id: "conn-6", name: "NGINX Load Balancers", category: "Host", renewalThreshold: 14, status: "Pending" },
];

export const MOCK_EVENTS: EventLog[] = [
  { id: "evt-1", type: "Renewal", description: "Successfully renewed api.certops.io", timestamp: "2026-07-16T08:15:00Z", status: "Success" },
  { id: "evt-2", type: "Failure", description: "Failed to renew auth.certops.io - ACME challenge failed", timestamp: "2026-07-15T23:30:00Z", status: "Failed" },
  { id: "evt-3", type: "Config", description: "Updated Vault Primary connector credentials", timestamp: "2026-07-15T14:22:00Z", status: "Info" },
  { id: "evt-4", type: "Login", description: "Admin user logged in", timestamp: "2026-07-15T09:00:00Z", status: "Info" },
  { id: "evt-5", type: "Renewal", description: "Successfully renewed vpn.certops.io", timestamp: "2026-07-14T11:45:00Z", status: "Success" },
];

export const MOCK_GROUPS: GroupPolicy[] = [
  { id: "grp-1", name: "Production API", maintenanceWindow: "Sun 02:00-04:00 UTC", notificationPolicy: "High Priority Alerting" },
  { id: "grp-2", name: "Development", maintenanceWindow: "Anytime", notificationPolicy: "Standard Email" },
  { id: "grp-3", name: "Network", maintenanceWindow: "Sat 00:00-02:00 UTC", notificationPolicy: "High Priority Alerting" },
];

export const MOCK_NOTIFICATIONS: NotificationPolicy[] = [
  { id: "notif-1", group: "Production API", threshold: "30 days, 15 days, 7 days", channel: "Slack (#ops-alerts), Email", status: "Active" },
  { id: "notif-2", group: "Development", threshold: "15 days", channel: "Email", status: "Active" },
  { id: "notif-3", group: "Network", threshold: "45 days, 30 days, 15 days", channel: "PagerDuty", status: "Active" },
];

export const MOCK_JOBS: ScheduledJob[] = [
  { id: "job-1", name: "Renew Expiring (Production API)", target: "auth.certops.io", nextRun: "2026-07-16T12:00:00Z", status: "Scheduled" },
  { id: "job-2", name: "Sync AWS Secrets", target: "AWS Production (us-east-1)", nextRun: "2026-07-16T10:00:00Z", status: "Running" },
  { id: "job-3", name: "Renew Expiring (Staging)", target: "staging.certops.io", nextRun: "2026-07-17T02:00:00Z", status: "Scheduled" },
];

export const MOCK_CHART_CA_BREAKDOWN: ChartDataPoint[] = [
  { name: "Let's Encrypt", value: 450 },
  { name: "DigiCert", value: 120 },
  { name: "GlobalSign", value: 80 },
  { name: "Internal PKI", value: 200 },
];

export const MOCK_CHART_MONTHLY_VOLUME = [
  { month: "Jan", issued: 45, expired: 12 },
  { month: "Feb", issued: 52, expired: 18 },
  { month: "Mar", issued: 38, expired: 25 },
  { month: "Apr", issued: 65, expired: 15 },
  { month: "May", issued: 48, expired: 30 },
  { month: "Jun", issued: 75, expired: 22 },
  { month: "Jul", issued: 90, expired: 10 },
];

// --- MOCK PRICING DATA LAYER ---
// Note: Real payment-provider integration (e.g. Stripe) is a hard blocker before this app can accept real users. This must NOT be silently treated as production-ready.

export const MOCK_PLANS = [
  { id: "Starter", name: "Starter", monthlyPrice: 49, annualPrice: 39, description: "Basic certificate management for small teams.", features: ["Up to 250 certificates", "Standard email notifications", "Basic Connectors", "Community Support"] },
  { id: "Professional", name: "Professional", monthlyPrice: 99, annualPrice: 79, description: "Advanced automation for growing infrastructure.", features: ["Unlimited certificates", "Priority Slack/PagerDuty", "All Connectors", "Priority Support"] },
  { id: "Enterprise", name: "Enterprise", monthlyPrice: 299, annualPrice: 249, description: "Full suite with advanced analytics and policy tools.", features: ["Everything in Pro", "Enterprise Dashboard", "Custom Policies", "24/7 Phone Support"] }
];

export function getPlans() {
  return MOCK_PLANS;
}

export async function subscribeToPlan(planId: string) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({ success: true, plan: planId });
    }, 1500);
  });
}
