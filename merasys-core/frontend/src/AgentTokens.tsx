import { useRef, useState } from "react";
import { request, message } from "./api";

type Row = { id: number; host: string; token: string; saved: boolean; savedHost?: string };
export function AgentTokens({ hosts, tokens, onChanged }: { hosts: string[]; tokens: Record<string, string>; onChanged: () => Promise<void> }) {
  const nextId = useRef(hosts.length);
  const [rows, setRows] = useState<Row[]>(hosts.map((host, id) => ({ id, host, token: tokens[host] || "", saved: true, savedHost: host })));
  const [busy, setBusy] = useState(false), [feedback, setFeedback] = useState("");
  const [bulk, setBulk] = useState("");
  const [installCommand, setInstallCommand] = useState("");
  function update(id: number, patch: Partial<Row>) { setRows(v => v.map(row => row.id === id ? { ...row, ...patch } : row)); }
  async function refreshHosts() {
    try { await onChanged(); } catch { setFeedback(v => v + " Không tải lại được danh sách IP; tải lại trang để kiểm tra."); }
  }
  async function save(row: Row, generate: boolean) {
    const host = row.host.trim();
    if (busy || !host) return;
    if (rows.some(r => r.id !== row.id && r.host.trim() === host)) { setFeedback("IP này đã có trong bảng. Hãy sửa dòng tương ứng."); return; }
    const previous_host = row.saved ? row.savedHost : undefined;
    const moving = previous_host !== undefined && previous_host !== host;
    const replace = row.saved || hosts.includes(host);
    if (replace && !confirm(moving ? `Chuyển token từ ${previous_host} sang ${host}? IP cũ sẽ không còn được cấp quyền. Cập nhật IP/token trong cấu hình agent và khai báo Sheet tương ứng.` : `Đổi token của ${host}? Bạn cần cập nhật token trên agent tương ứng.`)) return;
    if (!generate && !/^[A-Za-z0-9_-]{32,256}$/.test(row.token.trim())) { setFeedback("Token cần 32–256 ký tự chữ/số/_/-. Hoặc bấm Tạo token để tạo tự động."); return; }
    setBusy(true); setFeedback("");
    try {
      let token = row.token.trim();
      if (generate) {
        const result = await request<{ token: string }>("/api/settings/agent-token", { method: "POST", body: JSON.stringify({ host, replace, previous_host }) });
        token = result.token;
      } else {
        await request(`/api/settings/agent-token/${encodeURIComponent(host)}`, { method: "PUT", body: JSON.stringify({ token, replace, previous_host }) });
      }
      update(row.id, { host, token, saved: true, savedHost: host });
      setFeedback(`Đã lưu token cho ${host}. Sao chép vào cấu hình agent; bạn có thể sửa hoặc sao chép lại bất cứ lúc nào.`);
      await refreshHosts();
    } catch (e) { setFeedback(message(e)); } finally { setBusy(false); }
  }
  async function remove(row: Row) {
    if (busy) return;
    if (!row.saved) { setRows(v => v.filter(r => r.id !== row.id)); return; }
    if (!confirm(`Xóa token của ${row.savedHost}? Agent này sẽ không gửi được dữ liệu cho đến khi được cấp token mới.`)) return;
    setBusy(true); setFeedback("");
    try {
      await request(`/api/settings/agent-token/${encodeURIComponent(row.savedHost || row.host)}`, { method: "DELETE" });
      setRows(v => v.filter(r => r.id !== row.id)); setFeedback(`Đã xóa token của ${row.host}.`);
      await refreshHosts();
    } catch (e) { setFeedback(message(e)); } finally { setBusy(false); }
  }
  async function copyText(text: string, success: string) {
    let copied = false;
    try { await navigator.clipboard.writeText(text); copied = true; } catch {
      // Clipboard API is unavailable on many private-network HTTP deployments.
      const input = document.createElement("textarea");
      input.value = text;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      const previous = document.activeElement;
      try { input.select(); copied = document.execCommand("copy"); } catch { /* Offer manual copy below. */ }
      finally { input.remove(); if (previous instanceof HTMLElement) previous.focus(); }
    }
    setFeedback(copied ? success : "Trình duyệt không cho sao chép tự động. Hãy chọn nội dung đang hiển thị và sao chép thủ công.");
  }
  async function copyInstall(row: Row) {
    if (!row.savedHost || row.host.trim() !== row.savedHost) return;
    if (row.token !== tokens[row.savedHost]) { setFeedback("Lưu token trước khi sao chép lệnh cài."); return; }
    const quote = (value: string) => "'" + value.replaceAll("'", "'\"'\"'") + "'";
    const command = `curl -fsSL ${quote(location.origin + '/agent/install.sh')} | sudo bash -s -- --url ${quote(location.origin)} --server ${quote(row.savedHost)} --token ${quote(row.token)}`;
    setInstallCommand(command);
    await copyText(command, `Đã sao chép lệnh cài agent cho ${row.savedHost}. Dán và chạy trên server đó; không cần nhập lại URL/IP/token.`);
  }
  async function importBulk() {
    if (busy) return;
    let tokens: Record<string, string>;
    try {
      const value: unknown = JSON.parse(bulk);
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error('Cần object JSON dạng {"IP":"token"}.');
      tokens = value as Record<string, string>;
      if (Object.values(tokens).some(t => typeof t !== "string" || !/^[A-Za-z0-9_-]{32,256}$/.test(t))) throw new Error("Mỗi token cần 32–256 ký tự chữ/số/_/-.");
    } catch (e) { setFeedback(message(e)); return; }
    if (!confirm(`Thay toàn bộ danh sách bằng ${Object.keys(tokens).length} token từ JSON? Các IP không có trong JSON sẽ bị xóa, các dòng chưa lưu trong bảng sẽ bị bỏ.`)) return;
    setBusy(true); setFeedback("");
    try {
      await request("/api/settings", { method: "PUT", body: JSON.stringify({ values: { agent_tokens: tokens }, clear: [] }) }, 45000);
      setRows(Object.keys(tokens).map(host => ({ id: nextId.current++, host, token: tokens[host], saved: true, savedHost: host })));
      setBulk(""); setFeedback("Đã nhập danh sách token. Bạn có thể sửa và sao chép từng dòng.");
      await refreshHosts();
    } catch (e) { setFeedback(message(e)); } finally { setBusy(false); }
  }
  return <section className="form-card"><h2>Token agent theo IP</h2><p>Có thể sửa IP và token trực tiếp trong bảng, rồi bấm Lưu IP / token. Hoặc bấm Tạo token để tạo tự động. Mỗi dòng được lưu riêng, không cần bấm Lưu cấu hình.</p><div className="agent-token-table"><table><thead><tr><th>IP server</th><th>Token</th><th>Thao tác</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><input aria-label={`IP server dòng ${row.id + 1}`} value={row.host} disabled={busy} placeholder="10.9.3.239" onChange={e => update(row.id, { host: e.target.value })} /></td><td><input aria-label={`Token của ${row.host || 'máy chủ mới'}`} value={row.token} disabled={busy} placeholder={row.saved ? "Nhập token để thay giá trị đã lưu" : "Nhập token hoặc tạo tự động"} autoComplete="off" spellCheck={false} maxLength={256} onChange={e => update(row.id, { token: e.target.value })} /></td><td><div className="agent-token-actions"><button className="btn btn-primary" disabled={busy || !row.host.trim() || !row.token.trim()} onClick={() => void save(row, false)}>Lưu IP / token</button><button className="btn btn-secondary" disabled={busy || !row.host.trim()} onClick={() => void save(row, true)}>{row.saved ? "Tạo/đổi token" : "Tạo token"}</button><button className="btn btn-secondary" disabled={busy || !row.token} onClick={() => void copyText(row.token, `Đã sao chép token của ${row.host}.`)}>Sao chép</button><button className="btn btn-secondary" disabled={busy || !row.saved || row.host.trim() !== row.savedHost} title="Lưu IP trước khi sao chép lệnh cài. Lệnh chứa URL/IP/token đã lưu." onClick={() => void copyInstall(row)}>Sao chép lệnh cài agent</button><button className="btn mtr-danger" disabled={busy} onClick={() => void remove(row)}>Xóa</button></div></td></tr>)}{!rows.length && <tr><td colSpan={3}>Chưa có máy chủ. Bấm Thêm máy chủ để bắt đầu.</td></tr>}</tbody></table></div><button className="btn btn-secondary" disabled={busy || rows.length >= 1000} onClick={() => setRows(v => [...v, { id: nextId.current++, host: "", token: "", saved: false }])}>+ Thêm máy chủ</button><p role="status" aria-live="polite" className="agent-token-feedback">{feedback}</p>{installCommand && <details open className="agent-token-install"><summary>Lệnh cài agent</summary><pre tabIndex={0}>{installCommand}</pre><p>Yêu cầu Linux/systemd, sudo và curl. Lệnh chứa token, dùng cho đúng server. Cài lại bằng lệnh này sẽ cập nhật URL/IP/token và sao lưu cấu hình cũ.</p></details>}<details className="agent-token-advanced"><summary>Nhập nâng cao — JSON hàng loạt</summary><p>Thay toàn bộ danh sách token bằng JSON. Các IP không có trong JSON sẽ bị xóa.</p><textarea aria-label="Agent tokens JSON" value={bulk} disabled={busy} onChange={e => setBulk(e.target.value)} placeholder={'{"10.9.3.239":"token"}'} autoComplete="off" spellCheck={false} /><button className="btn btn-secondary" disabled={busy || !bulk.trim()} onClick={() => void importBulk()}>Nhập danh sách JSON</button></details></section>;
}
