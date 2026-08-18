"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { subscribeToSessionChanges } from "./api";
import {
  bootstrapSession,
  type SessionState,
} from "./session";

const initialState: SessionState = { status: "loading" };

export function useSessionBootstrap(allowedRoles?: readonly string[]) {
  const [state, setState] = useState<SessionState>(initialState);
  const [attempt, setAttempt] = useState(0);
  const stateRef = useRef<SessionState>(initialState);
  const backgroundRefreshRef = useRef(false);
  const lastValidationAtRef = useRef(0);
  const rolesKey = allowedRoles?.join("|") ?? "";
  const stableRoles = useMemo(
    () => rolesKey ? rolesKey.split("|") : undefined,
    [rolesKey],
  );

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const scheduleValidation = useCallback((background: boolean) => {
    const now = Date.now();
    // Focus/pageshow can fire repeatedly while a user is dragging a file or
    // switching between browser windows. Avoid turning that normal browser
    // behavior into a destructive remount of the current workspace.
    if (background && now - lastValidationAtRef.current < 30_000) return;
    lastValidationAtRef.current = now;
    backgroundRefreshRef.current = background;
    if (!background) setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }, []);

  const retry = useCallback(() => {
    scheduleValidation(false);
  }, [scheduleValidation]);

  useEffect(() => {
    // A storage change is an explicit cross-tab session event (including
    // logout), so it is authoritative. Visibility/pageshow checks remain
    // background probes and are deliberately non-destructive to uploads.
    const unsubscribe = subscribeToSessionChanges(() => scheduleValidation(false));
    const revalidateVisibleSession = () => {
      if (document.visibilityState === "visible") scheduleValidation(true);
    };
    document.addEventListener("visibilitychange", revalidateVisibleSession);
    window.addEventListener("pageshow", revalidateVisibleSession);
    return () => {
      unsubscribe();
      document.removeEventListener("visibilitychange", revalidateVisibleSession);
      window.removeEventListener("pageshow", revalidateVisibleSession);
    };
  }, [retry, scheduleValidation]);

  useEffect(() => {
    let active = true;
    const background = backgroundRefreshRef.current;
    backgroundRefreshRef.current = false;
    const previous = stateRef.current;
    bootstrapSession({ allowedRoles: stableRoles }).then((nextState) => {
      if (!active) return;
      lastValidationAtRef.current = Date.now();
      // A background 5xx/network response must not unmount an authenticated
      // upload, intake, or review workspace. A single background 401 can be
      // caused by refresh-token rotation while a long upload is in flight;
      // keep the workspace mounted and let the next protected action perform
      // the authoritative authentication check. Role revocation (403) still
      // replaces the state immediately.
      if (
        background
        && previous.status === "authenticated"
        && (nextState.status === "temporary_error" || nextState.status === "unauthenticated")
      ) return;
      setState(nextState);
    });
    return () => {
      active = false;
    };
  }, [attempt, stableRoles]);

  return { state, retry };
}
