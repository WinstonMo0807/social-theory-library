"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { usePublicSession } from "./public-session-provider";

export function WorkReaderSessionRefresh({ loginRequired }: { loginRequired: boolean }) {
  const { state } = usePublicSession();
  const router = useRouter();
  const refreshed = useRef(false);

  useEffect(() => {
    // An expired access cookie can render public metadata before the shared
    // session bootstrap renews it. Reload server data once after recovery.
    if (loginRequired && state.status === "authenticated" && !refreshed.current) {
      refreshed.current = true;
      router.refresh();
    }
  }, [loginRequired, router, state.status]);

  return null;
}
