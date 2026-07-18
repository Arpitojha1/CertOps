/**
 * frontendNew/src/lib/adapters.ts
 *
 * Data transformation adapters — bridge between the raw JSON shapes returned
 * by api.py/db.py and the TypeScript interfaces declared in types.ts.
 *
 * ALL normalisation lives here so that page components stay clean and
 * backend serialiser changes only need to be handled in one place.
 *
 * Raw types (prefixed Raw*) reflect what api.py currently returns.
 * Target types come from @/types.ts.
 */

import {
  Certificate,
  Connector,
  EventLog,
  GroupPolicy,
  NotificationPolicy,
  ScheduledJob,
  CertStatus,
} from "@/types";

// ============================================================
// Raw API response shapes (what backend currently sends)
// ============================================================

export interface RawCertificate {
  id: string;
  name?: string;           // alias for domain in some serialisers
  domain?: string;
  connector?: string;
  source?: string;         // alias for connector
  ca?: string;
  expiry_date?: string;    // snake_case
  expiryDate?: string;     // in case backend is updated to camelCase
  status?: string;         // e.g. "VALID", "EXPIRED", "EXPIRING_SOON", "REVOKED"
  group_id?: string;
  group?: string;
  days_remaining?: number;
  daysRemaining?: number;
  // Enterprise extension fields (added in Tier 2)
  type?: "Server" | "Client";
  owner?: string;
}

export interface RawConnector {
  id: string;
  name: string;
  type?: string;           // snake_case category e.g. "secret_store", "azure"
  category?: string;       // normalised category (added in Tier 2)
  renewal_threshold_days?: number;
  renewalThreshold?: number;
  status?: string;
  // config blob present but not consumed in list views
}

export interface RawEventLog {
  id: string;
  action_type?: string;
  event_type?: string;
  type?: string;           // normalised (added in Tier 2)
  details?: string;
  description?: string;   // normalised (added in Tier 2)
  timestamp: string;
  status?: string;
  actor?: string;
  target_type?: string;
  target_id?: string;
}

export interface RawGroupPolicy {
  id: string;
  name: string;
  description?: string;
  maintenanceWindow?: string;  // joined (added in Tier 2)
  notificationPolicy?: string; // joined (added in Tier 2)
  // Raw separate fields when not joined:
  maintenance_window?: string;
  notification_policy_name?: string;
}

export interface RawNotificationPolicy {
  id: string;
  group_id?: string;
  group?: string;          // resolved display name (Tier 2)
  channel?: string;
  target?: string;
  days_before_expiry?: number;
  threshold?: string;      // formatted string (Tier 2)
  notify_on_success?: boolean;
  notify_on_failure?: boolean;
  is_active?: boolean;
  status?: string;         // "Active" | "Disabled" (Tier 2)
}

export interface RawScheduledJob {
  id: string;
  name: string;
  next_run?: string;
  nextRun?: string;
  last_run?: string;
  target?: string;         // (added in Tier 2)
  status?: string;         // (added in Tier 2)
}

export interface RawSchedulerStatus {
  running?: boolean;
  interval_hours?: number;
  jobs?: RawScheduledJob[];
}

// ============================================================
// Certificate adapter
// ============================================================

/** Map backend status strings to the UI's CertStatus union. */
function normaliseCertStatus(raw?: string): CertStatus {
  const s = (raw ?? "").toUpperCase();
  if (s === "VALID" || s === "ACTIVE") return "Active";
  if (s === "EXPIRING_SOON" || s === "EXPIRING") return "Expiring Soon";
  if (s === "REVOKED") return "Revoked";
  if (s === "EXPIRED") return "Expired";
  if (s === "PENDING") return "Pending";
  // Pass through title-cased values from updated serialiser
  if (raw === "Active") return "Active";
  if (raw === "Expiring Soon") return "Expiring Soon";
  if (raw === "Revoked") return "Revoked";
  if (raw === "Expired") return "Expired";
  if (raw === "Pending") return "Pending";
  return "Active";
}

/** Calculate days remaining from an ISO date string. */
function calcDaysRemaining(expiryDate?: string): number {
  if (!expiryDate) return 0;
  const diff = new Date(expiryDate).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

/** Adapt a raw API certificate object to the Certificate interface. */
export function adaptCertificate(raw: RawCertificate): Certificate {
  const expiryDate = raw.expiryDate ?? raw.expiry_date ?? "";
  return {
    id: raw.id,
    domain: raw.domain ?? raw.name ?? "",
    connector: raw.connector ?? raw.source ?? "",
    ca: raw.ca ?? "Unknown",
    expiryDate,
    daysRemaining: raw.daysRemaining ?? raw.days_remaining ?? calcDaysRemaining(expiryDate),
    status: normaliseCertStatus(raw.status),
    group: raw.group ?? raw.group_id ?? "",
  };
}

// ============================================================
// Connector adapter
// ============================================================

/** Normalise raw category strings to the UI category union. */
function normaliseCategory(raw?: string): "Secret Store" | "Host" | "Certificate Authority" {
  if (!raw) return "Host";
  const r = raw.toLowerCase();
  if (r === "secret store") return "Secret Store";
  if (["secret_store", "azure", "hashicorp", "vault"].includes(r)) return "Secret Store";
  if (["host", "ssh_host", "ssh", "winrm_host", "winrm"].includes(r)) return "Host";
  if (["ca", "certificate_authority", "certificate authority"].includes(r)) return "Certificate Authority";
  return "Host";
}

function normaliseConnectorStatus(raw?: string): "Connected" | "Error" | "Pending" {
  if (!raw) return "Pending";
  const r = raw.toLowerCase();
  if (["connected", "ok", "success", "healthy"].includes(r)) return "Connected";
  if (["error", "failed", "down", "unreachable"].includes(r)) return "Error";
  return "Pending";
}

export function adaptConnector(raw: RawConnector): Connector {
  return {
    id: raw.id,
    name: raw.name,
    category: raw.category
      ? normaliseCategory(raw.category)         // Tier 2: backend sends normalised
      : normaliseCategory(raw.type),            // Tier 1: backend sends raw type
    renewalThreshold: raw.renewalThreshold ?? raw.renewal_threshold_days ?? 30,
    status: normaliseConnectorStatus(raw.status),
  };
}

// ============================================================
// EventLog adapter
// ============================================================

function normaliseEventType(raw?: string): EventLog["type"] {
  const allowed: EventLog["type"][] = [
    "Renewal", "Failure", "Config", "Login", "Discovery", "Revocation", "Issuance",
  ];
  if (!raw) return "Config";
  const titleCased = raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
  if (allowed.includes(titleCased as EventLog["type"])) return titleCased as EventLog["type"];
  // Map backend action_type values
  if (raw.toLowerCase().includes("renewal")) return "Renewal";
  if (raw.toLowerCase().includes("revoc")) return "Revocation";
  if (raw.toLowerCase().includes("issue") || raw.toLowerCase().includes("enroll")) return "Issuance";
  if (raw.toLowerCase().includes("login") || raw.toLowerCase().includes("auth")) return "Login";
  if (raw.toLowerCase().includes("config")) return "Config";
  if (raw.toLowerCase().includes("discover")) return "Discovery";
  if (raw.toLowerCase().includes("fail") || raw.toLowerCase().includes("error")) return "Failure";
  return "Config";
}

function deriveEventStatus(raw?: RawEventLog): EventLog["status"] {
  // If backend provides status directly (Tier 2 serialiser fix)
  if (raw?.status === "Success" || raw?.status === "Failed" || raw?.status === "Info") {
    return raw.status;
  }
  // Derive from details content (Tier 1 fallback)
  const details = (raw?.details ?? raw?.description ?? "").toLowerCase();
  if (details.includes("error") || details.includes("fail") || details.includes("failed")) {
    return "Failed";
  }
  if (raw?.action_type?.toLowerCase().includes("config")) return "Info";
  return "Success";
}

export function adaptEventLog(raw: RawEventLog): EventLog {
  return {
    id: raw.id,
    type: normaliseEventType(raw.type ?? raw.action_type ?? raw.event_type),
    description: raw.description ?? raw.details ?? "",
    timestamp: raw.timestamp,
    status: deriveEventStatus(raw),
  };
}

// ============================================================
// GroupPolicy adapter
// ============================================================

export function adaptGroupPolicy(raw: RawGroupPolicy): GroupPolicy {
  return {
    id: raw.id,
    name: raw.name,
    maintenanceWindow:
      raw.maintenanceWindow ??           // Tier 2: backend returns joined
      raw.maintenance_window ??          // intermediate
      "Not configured",
    notificationPolicy:
      raw.notificationPolicy ??          // Tier 2: backend returns joined
      raw.notification_policy_name ??    // intermediate
      "Default",
  };
}

// ============================================================
// NotificationPolicy adapter
// ============================================================

export function adaptNotificationPolicy(raw: RawNotificationPolicy): NotificationPolicy {
  const threshold =
    raw.threshold ??                              // Tier 2: formatted string from backend
    (raw.days_before_expiry != null
      ? `${raw.days_before_expiry} days`
      : "30 days");

  const status: "Active" | "Disabled" =
    raw.status === "Active" || raw.status === "Disabled"
      ? raw.status
      : raw.is_active === false
        ? "Disabled"
        : "Active";

  return {
    id: raw.id,
    group: raw.group ?? raw.group_id ?? "",
    threshold,
    channel: raw.channel ?? "",
    status,
  };
}

// ============================================================
// ScheduledJob adapter
// ============================================================

function normaliseJobStatus(raw?: string): ScheduledJob["status"] {
  if (!raw) return "Scheduled";
  const r = raw.toLowerCase();
  if (r === "running") return "Running";
  if (r === "failed" || r === "error") return "Failed";
  return "Scheduled";
}

export function adaptScheduledJob(raw: RawScheduledJob): ScheduledJob {
  return {
    id: raw.id,
    name: raw.name,
    target: raw.target ?? "",
    nextRun: raw.nextRun ?? raw.next_run ?? "",
    status: normaliseJobStatus(raw.status),
  };
}
