import { useState } from "react";
import type { FormEvent } from "react";
import { request, message } from "./api";
export function Auth({ registered: initial }: { registered: boolean }) {
  const [registered, setRegistered] = useState(initial);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    if (!registered && password !== form.get("repeat")) {
      setError("Hai mật khẩu không khớp.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await request(`/api/auth/${registered ? "login" : "register"}`, {
        method: "POST",
        body: JSON.stringify({
          username: String(form.get("username")).trim(),
          password,
        }),
      });
      location.replace("/");
    } catch (error) {
      setError(message(error));
      try {
        const state = await request<{
          registered: boolean;
          authenticated: boolean;
        }>("/api/auth/state");
        if (state.authenticated) location.replace("/");
        setRegistered(state.registered);
      } catch {
        /* Keep the submitted form available when the server is offline. */
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <main className="auth-card">
        <div className="brand">Merasys</div>
        <p>GIÁM SÁT HẠ TẦNG TẬP TRUNG</p>
        <h1>{registered ? "Đăng nhập" : "Tạo tài khoản quản trị"}</h1>
        <p>
          {registered
            ? "Đăng nhập để theo dõi hệ thống và thay đổi cấu hình."
            : "Tạo tài khoản duy nhất để bắt đầu thiết lập."}
        </p>
        <form onSubmit={submit}>
          <label>
            Tên đăng nhập
            <input
              name="username"
              required
              minLength={3}
              maxLength={64}
              autoComplete="username"
              pattern="[A-Za-z0-9_.@\-]+"
            />
          </label>
          <label>
            Mật khẩu
            <input
              name="password"
              type="password"
              required
              maxLength={256}
              autoComplete={registered ? "current-password" : "new-password"}
            />
          </label>
          {!registered && (
            <label>
              Nhập lại mật khẩu
              <input
                name="repeat"
                type="password"
                required
                maxLength={256}
                autoComplete="new-password"
              />
            </label>
          )}
          <button className="btn btn-primary" disabled={busy}>
            {busy
              ? "Đang xử lý…"
              : registered
                ? "Đăng nhập"
                : "Đăng ký và bắt đầu"}
          </button>
        </form>
        <p role="alert" className="form-error">
          {error}
        </p>
        <small>Merasys chỉ có một tài khoản quản trị.</small>
      </main>
    </div>
  );
}
