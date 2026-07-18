import { 
  EntCertificate, DiscoveryRule, DiscoveryJob, ExcludedCert, 
  NetworkRange, CAPolicy, CAHealth, TimeSeriesDataPoint 
} from "./types";
import { MOCK_CERTIFICATES } from "./mock-data";

export const MOCK_ENT_CERTIFICATES: EntCertificate[] = MOCK_CERTIFICATES.map((cert, i) => ({
  ...cert,
  type: i % 3 === 0 ? "Client" : "Server",
  owner: i % 2 === 0 ? "Platform Team" : "Security Team"
}));

export const MOCK_DISCOVERY_RULES: DiscoveryRule[] = [
  { id: "dr-1", name: "AWS Prod Scraper", target: "AWS (us-east-1)", schedule: "Daily at 00:00 UTC", status: "Active" },
  { id: "dr-2", name: "Internal Subnet Scan", target: "10.0.0.0/8", schedule: "Weekly on Sunday", status: "Active" },
  { id: "dr-3", name: "Azure Gateway", target: "Azure Sub 1", schedule: "Daily at 02:00 UTC", status: "Disabled" },
];

export const MOCK_DISCOVERY_JOBS: DiscoveryJob[] = [
  { id: "dj-1", name: "Manual Subnet Sweep", type: "On Demand", lastRun: "2026-07-16T08:00:00Z", status: "Idle" },
  { id: "dj-2", name: "AWS Prod Scraper", type: "Scheduled", nextRun: "2026-07-17T00:00:00Z", status: "Scheduled" },
  { id: "dj-3", name: "K8s Ingress Sync", type: "Scheduled", nextRun: "2026-07-16T12:00:00Z", status: "Running" },
];

export const MOCK_EXCLUDED_CERTS: ExcludedCert[] = [
  { id: "exc-1", domain: "test.certops.io", reason: "Short-lived ephemeral cert", dateExcluded: "2026-06-01" },
  { id: "exc-2", domain: "legacy-app.internal", reason: "Managed by third party", dateExcluded: "2026-05-15" },
];

export const MOCK_NETWORK_INVENTORY: NetworkRange[] = [
  { id: "net-1", cidr: "10.0.0.0/16", description: "Primary Datacenter", lastScan: "2026-07-15T00:00:00Z", status: "Scanned" },
  { id: "net-2", cidr: "172.16.0.0/12", description: "AWS VPC Peering", lastScan: "2026-07-16T02:00:00Z", status: "Pending" },
  { id: "net-3", cidr: "192.168.1.0/24", description: "Legacy Office Net", lastScan: "2026-07-10T00:00:00Z", status: "Error" },
];

export const MOCK_CA_POLICIES: CAPolicy[] = [
  { id: "cap-1", group: "Production API", allowedCAs: ["Let's Encrypt", "DigiCert"], renewalThreshold: 30, autoRenew: true },
  { id: "cap-2", group: "Internal", allowedCAs: ["Internal PKI"], renewalThreshold: 15, autoRenew: true },
  { id: "cap-3", group: "Legacy", allowedCAs: ["Symantec", "GlobalSign"], renewalThreshold: 45, autoRenew: false },
];

export const MOCK_CA_HEALTH: CAHealth[] = [
  { id: "cah-1", name: "Let's Encrypt", uptime: 99.99, lastIssuance: "2 mins ago", errorRate: 0.01, status: "Healthy" },
  { id: "cah-2", name: "DigiCert", uptime: 100, lastIssuance: "1 hour ago", errorRate: 0, status: "Healthy" },
  { id: "cah-3", name: "Internal PKI", uptime: 98.5, lastIssuance: "5 mins ago", errorRate: 2.4, status: "Degraded" },
  { id: "cah-4", name: "GlobalSign", uptime: 0, lastIssuance: "2 days ago", errorRate: 100, status: "Down" },
];

export const MOCK_CHART_FAILURE_RATE: TimeSeriesDataPoint[] = [
  { timestamp: "Mon", value: 1.2 },
  { timestamp: "Tue", value: 0.8 },
  { timestamp: "Wed", value: 3.5 },
  { timestamp: "Thu", value: 1.1 },
  { timestamp: "Fri", value: 0.5 },
  { timestamp: "Sat", value: 0.2 },
  { timestamp: "Sun", value: 0.1 },
];

export const MOCK_CHART_DISCOVERY_HISTORY = [
  { run: "Run 1", scanned: 500, found: 45 },
  { run: "Run 2", scanned: 520, found: 48 },
  { run: "Run 3", scanned: 600, found: 55 },
  { run: "Run 4", scanned: 590, found: 52 },
  { run: "Run 5", scanned: 610, found: 60 },
];
