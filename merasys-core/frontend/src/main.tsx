import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Auth } from "./Auth";
import { Dashboard } from "./Dashboard";
import { Settings } from "./Settings";
import { request, message } from "./api";
import "./dashboard.css";
import "./app.css";
function App() {
  const [auth, setAuth] = useState<{
      registered: boolean;
      authenticated: boolean;
    } | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void request<{ registered: boolean; authenticated: boolean }>(
      "/api/auth/state",
      { signal: controller.signal },
    )
      .then(setAuth)
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      });
    return () => controller.abort();
  }, []);
  if (error)
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>Không kết nối được máy chủ</h1>
          <p role="alert">{error}</p>
          <button className="btn btn-primary" onClick={() => location.reload()}>
            Thử lại
          </button>
        </div>
      </div>
    );
  if (!auth)
    return (
      <div className="auth-page" role="status">
        Đang kiểm tra tài khoản…
      </div>
    );
  if (!auth.authenticated) return <Auth registered={auth.registered} />;
  return location.pathname === "/settings" ? <Settings /> : <Dashboard />;
}
createRoot(document.getElementById("root")!).render(<App />);
