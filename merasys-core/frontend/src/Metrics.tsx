import type { Target, Snapshot } from "./types";
import { absolute, kind, state } from "./model";
const gb = (bytes: number | null | undefined) =>
  bytes == null
    ? "—"
    : (bytes / 1e9).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
export function Metrics({
  target: t,
  data,
}: {
  target: Target;
  data: Snapshot;
}) {
  const zone = data.display_timezone;
  if (kind(t) === "server" && t.server_config.disks?.length) {
    const metrics = t.disk_metrics;
    if (!metrics.disks?.length)
      return (
        <span className="rabbitmq-metric stale">
          Ổ đĩa: chờ agent gửi số liệu
        </span>
      );
    const stale =
      ["UNKNOWN", "DISABLED"].includes(state(t, data)) ||
      !metrics.checked_at ||
      Date.now() - Date.parse(metrics.checked_at) >
        data.stale_after_seconds * 1000;
    return (
      <>
        {metrics.disks.map((disk) => (
          <span
            className={`rabbitmq-metric ${stale || disk.observed !== "UP" ? "stale" : ""}`}
            key={disk.path}
            title={`${disk.reason} · ${absolute(metrics.checked_at, zone)}`}
          >
            {disk.path}: <b>{gb(disk.free_bytes)} GB</b> trống
            {stale ? " · cũ" : ""}
          </span>
        ))}
      </>
    );
  }
  if (kind(t) !== "rabbitmq") return null;
  const metrics = t.rabbitmq_metrics;
  if (!metrics.observed_at)
    return <span className="rabbitmq-metric stale">Chưa có số liệu</span>;
  const stamp = Date.parse(metrics.observed_at);
  const stale =
    ["UNKNOWN", "DISABLED"].includes(state(t, data)) ||
    !Number.isFinite(stamp) ||
    Date.now() - stamp > data.stale_after_seconds * 1000 ||
    metrics.observed_at !== t.checked_at;
  const items = [
    ["consumers", "consumers", false],
    ["messages", "msg", false],
    ["publish_rate", "Incoming", true],
    ["deliver_rate", "Deliver / get", true],
    ["ack_rate", "Ack", true],
  ] as const;
  return (
    <>
      {stale && <span className="rabbitmq-metric stale">Số liệu cũ</span>}
      {items.map(([key, label, rate]) => {
        const value = metrics[key],
          text =
            typeof value === "number" && Number.isFinite(value) && value >= 0
              ? value.toLocaleString("vi-VN", {
                  maximumFractionDigits: rate ? 1 : 0,
                })
              : "—";
        return (
          <span
            className="rabbitmq-metric"
            key={key}
            title={`Cập nhật: ${absolute(metrics.observed_at, zone)}${value == null ? " · RabbitMQ chưa cung cấp số liệu này" : ""}`}
          >
            {label}{" "}
            <b>
              {text}
              {rate && value != null ? "/s" : ""}
            </b>
          </span>
        );
      })}
    </>
  );
}
export function DiskDetail({
  target: t,
  data,
}: {
  target: Target;
  data: Snapshot;
}) {
  if (kind(t) !== "server" || !t.server_config.disks?.length) return null;
  const fresh =
    !["UNKNOWN", "DISABLED"].includes(state(t, data)) &&
    t.disk_metrics.checked_at &&
    Date.now() - Date.parse(t.disk_metrics.checked_at) <=
      data.stale_after_seconds * 1000;
  const labels: Record<string, string> = {
    UP: "Đủ dung lượng",
    LOW: "Thiếu dung lượng",
    ERROR: "Không kiểm tra được",
    UNKNOWN: "Chờ xác nhận",
  };
  return (
    <section className="detail-block">
      <h3>Dung lượng ổ đĩa</h3>
      <p>
        {!fresh && "Số liệu cũ hoặc chưa có dữ liệu · "}
        {absolute(t.disk_metrics.checked_at, data.display_timezone)} · 1 GB =
        1.000.000.000 byte
      </p>
      <div className="mtr-members">
        {t.server_config.disks.map((config) => {
          const disk = t.disk_metrics.disks?.find(
            (d) => d.path === config.path,
          );
          return (
            <div className="mtr-member" key={config.path}>
              <div className="mtr-member-head">
                <strong>{config.path}</strong>
                <span>{labels[disk?.state || ""] || "Chờ số liệu"}</span>
              </div>
              <p>
                Còn trống <strong>{gb(disk?.free_bytes)} GB</strong> /{" "}
                {gb(disk?.total_bytes)} GB
              </p>
              <p>
                Cảnh báo dưới {config.min_free_gb} GB · Phục hồi từ{" "}
                {config.recover_free_gb} GB
              </p>
              {disk && <p>{disk.reason}</p>}
            </div>
          );
        })}
      </div>
    </section>
  );
}
