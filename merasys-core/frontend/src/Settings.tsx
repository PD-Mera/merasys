import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { request, message, logout } from "./api";
import { groups, secretKeys } from "./fields";
import { AgentTokens } from "./AgentTokens";
import type { PublicSettings } from "./types";

export function Settings() {
  const [metadata, setMetadata] = useState<PublicSettings | null>(null);
  const [values, setValues] = useState<Record<string, string>>({}),
    [clear, setClear] = useState<string[]>([]);
  const [busy, setBusy] = useState(false),
    [feedback, setFeedback] = useState(""),
    [error, setError] = useState(false);
  const [passwordBusy, setPasswordBusy] = useState(false),
    [passwordFeedback, setPasswordFeedback] = useState("");
  function render(data: PublicSettings) {
    setMetadata(data);
    setClear([]);
    setValues(
      Object.fromEntries(
        groups.flatMap(([, , fields]) =>
          fields.map(([key]) => [
            key,
            secretKeys.has(key) && key !== "database_url" ? "" : String(data.values[key] ?? ""),
          ]),
        ),
      ),
    );
  }
  useEffect(() => {
    const controller = new AbortController();
    void request<PublicSettings>("/api/settings", { signal: controller.signal })
      .then(render)
      .catch((e) => {
        if (!controller.signal.aborted) {
          setFeedback(message(e));
          setError(true);
        }
      });
    return () => controller.abort();
  }, []);
  function show(text: string, failed = false) {
    setFeedback(text);
    setError(failed);
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy || !metadata) return;
    setBusy(true);
    show("Đang lưu; lần đầu có thể cần khởi tạo bảng PostgreSQL…");
    try {
      const patch: Record<string, unknown> = {};
      for (const [, , fields] of groups)
        for (const [key, , type] of fields) {
          const value = (values[key] || "").trim();
          if (clear.includes(key) || (secretKeys.has(key) && !value)) continue;
          patch[key] =
            type === "json"
              ? JSON.parse(value)
              : type === "number"
                ? Number(value)
                : type === "optional-number"
                  ? value
                    ? Number(value)
                    : null
                  : value;
        }
      render(
        await request<PublicSettings>(
          "/api/settings",
          { method: "PUT", body: JSON.stringify({ values: patch, clear }) },
          45000,
        ),
      );
      show("Đã lưu. Worker tự nạp cấu hình mới; không cần restart.");
    } catch (e) {
      show(message(e), true);
    } finally {
      setBusy(false);
    }
  }
  async function sync() {
    if (busy) return;
    setBusy(true);
    show("Đang đồng bộ Sheet…");
    try {
      await request("/api/settings/sync", { method: "POST" }, 45000);
      show("Đồng bộ Sheet thành công.");
    } catch (e) {
      show(message(e), true);
    } finally {
      setBusy(false);
    }
  }
  async function password(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (passwordBusy) return;
    const data = new FormData(event.currentTarget);
    if (data.get("new") !== data.get("repeat")) {
      setPasswordFeedback("Hai mật khẩu mới không khớp.");
      return;
    }
    setPasswordBusy(true);
    setPasswordFeedback("");
    try {
      await request("/api/auth/password", {
        method: "POST",
        body: JSON.stringify({
          current: data.get("current"),
          new: data.get("new"),
        }),
      });
      location.replace("/");
    } catch (e) {
      setPasswordFeedback(message(e));
    } finally {
      setPasswordBusy(false);
    }
  }
  return (
    <div className="settings-page">
      <header className="settings-header">
        <strong className="brand">Merasys / Cấu hình</strong>
        <nav>
          <a className="btn btn-secondary" href="/">
            Dashboard
          </a>
          <button
            className="btn btn-secondary"
            disabled={busy || !metadata}
            onClick={() => void sync()}
          >
            Đồng bộ Sheet ngay
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => void logout().catch((e) => show(message(e), true))}
          >
            Đăng xuất
          </button>
        </nav>
      </header>
      <main className="settings-main">
        <h1>Cấu hình hệ thống</h1>
        <p>
          Cấu hình lưu trên server, tự áp dụng cho các worker. Env chỉ còn địa
          chỉ và cổng web.
        </p>
        <p className="notice">
          {metadata
            ? `PostgreSQL: ${metadata.database} · Web: ${metadata.web.host}:${metadata.web.port}. Thay WEB_HOST/WEB_PORT cần recreate container.`
            : "Đang tải cấu hình…"}
        </p>
        <form onSubmit={save}>
          {metadata &&
            groups.map(([title, description, fields]) => (
              <section className="form-card" key={title}>
                <h2>{title}</h2>
                <p className="muted">{description}</p>
                <div className="form-grid">
                  {fields.map(([key, label, type, help]) => {
                    const secret = secretKeys.has(key) && key !== "database_url",
                      saved = secret && metadata.configured[key];
                    const props = {
                      id: key,
                      value: values[key] ?? "",
                      placeholder: saved ? "Đã lưu — để trống giữ nguyên" : "",
                      onChange: (e: { target: { value: string } }) =>
                        setValues((v) => ({ ...v, [key]: e.target.value })),
                    };
                    return (
                      <div
                        className={`form-field ${type === "json" || key === "database_url" ? "full" : ""}`}
                        key={key}
                      >
                        <label htmlFor={key}>{label}</label>
                        {type === "json" ? (
                          <textarea {...props} autoComplete="off" />
                        ) : (
                          <input
                            {...props}
                            type={type.includes("number") ? "number" : type}
                            step={type.includes("number") ? 1 : undefined}
                            min={type.includes("number") ? 0 : undefined}
                            autoComplete={secret ? "new-password" : "off"}
                          />
                        )}
                        <small>
                          {help}
                          {saved ? " · Đã cấu hình" : ""}
                        </small>
                        {secretKeys.has(key) && (
                          <label className="clear-secret">
                            <input
                              type="checkbox"
                              checked={clear.includes(key)}
                              onChange={(e) =>
                                setClear((v) =>
                                  e.target.checked
                                    ? [...v, key]
                                    : v.filter((k) => k !== key),
                                )
                              }
                            />
                            Xóa giá trị đã lưu
                          </label>
                        )}
                        {key === "google_credentials_info" && (
                          <input
                            type="file"
                            aria-label="Chọn JSON service account"
                            accept=".json,application/json"
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (!file) return;
                              if (file.size > 1000000) {
                                show("JSON key quá lớn.", true);
                                return;
                              }
                              void file
                                .text()
                                .then((text) =>
                                  setValues((v) => ({ ...v, [key]: text })),
                                )
                                .catch((e) => show(message(e), true));
                            }}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          <div className="save-bar">
            <button className="btn btn-primary" disabled={busy || !metadata}>
              Lưu cấu hình
            </button>
            <span role="status" className={error ? "form-error" : ""}>
              {feedback}
            </span>
          </div>
        </form>
        {metadata && <AgentTokens hosts={metadata.agent_hosts} tokens={metadata.agent_tokens} onChanged={async () => {
          setMetadata(await request<PublicSettings>("/api/settings"));
        }} />}
        <section className="form-card">
          <h2>Đổi mật khẩu</h2>
          <p>Đổi mật khẩu sẽ kết thúc tất cả phiên đăng nhập.</p>
          <form onSubmit={password}>
            <div className="form-grid">
              {[
                ["current", "Mật khẩu hiện tại"],
                ["new", "Mật khẩu mới"],
                ["repeat", "Nhập lại mật khẩu mới"],
              ].map(([key, label]) => (
                <label className="form-field" key={key}>
                  {label}
                  <input
                    type="password"
                    name={key}
                    required
                    maxLength={256}
                    autoComplete={
                      key === "current" ? "current-password" : "new-password"
                    }
                  />
                </label>
              ))}
            </div>
            <button className="btn btn-primary" disabled={passwordBusy}>
              Đổi mật khẩu
            </button>
            <p role="status">{passwordFeedback}</p>
          </form>
        </section>
      </main>
    </div>
  );
}
