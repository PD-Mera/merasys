import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { request, message, logout } from "./api";
import { Badge, Icon, Modal } from "./common";
import {
  absolute,
  ago,
  kind,
  labels,
  memberState,
  state,
  targetName,
  technicalName,
  typeName,
} from "./model";
import { Detail } from "./Detail";
import { TestAlert } from "./TestAlert";
import { Metrics } from "./Metrics";
import type { Snapshot, Target } from "./types";
type Tab = "all" | "service" | "server";
const rank = { DOWN: 0, UNKNOWN: 1, UP: 2, DISABLED: 3 };
const colors = [
  ["#eff6ff", "#1e40af", "#bfdbfe"],
  ["#f5f3ff", "#6d28d9", "#ddd6fe"],
  ["#ecfeff", "#155e75", "#a5f3fc"],
  ["#fdf2f8", "#9d174d", "#fbcfe8"],
  ["#eef2ff", "#3730a3", "#c7d2fe"],
  ["#f0fdfa", "#115e59", "#99f6e4"],
];
function tag(value: string, category: string) {
  let hash = 0;
  for (const c of `${category}:${value}`)
    hash = (Math.imul(hash, 31) + c.codePointAt(0)!) >>> 0;
  const [background, color, borderColor] = colors[hash % colors.length];
  return { background, color, borderColor };
}
export function Dashboard() {
  const [data, setData] = useState<Snapshot | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [updated, setUpdated] = useState<string | null>(null);
  const inFlight = useRef(false);
  const [clock, setClock] = useState(Date.now());
  const [tab, setTab] = useState<Tab>("all"),
    [host, setHost] = useState(""),
    [query, setQuery] = useState(""),
    [project, setProject] = useState(""),
    [status, setStatus] = useState("");
  const [limit, setLimit] = useState(40),
    [expanded, setExpanded] = useState<Set<number>>(new Set()),
    [selected, setSelected] = useState<Set<number>>(new Set());
  const [detailId, setDetailId] = useState<number | null>(null),
    [testAlert, setTestAlert] = useState(false);
  const [archiveIds, setArchiveIds] = useState<number[] | null>(null),
    [archiving, setArchiving] = useState(false),
    [archiveError, setArchiveError] = useState(""),
    [feedback, setFeedback] = useState("");
  const [retryBusy, setRetryBusy] = useState(false),
    [retryFeedback, setRetryFeedback] = useState("");
  const pane = useRef<HTMLDivElement>(null),
    sentinel = useRef<HTMLDivElement>(null),
    checkAll = useRef<HTMLInputElement>(null);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      const next = await request<Snapshot>("/api/status", { signal });
      if (
        !Array.isArray(next.targets) ||
        !Array.isArray(next.health) ||
        !Array.isArray(next.incidents)
      )
        throw new Error("Dữ liệu phản hồi không hợp lệ.");
      if (signal?.aborted) return;
      setData(next);
      setUpdated(new Date().toISOString());
      setError("");
      setSelected(
        (previous) =>
          new Set(
            [...previous].filter((id) =>
              next.targets.some((t) => t.id === id && t.status === "DISABLED"),
            ),
          ),
      );
    } catch (e) {
      if (!signal?.aborted) setError(message(e));
    } finally {
      inFlight.current = false;
      if (!signal?.aborted) setBusy(false);
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const poll = window.setInterval(
      () => void refresh(controller.signal),
      30000,
    );
    const tick = window.setInterval(() => setClock(Date.now()), 1000);
    const visible = () => {
      if (!document.hidden) void refresh(controller.signal);
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      controller.abort();
      clearInterval(poll);
      clearInterval(tick);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [refresh]);
  useEffect(() => {
    setLimit(40);
    if (pane.current) pane.current.scrollTop = 0;
  }, [tab, host, query, project, status]);
  const rows =
    data?.targets
      .filter(
        (t) =>
          (tab === "all" ||
            (tab === "server" ? kind(t) === "server" : kind(t) !== "server")) &&
          (!host || t.host === host) &&
          (!project || t.projects.includes(project)) &&
          (!status || state(t, data, clock) === status) &&
          (!query.trim() ||
            [
              targetName(t),
              technicalName(t),
              t.host,
              ...t.projects,
              ...t.owners,
              t.note,
              typeName(t),
            ]
              .join(" ")
              .toLocaleLowerCase("vi")
              .includes(query.trim().toLocaleLowerCase("vi"))),
      )
      .sort(
        (a, b) =>
          rank[state(a, data!, clock)] - rank[state(b, data!, clock)] ||
          a.host.localeCompare(b.host) ||
          targetName(a).localeCompare(targetName(b)),
      ) || [];
  const shown = rows.slice(0, limit),
    more = rows.length > limit;
  const eligible = shown
    .filter((t) => t.status === "DISABLED")
    .map((t) => t.id);
  const chosen = eligible.filter((id) => selected.has(id)).length;
  useEffect(() => {
    if (checkAll.current)
      checkAll.current.indeterminate = chosen > 0 && chosen < eligible.length;
  }, [chosen, eligible.length]);
  useEffect(() => {
    if (!more || archiving || !sentinel.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setLimit((v) => v + 40);
      },
      { root: pane.current, rootMargin: "120px" },
    );
    observer.observe(sentinel.current);
    return () => observer.disconnect();
  }, [more, archiving, limit, rows.length]);
  function select(ids: number[], checked: boolean) {
    const next = new Set(selected);
    ids.forEach((id) => (checked ? next.add(id) : next.delete(id)));
    if (next.size > 200) {
      setFeedback("Chỉ chọn tối đa 200 mục. Hãy thu hẹp bộ lọc.");
      return;
    }
    setSelected(next);
  }
  async function archive() {
    if (archiving || !archiveIds) return;
    setArchiving(true);
    setArchiveError("");
    try {
      const result = await request<{ archived_count: number }>(
        "/api/targets/archive",
        {
          method: "POST",
          headers: { "X-Monitor-Action": "archive-disabled" },
          body: JSON.stringify({ ids: archiveIds }),
        },
        20000,
      );
      setSelected(new Set());
      setArchiveIds(null);
      setFeedback(
        `Đã dọn ${result.archived_count} mục. Lịch sử được giữ nguyên.`,
      );
      await refresh();
    } catch (e) {
      setArchiveError(message(e));
    } finally {
      setArchiving(false);
    }
  }
  async function retry() {
    if (retryBusy) return;
    setRetryBusy(true);
    setRetryFeedback("Đang yêu cầu worker thử gửi lại…");
    try {
      const result = await request<{ message: string }>(
        "/api/notifications/retry",
        {
          method: "POST",
          headers: { "X-Monitor-Action": "retry-notification" },
        },
      );
      setRetryFeedback(result.message);
      await refresh();
    } catch (e) {
      setRetryFeedback(message(e));
    } finally {
      setRetryBusy(false);
    }
  }
  function reset() {
    setTab("all");
    setHost("");
    setQuery("");
    setProject("");
    setStatus("");
  }
  const targets = data?.targets || [],
    servers = targets.filter((t) => kind(t) === "server"),
    services = targets.filter((t) => kind(t) !== "server");
  const enabled = data
    ? services.filter((t) => state(t, data, clock) !== "DISABLED")
    : [];
  const count = (s: string) =>
    data ? enabled.filter((t) => state(t, data, clock) === s).length : 0;
  const zone = data?.display_timezone || "Asia/Bangkok";
  const at = (s: string | null) => absolute(s, zone);
  const detail = targets.find((t) => t.id === detailId);
  const filters = [
    host && `Máy chủ: ${host}`,
    project && `Dự án: ${project}`,
    status && `Trạng thái: ${labels[status]}`,
    query && `Từ khóa: ${query}`,
    tab !== "all" && `Loại: ${tab === "server" ? "Máy chủ" : "Dịch vụ"}`,
  ].filter(Boolean);
  return (
    <>
      <div
        className={`top-loader ${busy ? "active" : ""}`}
        aria-hidden="true"
      />
      <aside className="sidebar">
        <a className="brand" href="/">
          <Icon name="pulse" />
          <span className="brand-text">Merasys</span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav">
          <a href="#overview" onClick={reset}>
            <Icon name="grid" />
            <span className="nav-text">Tổng quan</span>
          </a>
          <a href="#servers" onClick={() => setTab("server")}>
            <Icon name="server" />
            <span className="nav-text">Máy chủ</span>
            <span className="count">{servers.length}</span>
          </a>
          <a href="#services" onClick={() => setTab("service")}>
            <Icon name="box" />
            <span className="nav-text">Dịch vụ</span>
            <span className="count">{services.length}</span>
          </a>
          <a href="#incidents">
            <Icon name="bell" />
            <span className="nav-text">Sự cố</span>
            <span className="count alert">{data?.incidents.length || 0}</span>
          </a>
          <a href="/settings">
            <Icon name="sliders" />
            <span className="nav-text">Cấu hình</span>
          </a>
        </nav>
        <div className="sidebar-footer">GIÁM SÁT HẠ TẦNG</div>
      </aside>
      <main id="overview">
        <header className="topbar">
          <div>
            <span className="eyebrow">HỆ THỐNG GIÁM SÁT</span>
            <p>
              {new Date(clock).toLocaleDateString("vi-VN", {
                weekday: "long",
                day: "2-digit",
                month: "long",
                year: "numeric",
                timeZone: zone,
              })}
            </p>
          </div>
          <div className={`live ${error ? "live-error" : "live-ok"}`}>
            <span className="dot" />
            {error
              ? "MẤT KẾT NỐI API"
              : busy && !data
                ? "ĐANG KẾT NỐI…"
                : "ĐANG KẾT NỐI"}
          </div>
        </header>
        <div className="page-heading">
          <div>
            <h1>Tổng quan hệ thống</h1>
            <p>Theo dõi hạ tầng và dịch vụ của bạn</p>
          </div>
          <div className="page-actions">
            <a className="btn btn-secondary" href="/settings">
              Cấu hình
            </a>
            <button
              className="btn btn-secondary"
              onClick={() =>
                void logout().catch((e) => setFeedback(message(e)))
              }
            >
              Đăng xuất
            </button>
            {data?.sheet_url && (
              <a
                className="btn btn-secondary"
                href={data.sheet_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Mở khai báo ↗
              </a>
            )}
            <button
              className="btn btn-secondary"
              onClick={() => setTestAlert(true)}
            >
              <Icon name="send" />
              Thử cảnh báo
            </button>
            <button
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void refresh()}
            >
              <Icon name="refresh" />
              {busy ? "Đang cập nhật…" : "Làm mới"}
            </button>
          </div>
        </div>
        {error && (
          <div className="banner" role="alert">
            {error}{" "}
            {data
              ? "Đang hiển thị dữ liệu gần nhất; trạng thái quá hạn được đánh dấu Chưa rõ."
              : "Kiểm tra API và kết nối backend."}
          </div>
        )}
        <section className="metrics">
          {[
            [
              "Máy chủ",
              data ? servers.length : "—",
              data
                ? `${servers.filter((t) => state(t, data, clock) === "UP").length} đang kết nối · ${servers.length} tổng cộng`
                : "Đang lấy dữ liệu…",
              "server",
            ],
            [
              "Dịch vụ giám sát",
              data ? enabled.length : "—",
              `${enabled.filter((t) => kind(t) === "compose").length} Compose đang giám sát`,
              "box",
            ],
            [
              "Dịch vụ hoạt động",
              data ? `${count("UP")} / ${enabled.length}` : "—",
              `${count("DOWN")} gián đoạn · ${count("UNKNOWN")} chưa rõ`,
              "pulse",
            ],
            [
              "Sự cố đang mở",
              data ? data.incidents.length : "—",
              data?.incidents.length
                ? "Cần kiểm tra và xử lý"
                : data
                  ? "Không có sự cố đang mở"
                  : "Đang lấy dữ liệu…",
              "bell",
            ],
          ].map(([label, value, hint, icon]) => (
            <article className="metric" key={String(label)}>
              <div className="metric-top">
                <span>{label}</span>
                <Icon name={String(icon)} />
              </div>
              <div className="metric-value">{value}</div>
              <div className="metric-bottom">{hint}</div>
            </article>
          ))}
        </section>
        <section className="server-section" id="servers">
          <div className="section-heading">
            <h2>
              Máy chủ <span className="index">{servers.length} máy chủ</span>
            </h2>
            <small>Chọn máy chủ để lọc dịch vụ</small>
          </div>
          <div className="server-grid">
            {data &&
              servers.map((t) => {
                const children = enabled.filter((c) => c.host === t.host),
                  up = children.filter(
                    (c) => state(c, data, clock) === "UP",
                  ).length,
                  percent = children.length
                    ? Math.round((up / children.length) * 100)
                    : 0;
                const color =
                  state(t, data, clock) === "DOWN"
                    ? "var(--red)"
                    : children.some((c) => state(c, data, clock) === "DOWN")
                      ? "var(--amber)"
                      : "var(--green)";
                return (
                  <button
                    className={`server-card ${host === t.host ? "selected" : ""}`}
                    key={t.id}
                    type="button"
                    aria-pressed={host === t.host}
                    onClick={() => {
                      setHost((v) => (v === t.host ? "" : t.host));
                      setTab("service");
                    }}
                  >
                    <div className="server-card-header">
                      <div className="server-badge-host">
                        <span className="server-icon">
                          <Icon name="server" />
                        </span>
                        <span className="server-name mono">{t.host}</span>
                      </div>
                      <Badge status={state(t, data, clock)} />
                    </div>
                    <div className="server-projects">
                      {t.projects.join(" · ") || "Hạ tầng dùng chung"}
                    </div>
                    <div className="server-progress-wrap">
                      <div className="server-progress-info">
                        <span>
                          {children.length
                            ? `${up}/${children.length} dịch vụ UP`
                            : "Chưa có dịch vụ đang giám sát"}
                        </span>
                        <span>{children.length ? `${percent}%` : "—"}</span>
                      </div>
                      <div className="progress-track">
                        <div
                          className="progress-fill"
                          style={{ width: `${percent}%`, background: color }}
                        />
                      </div>
                    </div>
                    <div className="server-card-footer">
                      <span title={at(t.checked_at)}>{ago(t.checked_at)}</span>
                      <span>
                        {host === t.host ? "✓ Đang lọc" : "Lọc host ↗"}
                      </span>
                    </div>
                  </button>
                );
              })}
            {!servers.length && (
              <div className="empty">
                {data
                  ? "Chưa có máy chủ. Khai báo IP trên Google Sheet để bắt đầu."
                  : "Đang tải máy chủ…"}
              </div>
            )}
          </div>
        </section>
        <div className="content-grid">
          <section className="panel" id="services">
            <div className="panel-heading">
              <h2>Danh sách giám sát</h2>
              <span className="small-pill">{rows.length} mục</span>
            </div>
            <div className="tabs" role="tablist" aria-label="Loại đối tượng">
              {(
                [
                  ["all", "Tất cả", targets.length],
                  ["service", "Dịch vụ", services.length],
                  ["server", "Máy chủ", servers.length],
                ] as const
              ).map(([key, label, size]) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={tab === key}
                  className={`tab ${tab === key ? "active" : ""}`}
                  onClick={() => setTab(key)}
                >
                  {label} <span className="tab-pill">{size}</span>
                </button>
              ))}
            </div>
            <div className="filters">
              <input
                className="filter-search"
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Tìm tên, IP, dự án, phụ trách…"
                aria-label="Tìm đối tượng giám sát"
              />
              <select
                className="filter-select"
                aria-label="Lọc trạng thái"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="">Tất cả trạng thái</option>
                {["UP", "DOWN", "UNKNOWN", "DISABLED"].map((s) => (
                  <option value={s} key={s}>
                    {labels[s]}
                  </option>
                ))}
              </select>
              <select
                className="filter-select"
                aria-label="Lọc dự án"
                value={project}
                onChange={(e) => setProject(e.target.value)}
              >
                <option value="">Tất cả dự án</option>
                {[
                  ...new Set([
                    ...targets.flatMap((t) => t.projects),
                    ...(project ? [project] : []),
                  ]),
                ]
                  .sort((a, b) => a.localeCompare(b, "vi"))
                  .map((p) => (
                    <option key={p}>{p}</option>
                  ))}
              </select>
            </div>
            {!!filters.length && (
              <div className="filter-active-bar">
                <span>{filters.join(" · ")}</span>
                <button className="btn-clear-filters" onClick={reset}>
                  Xóa bộ lọc
                </button>
              </div>
            )}
            <div className="mtr-tools">
              <span>
                {selected.size
                  ? `Đã chọn ${selected.size} mục`
                  : "Chưa chọn mục nào"}
              </span>
              <span className="muted">Chỉ dọn mục đã tắt</span>
              <button
                className="btn mtr-danger"
                disabled={!selected.size || archiving || !!error}
                onClick={() => {
                  setArchiveIds([...selected]);
                  setArchiveError("");
                }}
              >
                Xóa mục đã chọn
              </button>
            </div>
            {feedback && (
              <p className="mtr-feedback" role="status">
                {feedback}
              </p>
            )}
            <div
              className="table-wrap"
              id="mtr-scroll"
              ref={pane}
              tabIndex={0}
              role="region"
              aria-label="Danh sách giám sát có cuộn và tải thêm"
            >
              <table>
                <thead>
                  <tr>
                    <th className="mtr-select">
                      <input
                        type="checkbox"
                        className="mtr-check"
                        ref={checkAll}
                        aria-label="Chọn mục đã tắt trong các dòng đã tải"
                        disabled={!eligible.length || archiving}
                        checked={
                          eligible.length > 0 && chosen === eligible.length
                        }
                        onChange={(e) => select(eligible, e.target.checked)}
                      />
                    </th>
                    <th>Đối tượng</th>
                    <th>Máy chủ</th>
                    <th>Dự án</th>
                    <th>Phụ trách</th>
                    <th>Trạng thái</th>
                    <th className="table-hide">Cập nhật</th>
                    <th>
                      <span className="sr-only">Chi tiết</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data &&
                    shown.map((t) => (
                      <Fragment key={t.id}>
                        <tr className="mtr-entry">
                          <td className="mtr-select">
                            <input
                              className="mtr-check"
                              type="checkbox"
                              checked={selected.has(t.id)}
                              disabled={t.status !== "DISABLED" || archiving}
                              aria-label={`Chọn ${targetName(t)}`}
                              onChange={(e) => select([t.id], e.target.checked)}
                            />
                          </td>
                          <td>
                            <button
                              className="entity"
                              onClick={() => setDetailId(t.id)}
                            >
                              <span className={`entity-icon ${kind(t)}`}>
                                <Icon
                                  name={
                                    kind(t) === "server"
                                      ? "server"
                                      : kind(t) === "compose"
                                        ? "layers"
                                        : "box"
                                  }
                                />
                              </span>
                              <span className="entity-body">
                                <span className="entity-name">
                                  {targetName(t)}
                                </span>
                                <span className="entity-type">
                                  <span className="rabbitmq-label">
                                    {typeName(t)}
                                  </span>
                                  <Metrics target={t} data={data} />
                                </span>
                              </span>
                            </button>
                            {kind(t) === "compose" && (
                              <button
                                className="mtr-compose-toggle"
                                aria-expanded={expanded.has(t.id)}
                                aria-controls={`members-${t.id}`}
                                onClick={() =>
                                  setExpanded((v) => {
                                    const next = new Set(v);
                                    if (next.has(t.id)) next.delete(t.id);
                                    else next.add(t.id);
                                    return next;
                                  })
                                }
                              >
                                {expanded.has(t.id) ? "▾" : "▸"}{" "}
                                {t.compose_services.length} service{" "}
                                {t.compose_services.some(
                                  (m) => memberState(t, m, data) === "DOWN",
                                ) && (
                                  <span className="bad">
                                    ·{" "}
                                    {
                                      t.compose_services.filter(
                                        (m) =>
                                          memberState(t, m, data) === "DOWN",
                                      ).length
                                    }{" "}
                                    lỗi
                                  </span>
                                )}
                              </button>
                            )}
                          </td>
                          <td>
                            <span
                              className="host-badge mono"
                              style={tag(t.host, "host")}
                            >
                              {t.host}
                            </span>
                          </td>
                          <td>
                            <div
                              className="projects"
                              title={t.projects.join(", ")}
                            >
                              {t.projects.slice(0, 2).map((p) => (
                                <span
                                  className="project"
                                  key={p}
                                  style={tag(p, "project")}
                                >
                                  {p}
                                </span>
                              ))}
                              {t.projects.length > 2 && (
                                <span className="project more">
                                  +{t.projects.length - 2}
                                </span>
                              )}
                              {!t.projects.length && "—"}
                            </div>
                          </td>
                          <td className="mtr-owner">
                            <div className="mtr-owners">
                              {t.owners.map((p) => (
                                <span
                                  className="mtr-owner-badge"
                                  key={p}
                                  style={tag(p, "owner")}
                                >
                                  {p}
                                </span>
                              ))}
                              {!t.owners.length && "—"}
                            </div>
                          </td>
                          <td>
                            <Badge status={state(t, data, clock)} />
                          </td>
                          <td
                            className="table-hide last-seen"
                            title={at(t.checked_at)}
                          >
                            {ago(t.checked_at)}
                          </td>
                          <td>
                            <button
                              className="row-chevron"
                              aria-label={`Chi tiết ${targetName(t)}`}
                              onClick={() => setDetailId(t.id)}
                            >
                              ›
                            </button>
                          </td>
                        </tr>
                        {kind(t) === "compose" && expanded.has(t.id) && (
                          <tr className="mtr-child-row" id={`members-${t.id}`}>
                            <td colSpan={8}>
                              <div className="mtr-members">
                                {t.compose_services.map((m) => (
                                  <div className="mtr-member" key={m.name}>
                                    <div className="mtr-member-head">
                                      <strong>{m.name}</strong>
                                      <Badge status={memberState(t, m, data)} />
                                    </div>
                                    <p>{m.reason || "Chưa có dữ liệu"}</p>
                                  </div>
                                ))}
                                {!t.compose_services.length && (
                                  <p>
                                    Chưa phát hiện service. Chờ agent cập nhật.
                                  </p>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  {!shown.length && (
                    <tr>
                      <td colSpan={8}>
                        <div className="empty">
                          {data
                            ? targets.length
                              ? "Không tìm thấy kết quả. Thử đổi bộ lọc."
                              : "Chưa có đối tượng giám sát. Kiểm tra cấu hình Sheet."
                            : "Đang tải dữ liệu…"}
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="mtr-sentinel" ref={sentinel}>
                {more
                  ? "Cuộn xuống để hiển thị thêm 40 mục"
                  : "Đã hiển thị hết kết quả"}
              </div>
            </div>
            <div className="table-footer">
              <span>
                Đã tải {shown.length}/{rows.length} kết quả · Tổng{" "}
                {targets.length} mục
              </span>
              {more && (
                <button
                  className="btn btn-secondary"
                  disabled={archiving}
                  onClick={() => setLimit((v) => v + 40)}
                >
                  Xem thêm 40 mục
                </button>
              )}
            </div>
          </section>
          <div className="sidebar-monitor">
            <details className="panel monitor-panel" id="incidents" open>
              <summary className="panel-heading">
                <h2>Sự cố đang mở</h2>
                <span className="alert-count">
                  {data?.incidents.length || 0}
                </span>
              </summary>
              <div className="incidents">
                {data?.incidents
                  .slice()
                  .sort(
                    (a, b) => Date.parse(b.opened_at) - Date.parse(a.opened_at),
                  )
                  .map((i, index) => (
                    <article className="incident" key={index}>
                      <div className="incident-head">
                        <span className="incident-dot" />
                        <strong className="incident-title">{i.title}</strong>
                      </div>
                      <pre className="incident-detail mono">{i.detail}</pre>
                      <div className="incident-meta">
                        <time title={at(i.opened_at)}>
                          Mở {ago(i.opened_at)}
                        </time>
                      </div>
                    </article>
                  ))}
                {data && !data.incidents.length && (
                  <div className="calm">
                    <strong>Chưa có sự cố đang mở</strong>
                    <p>Hiện không có sự cố nào cần xử lý lúc này.</p>
                  </div>
                )}
              </div>
            </details>
            <section className="panel">
              <div className="panel-heading">
                <h2>Sức khỏe hệ thống</h2>
              </div>
              <div className="health-list">
                {data?.health
                  .filter((h) => !h.component.startsWith("host:"))
                  .map((h) => (
                    <Fragment key={h.component}>
                      <div className="health-row">
                        <div>
                          <div className="health-name">
                            {(
                              {
                                sheet: "Google Sheet",
                                "alert-worker": "Cảnh báo Telegram",
                                "rabbitmq-worker": "Kiểm tra RabbitMQ",
                              } as Record<string, string>
                            )[h.component] || h.component}
                          </div>
                          <div className="health-time" title={at(h.last_ok_at)}>
                            {ago(h.last_ok_at)}
                          </div>
                        </div>
                        <Badge
                          status={
                            h.last_ok_at &&
                            clock - Date.parse(h.last_ok_at) >
                              (h.stale_after_seconds || 600) * 1000
                              ? "STALE"
                              : h.status
                          }
                        />
                      </div>
                      {h.error && (
                        <div className="health-error mono">{h.error}</div>
                      )}
                    </Fragment>
                  ))}
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>Hàng đợi thông báo</h2>
                <strong>{data?.pending_notifications || 0}</strong>
              </div>
              <div className="queue-content">
                <div className="queue-toolbar">
                  <small>5 tin đầu · Theo thứ tự gửi</small>
                  <button
                    className="btn btn-secondary"
                    disabled={
                      retryBusy || !data?.notification_queue.length || !!error
                    }
                    onClick={() => void retry()}
                  >
                    Gửi ngay tin đầu
                  </button>
                </div>
                <div className="queue-items">
                  {data?.notification_queue.map((item, index) => (
                    <article className="queue-item" key={item.id}>
                      <strong>
                        #{item.id} · {item.title}
                      </strong>
                      <small>
                        {index === 0 && "Đầu hàng đợi · "}Đã thử {item.attempts}{" "}
                        lần · Tạo {ago(item.created_at)}
                      </small>
                      <small>Thử lại: {at(item.next_attempt_at)}</small>
                      {item.last_error && (
                        <small className="queue-error">{item.last_error}</small>
                      )}
                    </article>
                  ))}
                  {data && !data.notification_queue.length && (
                    <small>Không có thông báo chờ gửi.</small>
                  )}
                </div>
                <p role="status">{retryFeedback}</p>
              </div>
            </section>
          </div>
        </div>
        <footer className="footer">
          <span>
            {updated
              ? `${error ? "Dữ liệu cũ · " : ""}Đồng bộ giao diện ${ago(updated)}`
              : "Chưa nhận dữ liệu"}
          </span>
          <span>Chu kỳ tự cập nhật: 30s · Múi giờ: {zone}</span>
        </footer>
      </main>
      {detail && data && (
        <Detail
          key={detail.id}
          target={detail}
          data={data}
          close={() => setDetailId(null)}
        />
      )}
      <TestAlert
        open={testAlert}
        close={() => setTestAlert(false)}
        zone={zone}
      />
      {archiveIds && (
        <Modal
          title="Dọn các mục đã tắt?"
          close={() => setArchiveIds(null)}
          busy={archiving}
        >
          <p>
            Chỉ ẩn khỏi danh sách, giữ lịch sử và Google Sheet. Bật lại trên
            Sheet thì mục sẽ xuất hiện lại.
          </p>
          <ul className="mtr-modal-list">
            {targets
              .filter((t) => archiveIds.includes(t.id))
              .map((t) => (
                <li key={t.id}>
                  {targetName(t)} · {t.host}
                </li>
              ))}
          </ul>
          <p className="form-error" role="alert">
            {archiveError}
          </p>
          <div className="mtr-modal-buttons">
            <button
              className="btn btn-secondary"
              disabled={archiving}
              onClick={() => setArchiveIds(null)}
            >
              Hủy
            </button>
            <button
              className="btn mtr-danger"
              disabled={archiving}
              onClick={() => void archive()}
            >
              Xác nhận xóa
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
