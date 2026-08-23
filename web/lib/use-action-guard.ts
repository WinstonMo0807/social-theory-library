"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Serializes user-triggered mutations inside one mounted surface.
 * The ref is updated synchronously, before React can schedule a render, so a
 * second pointer or keyboard event in the same frame cannot submit twice.
 */
export function useActionGuard() {
  const actionInFlightRef = useRef<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const startAction = useCallback((key: string) => {
    if (actionInFlightRef.current) return false;
    actionInFlightRef.current = key;
    setPendingAction(key);
    return true;
  }, []);

  const finishAction = useCallback((key: string) => {
    if (actionInFlightRef.current !== key) return;
    actionInFlightRef.current = null;
    setPendingAction(null);
  }, []);

  return { actionInFlightRef, pendingAction, startAction, finishAction };
}
