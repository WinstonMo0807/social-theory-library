import { apiEndpoint, getApiBase, normalizePublicResourceUrl } from "./runtime-api";

export { getApiBase, normalizePublicResourceUrl };

let activeRefresh: Promise<string | null> | null = null;
const COOKIE_SESSION = "cookie-session";
const SESSION_HINT_KEY = "library_session_active";

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export function isAuthenticationError(reason: unknown) {
  return reason instanceof ApiRequestError && [401, 403].includes(reason.status);
}

export function clearStoredSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem("library_access_token");
  window.localStorage.removeItem("library_refresh_token");
  window.localStorage.removeItem("library_user");
  window.localStorage.removeItem(SESSION_HINT_KEY);
}

export function markSessionActive() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem("library_access_token");
  window.localStorage.removeItem("library_refresh_token");
  window.localStorage.removeItem("library_user");
  window.localStorage.setItem(SESSION_HINT_KEY, "1");
}

function csrfToken() {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function errorText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(errorText).filter(Boolean).join("；");
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .flatMap(([field, detail]) => {
        const text = errorText(detail);
        return text ? [`${field}：${text}`] : [];
      })
      .join("；");
  }
  return "";
}

async function refreshAccessToken() {
  if (typeof window === "undefined") return null;
  if (!activeRefresh) {
    activeRefresh = (async () => {
      let response: Response;
      try {
        response = await fetch(apiEndpoint("/auth/token/refresh/"), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(csrfToken() ? { "X-CSRFToken": csrfToken() } : {}),
          },
          credentials: "include",
          body: JSON.stringify({}),
        });
      } catch {
        throw new ApiRequestError("暂时无法连接认证服务，请稍后重试。", 0);
      }
      if ([401, 403].includes(response.status)) {
        clearStoredSession();
        return null;
      }
      if (!response.ok) {
        throw new ApiRequestError(`认证服务暂时不可用（${response.status}）。`, response.status);
      }
      markSessionActive();
      return COOKIE_SESSION;
    })()
      .finally(() => {
        activeRefresh = null;
      });
  }
  return activeRefresh;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
  allowRefresh = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token && token !== COOKIE_SESSION) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const method = (options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRFToken", csrf);
  }
  let response: Response;
  try {
    response = await fetch(apiEndpoint(path), {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      throw new ApiRequestError("请求已取消。", 0);
    }
    throw new ApiRequestError("无法连接书库服务，请检查网络后重试。", 0);
  }
  if (
    response.status === 401
    && token
    && !path.includes("/auth/token/refresh/")
    && allowRefresh
  ) {
    const nextToken = await refreshAccessToken();
    if (nextToken) {
      if (nextToken === COOKIE_SESSION) {
        headers.delete("Authorization");
      } else {
        headers.set("Authorization", `Bearer ${nextToken}`);
      }
      return apiRequest<T>(path, { ...options, headers }, nextToken, false);
    }
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const nested = payload?.error?.detail;
    const reasons = payload?.reasons ?? nested?.reasons;
    const detail = nested?.detail ?? payload?.detail ?? nested;
    const pieces = [errorText(detail), errorText(reasons)].filter(Boolean);
    throw new ApiRequestError(pieces.join("；") || `请求失败（${response.status}）`, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function apiStreamRequest(
  path: string,
  options: RequestInit = {},
  token?: string | null,
  allowRefresh = true,
): Promise<Response> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token && token !== COOKIE_SESSION) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const method = (options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRFToken", csrf);
  }
  let response: Response;
  try {
    response = await fetch(apiEndpoint(path), {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
    throw new ApiRequestError("无法连接书库服务，请检查网络后重试。", 0);
  }
  if (response.status === 401 && token && allowRefresh) {
    const nextToken = await refreshAccessToken();
    if (nextToken) {
      if (nextToken === COOKIE_SESSION) {
        headers.delete("Authorization");
      } else {
        headers.set("Authorization", `Bearer ${nextToken}`);
      }
      return apiStreamRequest(path, { ...options, headers }, nextToken, false);
    }
  }
  return response;
}

export type UploadProgress = {
  loaded: number;
  total: number;
};

export async function apiUpload<T>(
  path: string,
  body: FormData,
  token?: string | null,
  onProgress?: (progress: UploadProgress) => void,
  allowRefresh = true,
): Promise<T> {
  if (typeof window === "undefined") throw new Error("上传只能在浏览器中进行。");
  return new Promise<T>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", apiEndpoint(path), true);
    request.withCredentials = true;
    request.timeout = 0;
    if (token && token !== COOKIE_SESSION) {
      request.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    const csrf = csrfToken();
    if (csrf) request.setRequestHeader("X-CSRFToken", csrf);
    request.upload.onprogress = (event) => {
      onProgress?.({
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : body.get("file") instanceof File
          ? (body.get("file") as File).size
          : 0,
      });
    };
    request.onerror = () => reject(new ApiRequestError("上传连接中断，请检查网络后重试。", 0));
    request.onabort = () => reject(new ApiRequestError("上传已取消。", 0));
    request.onload = async () => {
      if (request.status === 401 && token && allowRefresh) {
        const nextToken = await refreshAccessToken();
        if (nextToken) {
          try {
            resolve(await apiUpload<T>(path, body, nextToken, onProgress, false));
          } catch (reason) {
            reject(reason);
          }
          return;
        }
      }
      let payload: unknown = {};
      try {
        payload = request.responseText ? JSON.parse(request.responseText) : {};
      } catch {
        payload = {};
      }
      if (request.status < 200 || request.status >= 300) {
        const record = payload && typeof payload === "object"
          ? payload as Record<string, unknown>
          : {};
        const error = record.error;
        const errorRecord = error && typeof error === "object"
          ? error as Record<string, unknown>
          : {};
        const nested = errorRecord.detail ?? error;
        const nestedRecord = nested && typeof nested === "object"
          ? nested as Record<string, unknown>
          : {};
        const detail = nestedRecord.detail ?? record.detail ?? nested;
        reject(new ApiRequestError(errorText(detail) || `上传失败（${request.status || "网络中断"}）`, request.status));
        return;
      }
      resolve(payload as T);
    };
    request.send(body);
  });
}

export async function apiBlob(
  pathOrUrl: string,
  token?: string | null,
  allowRefresh = true,
): Promise<Blob> {
  const headers = new Headers();
  if (token && token !== COOKIE_SESSION) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const url = /^https?:\/\//i.test(pathOrUrl)
    ? normalizePublicResourceUrl(pathOrUrl)
    : apiEndpoint(pathOrUrl);
  let response: Response;
  try {
    response = await fetch(url, { headers, credentials: "include" });
  } catch {
    throw new ApiRequestError("无法连接书库文件服务，请检查网络后重试。", 0);
  }
  if (response.status === 401 && token && allowRefresh) {
    const nextToken = await refreshAccessToken();
    if (nextToken) {
      return apiBlob(pathOrUrl, nextToken, false);
    }
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const nested = payload?.error?.detail;
    const detail = nested?.detail ?? payload?.detail ?? nested;
    throw new ApiRequestError(errorText(detail) || `图片读取失败（${response.status}）`, response.status);
  }
  return response.blob();
}

export function getStoredAccessToken() {
  if (typeof window === "undefined") return null;
  window.localStorage.removeItem("library_access_token");
  window.localStorage.removeItem("library_refresh_token");
  window.localStorage.removeItem("library_user");
  return window.localStorage.getItem(SESSION_HINT_KEY) ? COOKIE_SESSION : null;
}

export async function logoutCurrentSession() {
  if (typeof window === "undefined") return;
  const session = getStoredAccessToken();
  try {
    if (session) {
      await apiRequest<void>(
        "/auth/logout/",
        {
          method: "POST",
          body: JSON.stringify({}),
        },
        session,
        false,
      );
    }
  } catch {
    // Local cleanup must still happen when the server or network is unavailable.
  } finally {
    clearStoredSession();
  }
}
