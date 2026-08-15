"use client";

import { Check, Type } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest, getStoredAccessToken } from "@/lib/api";

type TextSize = "standard" | "comfortable" | "large";
type FontFamily = "sans" | "serif";

function applyPreferences(size: TextSize, family: FontFamily) {
  document.documentElement.dataset.textSize = size;
  document.documentElement.dataset.fontFamily = family;
}

export function DisplayPreferences() {
  const [size, setSize] = useState<TextSize>("standard");
  const [family, setFamily] = useState<FontFamily>("sans");
  const [syncStatus, setSyncStatus] = useState("访客设置保存在当前浏览器");

  useEffect(() => {
    let active = true;
    const savedSize = window.localStorage.getItem("library_text_size");
    const savedFamily = window.localStorage.getItem("library_font_family");
    const nextSize: TextSize = ["standard", "comfortable", "large"].includes(savedSize ?? "")
      ? savedSize as TextSize
      : "standard";
    const nextFamily: FontFamily = savedFamily === "serif" ? "serif" : "sans";
    applyPreferences(nextSize, nextFamily);
    const token = getStoredAccessToken();
    Promise.resolve().then(async () => {
      if (!active) return;
      setSize(nextSize);
      setFamily(nextFamily);
      if (!token) return;
      try {
        const account = await apiRequest<{
          reading_preferences?: {
            text_size?: TextSize;
            font_family?: FontFamily;
          };
        }>("/auth/me/", {}, token);
        if (!active) return;
        const remoteSize = account.reading_preferences?.text_size;
        const remoteFamily = account.reading_preferences?.font_family;
        const syncedSize = remoteSize && ["standard", "comfortable", "large"].includes(remoteSize)
          ? remoteSize
          : nextSize;
        const syncedFamily = remoteFamily === "serif" || remoteFamily === "sans"
          ? remoteFamily
          : nextFamily;
        setSize(syncedSize);
        setFamily(syncedFamily);
        window.localStorage.setItem("library_text_size", syncedSize);
        window.localStorage.setItem("library_font_family", syncedFamily);
        applyPreferences(syncedSize, syncedFamily);
        setSyncStatus("已与读者账户同步");
      } catch {
        if (active) setSyncStatus("账户暂不可用，设置已保存在本机");
      }
    });
    return () => {
      active = false;
    };
  }, []);

  async function persistPreferences(nextSize: TextSize, nextFamily: FontFamily) {
    const token = getStoredAccessToken();
    if (!token) {
      setSyncStatus("访客设置保存在当前浏览器");
      return;
    }
    setSyncStatus("正在同步……");
    try {
      await apiRequest(
        "/auth/me/",
        {
          method: "PATCH",
          body: JSON.stringify({
            reading_preferences: {
              text_size: nextSize,
              font_family: nextFamily,
            },
          }),
        },
        token,
      );
      setSyncStatus("已与读者账户同步");
    } catch {
      setSyncStatus("同步失败，设置已保存在本机");
    }
  }

  function changeSize(value: TextSize) {
    setSize(value);
    window.localStorage.setItem("library_text_size", value);
    applyPreferences(value, family);
    void persistPreferences(value, family);
  }

  function changeFamily(value: FontFamily) {
    setFamily(value);
    window.localStorage.setItem("library_font_family", value);
    applyPreferences(size, value);
    void persistPreferences(size, value);
  }

  return (
    <section className="display-preferences" aria-label="显示与字体">
      <header><Type size={17} /><span><strong>显示与字体</strong><small aria-live="polite">{syncStatus}</small></span></header>
      <div>
        <span>字号</span>
        {([
          ["standard", "标准"],
          ["comfortable", "舒适"],
          ["large", "大号"],
        ] as const).map(([value, label]) => (
          <button className={size === value ? "active" : ""} type="button" key={value} onClick={() => changeSize(value)}>
            {label}{size === value ? <Check size={12} /> : null}
          </button>
        ))}
      </div>
      <div>
        <span>字体</span>
        {([
          ["sans", "现代无衬线"],
          ["serif", "人文宋体"],
        ] as const).map(([value, label]) => (
          <button className={family === value ? "active" : ""} type="button" key={value} onClick={() => changeFamily(value)}>
            {label}{family === value ? <Check size={12} /> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
