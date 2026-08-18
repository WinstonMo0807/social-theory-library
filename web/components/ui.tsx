import Link from "next/link";
import { ArrowRight, Eye, Search } from "lucide-react";
import type { ReactNode } from "react";
import type { Scholar, Work } from "@/lib/data";
import { SaveWorkButton } from "./save-work-button";

export function ArchitecturalImage({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`architectural-image ${compact ? "compact" : ""}`} aria-label="抽象建筑光影">
      <span className="arch-plane arch-plane-one" />
      <span className="arch-plane arch-plane-two" />
      <span className="arch-person" />
    </div>
  );
}

export function SectionHeading({
  title,
  href,
  action = "查看全部",
}: {
  title: string;
  href?: string;
  action?: string;
}) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      {href ? (
        <Link className="text-link" href={href}>
          {action}
          <ArrowRight size={15} />
        </Link>
      ) : null}
    </div>
  );
}

export function BookCover({ work, size = "normal" }: { work: Work; size?: "small" | "normal" | "large" }) {
  return (
    <div className={`book-cover ${work.cover} ${size}${work.coverImage ? " has-image" : ""}`} aria-label={`${work.title}封面`}>
      {work.coverImage ? (
        <span
          className="book-cover-image"
          style={{ backgroundImage: `url("${work.coverImage}")` }}
          aria-hidden="true"
        />
      ) : (
        <>
          <span>{work.originalTitle ?? work.title}</span>
          <small>{work.author}</small>
        </>
      )}
    </div>
  );
}

export function BookCard({
  work,
  dense = false,
  showSummary = !dense,
  exploreActions = false,
}: {
  work: Work;
  dense?: boolean;
  showSummary?: boolean;
  exploreActions?: boolean;
}) {
  return (
    <article className={`book-card ${dense ? "dense" : ""} ${exploreActions ? "explore-result-card" : ""}`}>
      <div className="book-card-main">
        <Link
          className="book-cover-link"
          href={`/works/${work.slug}`}
          aria-label={`查看《${work.title}》详情`}
        >
          <BookCover work={work} size={dense ? "small" : "normal"} />
        </Link>
        <div className="book-meta">
          <p className="eyebrow">{work.school}</p>
          <h3>
            <Link href={`/works/${work.slug}`}>{work.title}</Link>
          </h3>
          <p className="book-author">{work.author}</p>
          <p className="muted-row">
            {work.year} <span>·</span> {work.kind}
          </p>
          {showSummary && work.summary ? <p className="book-summary">{work.summary}</p> : null}
        </div>
      </div>
      {!dense ? (
        <div className="book-actions">
          {exploreActions ? (
            <>
              <Link href={`/works/${work.slug}`}>预览</Link>
              <Link href={`/reader/${work.id}`}><Eye size={15} />阅读 PDF</Link>
              <Link href={`/works/${work.slug}#citation`}>论文引用</Link>
            </>
          ) : (
            <Link href={`/reader/${work.id}`}>
              <Eye size={15} />
              阅读
            </Link>
          )}
          <SaveWorkButton workId={work.workId} />
        </div>
      ) : null}
    </article>
  );
}

export function ScholarPortrait({ scholar, large = false }: { scholar: Scholar; large?: boolean }) {
  const initials = scholar.originalName
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2);
  return (
    <div
      className={`scholar-portrait ${large ? "large" : ""} ${scholar.portrait ? "has-image" : ""}`}
      style={scholar.portrait ? { backgroundImage: `url("${scholar.portrait}")` } : undefined}
      aria-label={scholar.portrait ? `${scholar.name}肖像` : `${scholar.name}肖像占位`}
    >
      {!scholar.portrait ? <span>{initials}</span> : null}
    </div>
  );
}

export function ScholarCard({ scholar }: { scholar: Scholar }) {
  return (
    <article className="scholar-card">
      <ScholarPortrait scholar={scholar} />
      <div>
        <h3>
          <Link href={`/scholars/${scholar.slug}`}>{scholar.name}</Link>
        </h3>
        <p>{scholar.years}</p>
        <p>{scholar.biography}</p>
        <Link className="arrow-only" href={`/scholars/${scholar.slug}`} aria-label={`查看${scholar.name}`}>
          <ArrowRight size={17} />
        </Link>
      </div>
    </article>
  );
}

export function TagList({
  items,
  hrefFor = (item) => `/explore?context=global&q=${encodeURIComponent(item)}`,
}: {
  items: string[];
  hrefFor?: (item: string) => string;
}) {
  return (
    <div className="tag-list">
      {items.map((item) => (
        <Link href={hrefFor(item)} key={item}>
          {item}
        </Link>
      ))}
    </div>
  );
}

export function SearchField({
  defaultValue = "",
  placeholder = "搜索全文、作者、书名、概念……",
}: {
  defaultValue?: string;
  placeholder?: string;
}) {
  return (
    <label className="search-field">
      <Search size={20} />
      <input
        aria-label="搜索"
        autoComplete="off"
        defaultValue={defaultValue}
        name="q"
        placeholder={placeholder}
        type="search"
      />
      <span className="sr-only">搜索</span>
    </label>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <strong>社会理论书库</strong>
      <nav aria-label="页脚导航">
        <Link href="/about">关于</Link>
        <Link href="/login">读者登录</Link>
        <Link href="/account">读者中心</Link>
      </nav>
      <p>© 2026 社会理论书库</p>
    </footer>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`panel ${className}`}>{children}</section>;
}
