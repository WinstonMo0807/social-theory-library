"use client";

import { createContext, use } from "react";
import type { SessionUser } from "./session";

// AdminShell owns authentication and revalidation. Its children consume the
// same verified user instead of independently requesting another /auth/me/.
export const AdminSessionContext = createContext<SessionUser | null>(null);

export function useAdminSession() {
  return use(AdminSessionContext);
}

/** Display/request gating only; the API remains the permission authority. */
export function hasAdminCapability(user: SessionUser | null, capability: string) {
  if (!user) return false;
  if (user.capabilities !== undefined) return user.capabilities.includes(capability);
  // Do not infer owner-only or future capabilities from the legacy role.
  return user.role === "admin" && ["can_view_audit_log", "can_view_system_status"].includes(capability);
}
