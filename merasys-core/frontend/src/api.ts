export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 15000,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const timer = window.setTimeout(abort, timeoutMs);
  try {
    const headers = new Headers(options.headers);
    headers.set("X-Merasys-Request", "1");
    headers.set("Accept", "application/json");
    if (options.body) headers.set("Content-Type", "application/json");
    const response = await fetch(path, {
      ...options,
      credentials: "same-origin",
      cache: "no-store",
      headers,
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 401 && !path.startsWith("/api/auth/"))
        location.replace("/");
      if (response.status === 409 && path === "/api/status")
        location.replace("/settings");
      throw new ApiError(
        response.status,
        typeof result.detail === "string"
          ? result.detail
          : `Yêu cầu không hợp lệ (HTTP ${response.status}).`,
      );
    }
    return result as T;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}
export function message(error: unknown): string {
  return error instanceof Error
    ? error.name === "AbortError"
      ? "Chưa nhận phản hồi đúng hạn. Kiểm tra kết quả trước khi thử lại."
      : error.message
    : "Không thực hiện được yêu cầu.";
}
export async function logout() {
  await request("/api/auth/logout", { method: "POST" });
  location.replace("/");
}
