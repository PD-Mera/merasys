import { useState } from "react";
import type { FormEvent } from "react";
import { request, message } from "./api";
import { Modal } from "./common";
import { absolute } from "./model";
import type { NotificationResult } from "./types";
export function TestAlert({
  open,
  close,
  zone,
}: {
  open: boolean;
  close: () => void;
  zone: string;
}) {
  const [busy, setBusy] = useState(false),
    [id, setId] = useState<number | null>(null),
    [feedback, setFeedback] = useState("");
  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    const owners = String(data.get("owners"))
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (owners.length > 20) {
      setFeedback("Chỉ chọn tối đa 20 người phụ trách.");
      return;
    }
    setBusy(true);
    setId(null);
    setFeedback("Đang đưa tin thử vào hàng đợi…");
    try {
      const result = await request<{ id: number }>("/api/notifications/test", {
        method: "POST",
        headers: { "X-Monitor-Action": "test-alert" },
        body: JSON.stringify({
          title: data.get("title"),
          message: data.get("message"),
          owners,
        }),
      });
      setId(result.id);
      setFeedback(
        `Đã xếp hàng tin thử #${result.id}. Worker sẽ gửi theo thứ tự hàng đợi. Nhấn “Kiểm tra kết quả” để xác nhận Telegram đã nhận.`,
      );
    } catch (e) {
      setFeedback(
        `${message(e)} Tin có thể đã được xếp hàng; kiểm tra Telegram trước khi gửi lại.`,
      );
    } finally {
      setBusy(false);
    }
  }
  async function check() {
    if (busy || id == null) return;
    setBusy(true);
    try {
      const result = await request<NotificationResult>(
        `/api/notifications/test/${id}`,
      );
      if (result.status === "sent")
        setFeedback(
          `Telegram đã nhận tin thử #${result.id} · ${absolute(result.sent_at, zone)}`,
        );
      else
        setFeedback(
          [
            `Tin thử #${result.id} đang chờ gửi · Đã thử ${result.attempts} lần.`,
            result.last_error && `Lỗi gửi tin: ${result.last_error}`,
            result.attempts > 0 &&
              `Lần thử tiếp theo: ${absolute(result.next_attempt_at, zone)}`,
            result.queued_ahead > 0 &&
              `Có ${result.queued_ahead} tin phía trước trong hàng đợi.`,
            result.blocking_error &&
              `Tin phía trước đang lỗi: ${result.blocking_error}`,
            !result.worker_recent &&
              "Worker alerts chưa có heartbeat gần đây. Kiểm tra container và logs alerts.",
            !result.attempts &&
              !result.queued_ahead &&
              "Chưa có lần gửi. Kiểm tra worker alerts, cấu hình Telegram và nâng cấp DB (init-db).",
          ]
            .filter(Boolean)
            .join("\n"),
        );
    } catch (e) {
      setFeedback(message(e));
    } finally {
      setBusy(false);
    }
  }
  if (!open) return null;
  return (
    <Modal title="Thử cảnh báo Telegram" close={close} busy={busy}>
      <form className="test-alert-form" onSubmit={send}>
        <p>Tin thử được đưa vào hàng đợi; không đổi trạng thái giám sát.</p>
        <label className="test-alert-field">
          Tiêu đề
          <input
            name="title"
            required
            maxLength={120}
            defaultValue="Kiểm tra cảnh báo Telegram"
          />
        </label>
        <label className="test-alert-field">
          Nội dung
          <textarea name="message" required maxLength={2000} />
        </label>
        <label className="test-alert-field">
          Người phụ trách cần tag (tùy chọn)
          <input
            name="owners"
            maxLength={4000}
            placeholder="dong.trinh1, nghia.nguyen1"
          />
          <small>
            Ngăn cách bằng dấu phẩy; tối đa 20 người. Tra ID/username từ tab
            TelegramUsers đã đồng bộ.
          </small>
        </label>
        <p role="status" style={{ whiteSpace: "pre-wrap" }}>
          {feedback}
        </p>
        <div className="mtr-modal-buttons">
          <button
            className="btn btn-secondary"
            type="button"
            disabled={busy || id == null}
            onClick={() => void check()}
          >
            Kiểm tra kết quả
          </button>
          <button className="btn btn-primary" disabled={busy}>
            Gửi thử Telegram
          </button>
        </div>
      </form>
    </Modal>
  );
}
