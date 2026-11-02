import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { labels } from "./model";
export function Badge({ status }: { status: string }) {
  return (
    <span className={`state ${status in labels ? status : "UNKNOWN"}`}>
      <span className="dot" />
      {labels[status] || labels.UNKNOWN}
    </span>
  );
}
export function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    server: "M3 3h18v7H3z M3 14h18v7H3z M7 6h1 M7 17h1 M12 6h5 M12 17h5",
    box: "m12 3 9 5v8l-9 5-9-5V8l9-5 M12 13l9-5 M12 13 3 8 M12 13v8",
    layers: "m12 3 10 5-10 5L2 8l10-5 M2 12l10 5 10-5 M2 16l10 5 10-5",
    clock: "M12 7v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    refresh:
      "M20 7a9 9 0 0 0-15-2L2 8 M2 3v5h5 M4 17a9 9 0 0 0 15 2l3-3 M22 21v-5h-5",
    pulse: "M3 12h5l3-8 4 16 3-8h3",
    bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9 M9 21h6",
    grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    send: "m22 2-7 20-4-9-9-4L22 2 M11 13 22 2",
    sliders: "M5 3v7m0 4v7 M12 3v12m0 4v2 M19 3v2m0 4v12 M2 10h6m1 5h6m1-10h6",
  };
  return (
    <svg
      className="i"
      viewBox="0 0 24 24"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name] || paths.box} />
    </svg>
  );
}
export function Modal({
  title,
  children,
  close,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = `dialog-${title.replace(/\s/g, "-")}`;
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={heading}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) close();
      }}
    >
      <div className="detail-head">
        <h2 id={heading}>{title}</h2>
        <button
          className="close-btn"
          type="button"
          aria-label="Đóng"
          disabled={busy}
          onClick={close}
        >
          ×
        </button>
      </div>
      <div className="detail-body">{children}</div>
    </dialog>
  );
}
