"use client";

import { Check, Monitor, Moon, Sun, Type } from "lucide-react";
import { useAppearance } from "./appearance-provider";

export function DisplayPreferences() {
  const { preferences, update, status } = useAppearance();
  return <section className="display-preferences" aria-label="外观与字体">
    <header><Type size={17} /><span><strong>外观与字体</strong><small aria-live="polite">{status}</small></span></header>
    <div role="group" aria-label="外观模式" className="appearance-choices">
      <span>外观</span>
      {([["light", "白昼", Sun], ["dark", "夜间", Moon], ["system", "系统", Monitor]] as const).map(([value, label, Icon]) =>
        <button className={preferences.theme === value ? "active" : ""} aria-pressed={preferences.theme === value} type="button" key={value} onClick={() => update({ theme: value })}><Icon size={16} aria-hidden="true" />{label}</button>)}
    </div>
    <div role="group" aria-label="字号"><span>字号</span>
      {([["standard", "标准"], ["comfortable", "舒适"], ["large", "大号"]] as const).map(([value, label]) =>
        <button className={preferences.text_size === value ? "active" : ""} aria-pressed={preferences.text_size === value} type="button" key={value} onClick={() => update({ text_size: value })}>{label}{preferences.text_size === value ? <Check size={12} /> : null}</button>)}
    </div>
    <div role="group" aria-label="字体"><span>字体</span>
      {([["sans", "现代无衬线"], ["serif", "人文宋体"]] as const).map(([value, label]) =>
        <button className={preferences.font_family === value ? "active" : ""} aria-pressed={preferences.font_family === value} type="button" key={value} onClick={() => update({ font_family: value })}>{label}{preferences.font_family === value ? <Check size={12} /> : null}</button>)}
    </div>
  </section>;
}
