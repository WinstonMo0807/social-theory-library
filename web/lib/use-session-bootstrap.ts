"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { subscribeToSessionChanges } from "./api";
import {
  bootstrapSession,
  type SessionState,
} from "./session";

const initialState: SessionState = { status: "loading" };

export function useSessionBootstrap(allowedRoles?: readonly string[]) {
  const [state, setState] = useState<SessionState>(initialState);
  const [attempt, setAttempt] = useState(0);
  const rolesKey = allowedRoles?.join("|") ?? "";
  const stableRoles = useMemo(
    () => rolesKey ? rolesKey.split("|") : undefined,
    [rolesKey],
  );

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeToSessionChanges(retry);
    const revalidateVisibleSession = () => {
      if (document.visibilityState === "visible") retry();
    };
    window.addEventListener("focus", revalidateVisibleSession);
    window.addEventListener("pageshow", revalidateVisibleSession);
    return () => {
      unsubscribe();
      window.removeEventListener("focus", revalidateVisibleSession);
      window.removeEventListener("pageshow", revalidateVisibleSession);
    };
  }, [retry]);

  useEffect(() => {
    let active = true;
    bootstrapSession({ allowedRoles: stableRoles }).then((nextState) => {
      if (active) setState(nextState);
    });
    return () => {
      active = false;
    };
  }, [attempt, stableRoles]);

  return { state, retry };
}
