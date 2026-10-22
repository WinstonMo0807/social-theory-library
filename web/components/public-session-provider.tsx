"use client";

import { createContext, type ReactNode, useContext } from "react";
import { usePathname } from "next/navigation";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";

type PublicSessionValue = ReturnType<typeof useSessionBootstrap>;

const PublicSessionContext = createContext<PublicSessionValue | null>(null);

function isPublicSessionRoute(pathname: string) {
  // Shared appearance also belongs to the signed-in account in the back office.
  // AdminShell independently enforces its role/capability permissions.
  return !["/login", "/register", "/reset-password"].includes(pathname);
}

export function PublicSessionProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const session = useSessionBootstrap(undefined, isPublicSessionRoute(pathname));
  return <PublicSessionContext.Provider value={session}>{children}</PublicSessionContext.Provider>;
}

export function usePublicSession() {
  const value = useContext(PublicSessionContext);
  if (!value) throw new Error("PublicSessionProvider is missing.");
  return value;
}
