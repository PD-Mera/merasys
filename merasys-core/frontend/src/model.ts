import type { Target, Snapshot, Member, State } from "./types";
export const labels: Record<string, string> = {
  UP: "Hoạt động",
  DOWN: "Gián đoạn",
  UNKNOWN: "Chưa rõ",
  DISABLED: "Đã tắt",
  DEGRADED: "Cần chú ý",
  STALE: "Quá hạn",
};
export function kind(t: Target) {
  const declared = t.type?.trim().toLowerCase();
  if (
    declared &&
    ["server", "compose", "rabbitmq", "systemd"].includes(declared)
  )
    return declared;
  return t.container === "(server)"
    ? "server"
    : t.container.startsWith("compose:")
      ? "compose"
      : t.container.startsWith("rabbitmq:")
        ? "rabbitmq"
        : t.container.startsWith("systemd:")
          ? "systemd"
          : "legacy";
}
export const typeName = (t: Target) =>
  ({
    server: "Máy chủ · Heartbeat",
    compose: "Docker Compose",
    rabbitmq: "RabbitMQ Queue",
    systemd: "System service",
    legacy: "Mục cũ đã ngừng hỗ trợ",
  })[kind(t)] ?? "Chưa rõ";
export const technicalName = (t: Target) =>
  kind(t) === "server"
    ? t.host
    : kind(t) === "rabbitmq"
      ? `${t.rabbitmq.queue || "Queue"} · ${t.rabbitmq.connection || ""}`
      : t.container.replace(/^(compose:|systemd:)/, "");
export const targetName = (t: Target) =>
  t.display_name?.trim() ||
  (kind(t) === "rabbitmq"
    ? t.rabbitmq.queue?.trim() || "Queue RabbitMQ"
    : technicalName(t));
export function state(t: Target, data: Snapshot, now = Date.now()): State {
  if (t.status === "DISABLED") return "DISABLED";
  const stamp = t.checked_at ? Date.parse(t.checked_at) : NaN;
  if (
    !Number.isFinite(stamp) ||
    now - stamp > (data.stale_after_seconds || 180) * 1000
  )
    return "UNKNOWN";
  return t.status in labels ? t.status : "UNKNOWN";
}
export const memberState = (t: Target, member: Member, data: Snapshot) =>
  ["UNKNOWN", "DISABLED"].includes(state(t, data))
    ? state(t, data)
    : member.status;
export function absolute(
  value: string | null | undefined,
  zone = "Asia/Bangkok",
) {
  if (!value) return "Chưa có dữ liệu";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Thời gian không hợp lệ"
    : date.toLocaleString("vi-VN", { timeZone: zone, hour12: false });
}
export function ago(value: string | null | undefined) {
  if (!value) return "Chưa nhận dữ liệu";
  const seconds = Math.max(
    0,
    Math.floor((Date.now() - Date.parse(value)) / 1000),
  );
  if (!Number.isFinite(seconds)) return "Chưa rõ";
  return seconds < 10
    ? "Vừa xong"
    : seconds < 60
      ? `${seconds} giây trước`
      : seconds < 3600
        ? `${Math.floor(seconds / 60)} phút trước`
        : seconds < 86400
          ? `${Math.floor(seconds / 3600)} giờ trước`
          : `${Math.floor(seconds / 86400)} ngày trước`;
}
export function duration(value: number) {
  const s = Math.max(0, Math.round(value || 0)),
    m = Math.floor(s / 60),
    h = Math.floor(m / 60);
  return s < 60
    ? `${s} giây`
    : m < 60
      ? `${m} phút`
      : h < 24
        ? `${h} giờ ${m % 60} phút`
        : `${Math.floor(h / 24)} ngày ${h % 24} giờ`;
}
