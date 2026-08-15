import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Highlighter,
  Network,
  RefreshCw,
  Search,
  Users,
  type LucideIcon,
} from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { loadAboutBlocks, loadSiteConfig, loadSiteStats, type AboutPageBlock } from "@/lib/server-api";

export const metadata: Metadata = {
  title: "关于书库",
};

const icons: Record<string, LucideIcon> = {
  "book-open": BookOpen,
  highlighter: Highlighter,
  network: Network,
  refresh: RefreshCw,
  search: Search,
  users: Users,
};

function SlotIcon({ block, fallback, size }: { block?: AboutPageBlock; fallback: LucideIcon; size: number }) {
  const Icon = icons[block?.icon ?? ""] ?? fallback;
  return <Icon size={size} />;
}

export default async function AboutPage() {
  const [config, stats, about] = await Promise.all([
    loadSiteConfig(),
    loadSiteStats(),
    loadAboutBlocks(),
  ]);
  const byKey = new Map(about.blocks.map((block) => [block.key, block]));
  const enabled = (key: string) => !about.configured || byKey.has(key);
  const value = (
    key: string,
    field: "title" | "body" | "action_label" | "action_href",
    fallback: string,
  ) => {
    const block = byKey.get(key);
    return block ? block[field] : about.configured ? "" : fallback;
  };

  const processSteps = value(
    "about-process",
    "body",
    "文件识别|元数据提取|全文处理|人工校订|正式发布",
  ).split("|").map((item) => item.trim()).filter(Boolean);
  const features = [
    {
      key: "about-feature-source",
      fallbackIcon: Search,
      title: config.about_feature_search_title,
      body: config.about_feature_search_body,
      href: "/explore",
    },
    {
      key: "about-feature-reading",
      fallbackIcon: BookOpen,
      title: config.about_feature_read_title,
      body: config.about_feature_read_body,
      href: "/account",
    },
    {
      key: "about-feature-knowledge",
      fallbackIcon: Network,
      title: config.about_feature_knowledge_title,
      body: config.about_feature_knowledge_body,
      href: "/theory-schools",
    },
  ];
  const principles = [
    ["about-open", config.about_access_title, config.about_access_body],
    ["about-copyright", config.about_rights_title, config.about_rights_body],
    ["about-privacy", config.about_privacy_title, config.about_privacy_body],
  ] as const;
  const statSlots = [
    { key: "about-stat-documents", amount: stats.documents.toLocaleString("zh-CN"), label: "种文献", icon: BookOpen },
    { key: "about-stat-scholars", amount: stats.scholars.toLocaleString("zh-CN"), label: "位学者", icon: Users },
    { key: "about-stat-knowledge", amount: stats.knowledge_objects.toLocaleString("zh-CN"), label: "个理论与研究专题", icon: Network },
    { key: "about-stat-updated", amount: stats.last_updated_label, label: "最后更新于", icon: RefreshCw },
  ];

  return (
    <>
      <div className="page-shell about-page">
        <section className="about-hero">
          {(enabled("about-breadcrumb-home") || enabled("about-breadcrumb-current")) ? (
            <p className="breadcrumbs">
              {enabled("about-breadcrumb-home") ? <Link href="/">{value("about-breadcrumb-home", "title", "首页")}</Link> : null}
              {enabled("about-breadcrumb-home") && enabled("about-breadcrumb-current") ? " / " : null}
              {enabled("about-breadcrumb-current") ? value("about-breadcrumb-current", "title", "关于") : null}
            </p>
          ) : null}
          {enabled("about-intro") ? (
            <div className="about-hero-copy">
              <h1>{value("about-intro", "title", config.about_title)}</h1>
              <p>{value("about-intro", "body", config.about_body)}</p>
            </div>
          ) : null}
          <dl className="about-stats">
            {statSlots.filter((slot) => enabled(slot.key)).map((slot) => (
              <div key={slot.key}>
                <dt>{slot.amount}</dt>
                <dd><SlotIcon block={byKey.get(slot.key)} fallback={slot.icon} size={16} />{value(slot.key, "title", slot.label)}</dd>
              </div>
            ))}
          </dl>
        </section>
        {enabled("about-why") ? <section className="about-why"><h2>{value("about-why", "title", config.about_why_title)}</h2><p>{value("about-why", "body", config.about_why_body)}</p></section> : null}
        <section className="about-principles">
          {features.filter((feature) => enabled(feature.key)).map((feature) => {
            const actionLabel = value(feature.key, "action_label", "了解更多");
            return (
              <article key={feature.key}>
                <SlotIcon block={byKey.get(feature.key)} fallback={feature.fallbackIcon} size={34} />
                <h2>{value(feature.key, "title", feature.title)}</h2>
                <p>{value(feature.key, "body", feature.body)}</p>
                {actionLabel ? <Link href={value(feature.key, "action_href", feature.href)}>{actionLabel} <ArrowRight size={15} /></Link> : null}
              </article>
            );
          })}
        </section>
        {enabled("about-process") ? (
          <section className="about-ingestion">
            <h2>{value("about-process", "title", config.about_ingestion_title)}</h2>
            <ol>
              {processSteps.map((label, index) => (
                <li key={`${label}-${index}`}><span>{index + 1}</span>{label}{index < processSteps.length - 1 ? <ArrowRight size={18} /> : null}</li>
              ))}
            </ol>
            {enabled("about-process-description") && value("about-process-description", "body", "") ? <p>{value("about-process-description", "body", "")}</p> : null}
          </section>
        ) : null}
        <section className="about-boundaries">
          {principles.filter(([key]) => enabled(key)).map(([key, title, body]) => <article key={key}><h2>{value(key, "title", title)}</h2><p>{value(key, "body", body)}</p></article>)}
        </section>
        {enabled("about-notice") ? (
          <section className="about-warning">
            <SlotIcon block={byKey.get("about-notice")} fallback={Highlighter} size={26} />
            <div><h2>{value("about-notice", "title", config.about_warning_title)}</h2><p>{value("about-notice", "body", config.about_warning_body)}</p></div>
            {value("about-notice", "action_label", "开始搜索书库") ? <Link className="button secondary" href={value("about-notice", "action_href", "/explore")}>{value("about-notice", "action_label", "开始搜索书库")} <ArrowRight size={16} /></Link> : null}
          </section>
        ) : null}
        {(enabled("about-version-current") || enabled("about-version-updated")) ? (
          <p className="about-version">
            {enabled("about-version-current") ? `${value("about-version-current", "title", "当前版本")} ${stats.version}` : ""}
            {enabled("about-version-current") && enabled("about-version-updated") ? " · " : ""}
            {enabled("about-version-updated") ? `${value("about-version-updated", "title", "最近更新")} ${stats.last_updated_label}` : ""}
          </p>
        ) : null}
      </div>
      <SiteFooter />
    </>
  );
}
