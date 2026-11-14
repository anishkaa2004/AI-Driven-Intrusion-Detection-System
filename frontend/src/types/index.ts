export type Role = "admin" | "analyst" | "viewer";
export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type AlertStatus = "new" | "acknowledged" | "investigating" | "resolved" | "false_positive";
export type Health = "online" | "stale" | "offline" | "never_seen" | "pending" | "revoked";

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];
export const STATUSES: AlertStatus[] = ["new", "acknowledged", "investigating", "resolved", "false_positive"];
export const OPEN_STATUSES: AlertStatus[] = ["new", "acknowledged", "investigating"];

export interface User {
  id: number;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface Device {
  id: number;
  owner_user_id: number;
  owner_email: string | null;
  display_name: string;
  platform: string | null;
  hostname: string | null;
  agent_version: string | null;
  status: "pending" | "active" | "revoked";
  health: Health;
  created_at: string;
  enrolled_at: string | null;
  last_seen_at: string | null;
  revoked_at: string | null;
  enrollment_expires_at: string | null;
  monitoring_paused: boolean;
  last_collector: string | null;
  last_interface: string | null;
  events_24h: number;
  open_alerts: number;
}

export interface Alert {
  id: number;
  device_id: number;
  device_name: string | null;
  title: string;
  category: string;
  severity: Severity;
  status: AlertStatus;
  detection_source: "rule" | "ml" | "anomaly" | "combined";
  rule_id: string | null;
  model_version: string | null;
  score: number | null;
  score_meaning: string | null;
  occurrence_count: number;
  is_demo: boolean;
  first_seen_at: string;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export interface FlowEvent {
  id: number;
  event_uid: string;
  device_id: number;
  source: string;
  event_time: string;
  received_at: string;
  protocol: string;
  src_ip: string | null;
  dst_ip: string | null;
  src_port: number | null;
  dst_port: number | null;
  flow_duration: number | null;
  packets_in: number | null;
  packets_out: number | null;
  bytes_in: number | null;
  bytes_out: number | null;
  conn_state: string | null;
  dns_rcode: string | null;
  ml_label: string | null;
  ml_score: number | null;
  model_version: string | null;
}

export interface Note {
  id: number;
  alert_id: number;
  author_user_id: number;
  author_email: string | null;
  note: string;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  actor_user_id: number | null;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  ip_address: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface AlertDetail extends Alert {
  evidence_json: Record<string, unknown>;
  recommendation: string | null;
  notes: Note[];
  audit_trail: AuditEntry[];
  related_events: FlowEvent[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Summary {
  window_hours: number;
  generated_at: string;
  devices: { total: number; reporting: number; stale: number; offline: number; pending: number; revoked: number };
  events: number;
  open_alerts: number;
  alerts_by_severity: Record<Severity, number>;
  alerts_by_category: Record<string, number>;
  alerts_by_source: Record<string, number>;
  protocols: Record<string, number>;
  series: { t: string; flows: number; bytes: number; alerts: number }[];
  bucket_s: number;
  recent_alerts: Alert[];
  health: {
    backend: string;
    model_loaded: boolean;
    model_version: string | null;
    model_error: string | null;
    dashboard_clients: number;
  };
}

export interface ClassMetrics {
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface EvalMetrics {
  labels: string[];
  per_class: Record<string, ClassMetrics>;
  macro: { precision: number; recall: number; f1: number };
  accuracy: number;
  false_positive_rate: number | null;
  detection_rate: number | null;
  confusion_matrix: number[][];
  binary_pr_auc?: number;
  test_rows: number;
  latency?: {
    single_row_ms_median: number;
    single_row_ms_p95: number;
    batch_rows: number;
    batch_rows_per_second: number | null;
  };
  note?: string;
}

export interface Experiment {
  model_name: string;
  selected?: boolean;
  deployable?: boolean;
  validation?: EvalMetrics;
  test: EvalMetrics;
  feature_importance?: Record<string, number>;
}

export interface RuleDoc {
  rule_id: string;
  name: string;
  category: string;
  required_fields: string[];
  logic: string;
  benign_causes: string[];
}

export interface ModelMetrics {
  active: {
    loaded: boolean;
    model_version: string | null;
    load_error: string | null;
    last_inference_latency_ms: number | null;
    manifest: {
      model_name?: string;
      model_version?: string;
      dataset?: string;
      dataset_reference?: string;
      trained_at?: string;
      feature_schema_version?: string;
      feature_columns?: string[];
      labels?: string[];
      split?: Record<string, string | number>;
      clean_report?: Record<string, unknown>;
      metrics?: EvalMetrics;
      experiments?: Experiment[];
      environment?: Record<string, string>;
    };
  };
  registry: {
    id: number;
    model_name: string;
    model_version: string;
    dataset_reference: string;
    is_active: boolean;
    trained_at: string | null;
  }[];
  rules: RuleDoc[];
}

export type LiveMessage =
  | { type: "ready"; user_id: number }
  | { type: "pong" }
  | { type: "alert"; action: "created" | "updated"; alert: Alert }
  | { type: "device"; device: Device }
  | {
      type: "events";
      device_id: number;
      events: number;
      bytes: number;
      protocols: Record<string, number>;
      source: string;
      received_at: string;
    };
