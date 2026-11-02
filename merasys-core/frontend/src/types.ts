export type State = "UP" | "DOWN" | "UNKNOWN" | "DISABLED";
export interface Member {
  name: string;
  status: State;
  reason: string;
  containers: unknown[];
  checked_at: string | null;
}
export interface Disk {
  path: string;
  state: string;
  observed: string;
  reason: string;
  free_bytes: number | null;
  total_bytes: number | null;
}
export interface Target {
  id: number;
  host: string;
  container: string;
  type?: string;
  display_name: string;
  projects: string[];
  owners: string[];
  note: string;
  status: State;
  reason: string;
  checked_at: string | null;
  compose_services: Member[];
  rabbitmq: {
    queue?: string;
    connection?: string;
    vhost?: string;
    min_consumers?: number;
    alert_threshold?: number | null;
  };
  rabbitmq_metrics: {
    observed_at?: string;
    consumers?: number;
    messages?: number;
    publish_rate?: number;
    deliver_rate?: number;
    ack_rate?: number;
  };
  server_config: {
    disks?: { path: string; min_free_gb: number; recover_free_gb: number }[];
  };
  disk_metrics: { checked_at?: string; disks?: Disk[] };
}
export interface Snapshot {
  targets: Target[];
  health: {
    component: string;
    status: string;
    last_ok_at: string | null;
    stale_after_seconds: number;
    error: string;
  }[];
  incidents: { title: string; detail: string; opened_at: string }[];
  notification_queue: {
    id: number;
    title: string;
    attempts: number;
    last_error: string;
    created_at: string;
    next_attempt_at: string;
  }[];
  pending_notifications: number;
  generated_at: string;
  display_timezone: string;
  stale_after_seconds: number;
  sheet_url: string | null;
}
export type Period = "24h" | "7d" | "30d";
export type Seconds = Record<State | "NO_DATA", number>;
export interface Bucket {
  start: string;
  end: string;
  state: keyof Seconds;
  seconds: Seconds;
}
export interface History {
  target_id: number;
  period: Period;
  start: string;
  end: string;
  recorded_since: string | null;
  uptime_percent: number | null;
  coverage_percent: number | null;
  window_coverage_percent: number;
  seconds: Seconds;
  downtime_count: number;
  longest_down_seconds: number;
  buckets: Bucket[];
  downtimes: {
    started_at: string;
    ended_at: string | null;
    duration_seconds: number;
    reason: string;
    continues_from_before_window: boolean;
  }[];
  downtimes_truncated: boolean;
}
export interface PublicSettings {
  values: Record<string, string | number | null>;
  configured: Record<string, boolean>;
  agent_hosts: string[];
  agent_tokens: Record<string, string>;
  database: string;
  web: { host: string; port: number };
}
export interface NotificationResult {
  id: number;
  status: string;
  attempts: number;
  last_error: string;
  sent_at: string | null;
  next_attempt_at: string;
  queued_ahead: number;
  blocking_error: string;
  worker_recent: boolean;
}
