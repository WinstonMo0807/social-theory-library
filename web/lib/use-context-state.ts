"use client";

import { useCallback, useState, type Dispatch, type SetStateAction } from "react";

type ContextState<T> = { key: string; value: T };

export function updateContextState<T>(current: ContextState<T>, key: string, update: SetStateAction<T>): ContextState<T> {
  if (current.key !== key) return current;
  const value = typeof update === "function" ? (update as (previous: T) => T)(current.value) : update;
  return Object.is(current.value, value) ? current : { key, value };
}

/** Reset only this component's transient state when its editing scope changes.
 * Late async callbacks retain their original key and cannot replace new data.
 */
export function useContextState<T>(key: string, initialValue: T): [T, Dispatch<SetStateAction<T>>] {
  const [state, setState] = useState<ContextState<T>>({ key, value: initialValue });
  const value = state.key === key ? state.value : initialValue;
  if (state.key !== key) setState({ key, value: initialValue });
  const update = useCallback<Dispatch<SetStateAction<T>>>(
    (next) => setState((current) => updateContextState(current, key, next)), [key],
  );
  return [value, update];
}
