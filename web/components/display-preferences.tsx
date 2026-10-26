"use client";
import { useEvidenceLanguage } from "./evidence-language";

import { Check, Monitor, Moon, Sun, Type } from "lucide-react";
import { useAppearance } from "./appearance-provider";

export function DisplayPreferences() {
  const { t } = useEvidenceLanguage();
  const { preferences, update, status } = useAppearance();
  return <section className="display-preferences" aria-label={t("外观与字体")}>
    <header><Type size={17} /><span><strong>{t("外观与字体")}</strong><small aria-live="polite">{t(status)}</small></span></header>
    <div role="group" aria-label={t("外观模式")} className="appearance-choices">
      <span>{t("外观")}</span>
      {([["light", t("白昼"), Sun], ["dark", t("夜间"), Moon], ["system", t("系统"), Monitor]] as const).map(([value, label, Icon]) =>
        <button className={preferences.theme === value ? "active" : ""} aria-pressed={preferences.theme === value} type="button" key={value} onClick={() => update({ theme: value })}><Icon size={16} aria-hidden="true" />{label}</button>)}
    </div>
    <div role="group" aria-label={t("字号")}><span>{t("字号")}</span>
      {([["standard", t("标准")], ["comfortable", t("舒适")], ["large", t("大号")]] as const).map(([value, label]) =>
        <button className={preferences.text_size === value ? "active" : ""} aria-pressed={preferences.text_size === value} type="button" key={value} onClick={() => update({ text_size: value })}>{label}{preferences.text_size === value ? <Check size={12} /> : null}</button>)}
    </div>
    <div role="group" aria-label={t("字体")}><span>{t("字体")}</span>
      {([["sans", t("现代无衬线")], ["serif", t("人文宋体")]] as const).map(([value, label]) =>
        <button className={preferences.font_family === value ? "active" : ""} aria-pressed={preferences.font_family === value} type="button" key={value} onClick={() => update({ font_family: value })}>{label}{preferences.font_family === value ? <Check size={12} /> : null}</button>)}
    </div>
  </section>;
}
