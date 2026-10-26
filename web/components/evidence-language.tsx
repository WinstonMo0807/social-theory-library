"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { evidenceEnglish } from "@/lib/evidence-english";

type Language = "zh" | "en";
type Values = Record<string, string | number>;
const interpolate = (text: string, values?: Values) => text.replace(/\{(\w+)\}/g, (match, key: string) => values?.[key] === undefined ? match : String(values[key]));
const LanguageContext = createContext({ language: "zh" as Language, choose: (_: Language) => {}, t: (text: string, values?: Values) => interpolate(text, values) });
const preferenceKey = "stl:evidence-interface-language";

/** UI copy only. Search requests, citations and source text retain their original language. */
export function EvidenceLanguageProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const active = pathname === "/explore/evidence";
  const [preference, setPreference] = useState<Language>("zh");
  useEffect(() => {
    try { setPreference(localStorage.getItem(preferenceKey) === "en" ? "en" : "zh"); } catch { /* Keep the default when browser storage is unavailable. */ }
    const sync = (event: StorageEvent) => { if (event.key === preferenceKey || event.key === null) setPreference(event.newValue === "en" ? "en" : "zh"); };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  const language = active ? preference : "zh";
  useEffect(() => {
    if (!active) return;
    const previous = document.documentElement.lang;
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";
    return () => { document.documentElement.lang = previous; };
  }, [active, language]);
  const choose = useCallback((next: Language) => {
    setPreference(next);
    try { localStorage.setItem(preferenceKey, next); } catch { /* The current page still switches without persistence. */ }
  }, []);
  const value = useMemo(() => ({ language, choose, t: (text: string, values?: Values) => interpolate(language === "en" ? evidenceEnglish[text] ?? text : text, values) }), [language, choose]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export const useEvidenceLanguage = () => useContext(LanguageContext);

export function EvidenceLanguageSwitch() {
  const { language, choose } = useEvidenceLanguage();
  return <div className="evidence-language-switch" role="group" aria-label="界面语言 / Interface language">
    <button type="button" lang="zh-CN" aria-label="中文界面" aria-pressed={language === "zh"} onClick={() => choose("zh")}>中</button>
    <span aria-hidden="true">/</span>
    <button type="button" lang="en" aria-label="English interface" aria-pressed={language === "en"} onClick={() => choose("en")}>EN</button>
  </div>;
}
