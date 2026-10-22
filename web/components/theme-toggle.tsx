"use client";
import { Moon, Sun } from "lucide-react";
import { useAppearance } from "./appearance-provider";

export function ThemeToggle() {
  const { dark, update } = useAppearance();
  return <button type="button" className="icon-button theme-toggle" aria-label={dark ? "切换为白昼模式" : "切换为夜间模式"} title={dark ? "切换为白昼模式" : "切换为夜间模式"} aria-pressed={dark} onClick={() => update({ theme: dark ? "light" : "dark" })}>
    <Sun className="theme-sun" size={20} aria-hidden="true" /><Moon className="theme-moon" size={20} aria-hidden="true" />
  </button>;
}
