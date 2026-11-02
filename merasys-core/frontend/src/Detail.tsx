import { useEffect, useState } from "react";
import { request, message } from "./api";
import { Badge, Modal } from "./common";
import {
  absolute,
  duration,
  kind,
  memberState,
  state,
  targetName,
  technicalName,
  typeName,
} from "./model";
import type { Bucket, History, Period, Snapshot, Target } from "./types";
import { DiskDetail, Metrics } from "./Metrics";
const cache = new Map<string, { at: number; data: History }>();
const colors = {
  UP: "#32aa81",
  DOWN: "#e16a64",
  UNKNOWN: "#e2b35d",
  DISABLED: "#b7c1cd",
  NO_DATA: "#e1e7ee",
};
export function Detail({
  target: t,
  data,
  close,
}: {
  target: Target;
  data: Snapshot;
  close: () => void;
}) {
  const [period, setPeriod] = useState<Period>("30d");
  const [history, setHistory] = useState<History | null>(null),
    [error, setError] = useState(""),
    [bucket, setBucket] = useState<Bucket | null>(null);
  const key = `${t.id}:${period}`;
  const stamp = data.generated_at;
  useEffect(() => {
    const cached = cache.get(key),
      controller = new AbortController();
    setHistory(cached?.data || null);
    setError("");
    setBucket(null);
    if (cached && Date.now() - cached.at < 30000) return;
    void request<History>(
      `/api/targets/${t.id}/availability?period=${period}`,
      { signal: controller.signal },
    )
      .then((result) => {
        if (controller.signal.aborted) return;
        cache.set(key, { at: Date.now(), data: result });
        if (cache.size > 12) cache.delete(cache.keys().next().value!);
        setHistory(result);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      });
    return () => controller.abort();
  }, [key, t.id, period, stamp]);
  const at = (value: string | null | undefined) =>
    absolute(value, data.display_timezone);
  const fields = [
    ["Định danh giám sát", technicalName(t)],
    ["Máy chủ", t.host],
    ["Kiểm tra gần nhất", at(t.checked_at)],
    ["Dự án", t.projects.join(", ") || "Chưa gán dự án"],
    ["Người phụ trách", t.owners.join(", ") || "Chưa khai báo"],
  ];
  if (kind(t) === "rabbitmq")
    fields.push(
      ["Connection", t.rabbitmq.connection || "—"],
      ["Vhost", t.rabbitmq.vhost || "—"],
      ["Consumer tối thiểu", String(t.rabbitmq.min_consumers ?? 0)],
      [
        "Ngưỡng message chờ",
        t.rabbitmq.alert_threshold == null
          ? "Không giới hạn"
          : String(t.rabbitmq.alert_threshold),
      ],
    );
  return (
    <Modal title={targetName(t)} close={close}>
      <p>
        {typeName(t)} · <Badge status={state(t, data)} />
      </p>
      <section className="mtr-history">
        <div className="mtr-history-top">
          <h3>Lịch sử hoạt động</h3>
          <div className="mtr-periods">
            {(["24h", "7d", "30d"] as const).map((p) => (
              <button
                key={p}
                className={`mtr-period ${period === p ? "active" : ""}`}
                onClick={() => setPeriod(p)}
              >
                {p === "24h" ? "24 giờ" : p === "7d" ? "7 ngày" : "30 ngày"}
              </button>
            ))}
          </div>
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
            {history && " Đang giữ kết quả lịch sử gần nhất."}
          </p>
        )}
        {!history && !error && <p>Đang tải lịch sử…</p>}
        {history && (
          <>
            <div className="mtr-stat-grid">
              {[
                [
                  "Uptime",
                  history.uptime_percent == null
                    ? "Chưa đủ dữ liệu"
                    : `${history.uptime_percent.toFixed(2)}%`,
                  "UP / (UP + DOWN)",
                ],
                [
                  "Downtime",
                  duration(history.seconds.DOWN),
                  "Trong khoảng đã chọn",
                ],
                [
                  "Đợt gián đoạn",
                  history.downtime_count,
                  "Có giao với khoảng đã chọn",
                ],
                [
                  "Gián đoạn dài nhất",
                  duration(history.longest_down_seconds),
                  "Trong khoảng đã chọn",
                ],
              ].map(([label, value, hint]) => (
                <div className="mtr-stat" key={String(label)}>
                  <label>{label}</label>
                  <strong>{value}</strong>
                  <small>{hint}</small>
                </div>
              ))}
            </div>
            <div className="mtr-timeline">
              {history.buckets.map((b, index) => (
                <button
                  className="mtr-bin"
                  key={index}
                  style={{ background: colors[b.state] }}
                  onClick={() => setBucket(b)}
                  aria-label={`${at(b.start)}: ${b.state}`}
                  title={`${at(b.start)} → ${at(b.end)} · ${b.state}`}
                />
              ))}
            </div>
            <div className="mtr-axis">
              <span>{at(history.start)}</span>
              <span>{at(history.end)}</span>
            </div>
            <div className="mtr-legend">
              {Object.entries(colors).map(([s, color]) => (
                <span key={s}>
                  <i style={{ background: color }} />
                  {s === "NO_DATA" ? "Chưa ghi" : s === "DOWN" ? "Có DOWN" : s}
                </span>
              ))}
            </div>
            <p className="mtr-history-note">
              Độ phủ toàn kỳ: {history.window_coverage_percent.toFixed(1)}% · Độ
              phủ khi giám sát:{" "}
              {history.coverage_percent == null
                ? "Chưa đủ dữ liệu"
                : `${history.coverage_percent.toFixed(1)}%`}{" "}
              · UNKNOWN: {duration(history.seconds.UNKNOWN)} · Không giám sát:{" "}
              {duration(history.seconds.DISABLED)} · Chưa ghi:{" "}
              {duration(history.seconds.NO_DATA)}.<br />
              Lịch sử chỉ chuyển UP/DOWN khi đủ ngưỡng xác nhận. Bắt đầu ghi:{" "}
              {at(history.recorded_since)}. Màu đỏ chỉ có nghĩa là có gián đoạn
              trong vạch, không phải toàn bộ vạch bị DOWN. Nhấn vạch để xem chi
              tiết.
            </p>
            {bucket && (
              <div className="mtr-bucket">
                {at(bucket.start)} → {at(bucket.end)}
                <br />
                {Object.entries(bucket.seconds)
                  .map(([s, seconds]) => `${s}: ${duration(seconds)}`)
                  .join(" · ")}
              </div>
            )}
            <div className="mtr-outages">
              <h3>Các khoảng gián đoạn</h3>
              {history.downtimes.length ? (
                history.downtimes.map((event, index) => (
                  <details className="mtr-outage" key={index}>
                    <summary>
                      {at(event.started_at)} →{" "}
                      {event.ended_at ? at(event.ended_at) : "Đang tiếp diễn"} ·{" "}
                      <strong>{duration(event.duration_seconds)}</strong>
                      {event.continues_from_before_window &&
                        " · Từ trước đầu kỳ"}
                    </summary>
                    <pre>{event.reason || "Không có mô tả"}</pre>
                  </details>
                ))
              ) : (
                <p>
                  Chưa ghi nhận khoảng DOWN đã xác nhận trong kỳ. Kiểm tra độ
                  phủ dữ liệu phía trên.
                </p>
              )}
              {history.downtimes_truncated && (
                <p>
                  Chỉ hiện 100 khoảng gần nhất; tổng số và thời lượng vẫn tính
                  toàn kỳ.
                </p>
              )}
            </div>
          </>
        )}
      </section>
      <div className="detail-grid">
        {fields.map(([label, value]) => (
          <div className="detail-card" key={label}>
            <div className="detail-label">{label}</div>
            <div className="detail-value">{value}</div>
          </div>
        ))}
      </div>
      <section className="detail-block">
        <h3>Kết quả kiểm tra</h3>
        <pre className="detail-pre">{t.reason || "Chưa có kết quả"}</pre>
      </section>
      {t.note && (
        <section className="detail-block">
          <h3>Ghi chú</h3>
          <pre className="detail-pre note-pre">{t.note}</pre>
        </section>
      )}
      <DiskDetail target={t} data={data} />
      {kind(t) === "rabbitmq" && (
        <section className="detail-block">
          <h3>Số liệu RabbitMQ</h3>
          <Metrics target={t} data={data} />
        </section>
      )}
      {!!t.compose_services.length && (
        <section className="detail-block">
          <h3>Service trong Compose ({t.compose_services.length})</h3>
          <div className="mtr-members">
            {t.compose_services.map((m) => (
              <div className="mtr-member" key={m.name}>
                <div className="mtr-member-head">
                  <strong>{m.name}</strong>
                  <Badge status={memberState(t, m, data)} />
                </div>
                <p>{m.reason || "—"}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </Modal>
  );
}
