import {
  ApiRequestError,
  apiRequest,
  classifyClientError,
  clearStoredSession,
  getServerSessionCredential,
  markSessionActive,
  type ClientErrorCategory,
} from "./api";

export type SessionUser = {
  id: number;
  email: string;
  display_name: string;
  role: string;
  locale?: string;
  reading_preferences?: Record<string, unknown>;
  is_library_owner?: boolean;
  access_level?: "superadmin" | "admin" | "editor" | "reviewer" | "reader" | string;
  capabilities?: string[];
};

export type SessionStatus =
  | "unknown"
  | "loading"
  | "authenticated"
  | "unauthenticated"
  | "forbidden"
  | "temporary_error";

export type SessionState = {
  status: SessionStatus;
  user?: SessionUser;
  message?: string;
  errorCategory?: ClientErrorCategory;
};

export type BootstrapSessionOptions = {
  allowedRoles?: readonly string[];
};

export async function bootstrapSession(
  options: BootstrapSessionOptions = {},
): Promise<SessionState> {
  const credential = getServerSessionCredential();
  if (!credential) {
    return {
      status: "temporary_error",
      message: "登录状态只能在浏览器中验证。",
      errorCategory: "network_error",
    };
  }

  try {
    const user = await apiRequest<SessionUser>("/auth/me/", {}, credential);
    markSessionActive();
    if (options.allowedRoles && !options.allowedRoles.includes(user.role)) {
      return {
        status: "forbidden",
        user,
        message: "当前账户没有访问这个页面的权限。",
        errorCategory: "auth_403",
      };
    }
    return { status: "authenticated", user };
  } catch (reason) {
    const errorCategory = classifyClientError(reason, "auth");
    if (reason instanceof ApiRequestError && reason.status === 401) {
      clearStoredSession();
      return {
        status: "unauthenticated",
        message: "登录已过期，请重新登录。",
        errorCategory,
      };
    }
    if (reason instanceof ApiRequestError && reason.status === 403) {
      return {
        status: "forbidden",
        message: reason.message || "当前账户没有访问这个页面的权限。",
        errorCategory,
      };
    }
    return {
      status: "temporary_error",
      message: reason instanceof Error
        ? reason.message
        : "认证服务暂时不可用，请稍后重试。",
      errorCategory,
    };
  }
}
