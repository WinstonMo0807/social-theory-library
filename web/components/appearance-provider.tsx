"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { applyAppearance, appearanceKeys, defaultAppearance, readAppearance, storeAppearance, validAppearance, type Appearance } from "@/lib/appearance";
import { usePublicSession } from "./public-session-provider";

type AppearanceContextValue = { preferences: Appearance; dark: boolean; status: string; update: (patch: Partial<Appearance>) => void };
const AppearanceContext = createContext<AppearanceContextValue | null>(null);

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const { state: session } = usePublicSession();
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : null;
  const [preferences, setPreferences] = useState(defaultAppearance);
  const [dark, setDark] = useState(false);
  const [status, setStatus] = useState("外观设置保存在当前浏览器");
  const current = useRef(defaultAppearance);
  const change = useRef(0);
  const account = useRef<{ owner: string | null; controller: AbortController } | null>(null);
  const saves = useRef<Promise<void>>(Promise.resolve());
  const display = useCallback((value: Appearance) => {
    current.current = value;
    setPreferences(value);
    setDark(applyAppearance(value));
  }, []);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => { if (active) display(readAppearance()); });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const systemChanged = () => setDark(applyAppearance(current.current));
    const storageChanged = (event: StorageEvent) => {
      if (event.key !== null && !Object.values(appearanceKeys).some(key => key === event.key)) return;
      change.current += 1;
      display(readAppearance());
      setStatus("已应用本机的外观设置");
    };
    media.addEventListener("change", systemChanged);
    window.addEventListener("storage", storageChanged);
    const unsubscribe = subscribeToSessionChanges(() => { account.current?.controller.abort(); });
    return () => {
      active = false;
      media.removeEventListener("change", systemChanged);
      window.removeEventListener("storage", storageChanged);
      unsubscribe();
    };
  }, [display]);

  useEffect(() => {
    const controller = new AbortController();
    account.current = { owner, controller };
    saves.current = Promise.resolve();
    const revision = change.current;
    Promise.resolve().then(async () => {
      if (controller.signal.aborted) return;
      if (!owner) { setStatus("外观设置保存在当前浏览器"); return; }
      try {
        const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
        const result = await withPrivateOwner(owner, () => apiRequest<{ id: number; reading_preferences?: unknown }>("/auth/me/", {
          cache: "no-store", signal, headers: { "X-Reader-Owner": owner },
        }, getServerSessionCredential()), signal);
        if (controller.signal.aborted || change.current !== revision) return;
        if (String(result.id) !== owner) throw new Error("登录账户已变化。");
        const next = { ...current.current, ...validAppearance(result.reading_preferences) };
        display(next);
        const stored = storeAppearance(next);
        setStatus(stored ? "已读取此账户的外观设置" : "已读取账户设置，本机存储不可用");
      } catch {
        if (!controller.signal.aborted && change.current === revision) setStatus("账户设置暂不可用，当前外观仍可调整");
      }
    });
    return () => controller.abort();
  }, [owner, display]);

  const update = useCallback((patch: Partial<Appearance>) => {
    const safePatch = validAppearance(patch);
    const next = { ...current.current, ...safePatch };
    const revision = ++change.current;
    display(next);
    const stored = storeAppearance(next);
    const context = account.current;
    if (!context?.owner || context.controller.signal.aborted) {
      setStatus(stored ? "已保存在当前浏览器" : "已应用，本机存储不可用，刷新后可能重置");
      return;
    }
    const expectedOwner = context.owner;
    setStatus("已应用，正在同步至此账户……");
    // Serialize this tab's writes; partial patches preserve unrelated preferences.
    saves.current = saves.current.then(async () => {
      if (context.controller.signal.aborted) return;
      const signal = AbortSignal.any([context.controller.signal, AbortSignal.timeout(30000)]);
      await withPrivateOwner(expectedOwner, () => apiRequest("/auth/me/", {
        method: "PATCH", signal, headers: { "X-Reader-Owner": expectedOwner },
        body: JSON.stringify({ reading_preferences: safePatch }),
      }, getServerSessionCredential()), signal);
      if (!context.controller.signal.aborted && change.current === revision) setStatus(stored ? "已与此账户同步" : "已与此账户同步，本机存储不可用");
    }).catch(() => {
      if (!context.controller.signal.aborted && change.current === revision) setStatus(stored ? "账户同步未确认，已保存在本机；可再次选择重试" : "账户同步未确认，仅在当前页面生效");
    });
  }, [display]);

  return <AppearanceContext.Provider value={{ preferences, dark, status, update }}>{children}</AppearanceContext.Provider>;
}

export function useAppearance() {
  const value = useContext(AppearanceContext);
  if (!value) throw new Error("AppearanceProvider is missing.");
  return value;
}
