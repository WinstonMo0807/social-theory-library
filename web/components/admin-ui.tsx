"use client";

import Link from "next/link";
import { useId, type ReactNode } from "react";

export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

type CommonProps = {
  className?: string;
};

export type PageHeaderProps = CommonProps & {
  title: string;
  eyebrow?: string;
  description?: ReactNode;
  status?: ReactNode;
  actions?: ReactNode;
};

export function PageHeader({
  title,
  eyebrow,
  description,
  status,
  actions,
  className = "",
}: PageHeaderProps) {
  const titleId = useId();

  return (
    <header className={`admin-page-title admin-ui-page-header ${className}`.trim()} aria-labelledby={titleId}>
      <div className="admin-ui-page-header-copy">
        {eyebrow ? <p>{eyebrow}</p> : null}
        <div className="admin-ui-page-header-heading">
          <h1 id={titleId}>{title}</h1>
          {status}
        </div>
        {description ? <span>{description}</span> : null}
      </div>
      {actions ? <div className="admin-ui-page-header-actions" aria-label="页面操作">{actions}</div> : null}
    </header>
  );
}

export type StatusBadgeProps = CommonProps & {
  label: string;
  tone?: StatusTone;
  ariaLabel?: string;
};

export function StatusBadge({
  label,
  tone = "neutral",
  ariaLabel,
  className = "",
}: StatusBadgeProps) {
  return (
    <span
      className={`admin-ui-status-badge tone-${tone} ${className}`.trim()}
      aria-label={ariaLabel ?? `状态：${label}`}
    >
      <i aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

export type EmptyStateProps = CommonProps & {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
};

export function EmptyState({
  title,
  description,
  icon,
  action,
  compact = false,
  className = "",
}: EmptyStateProps) {
  const titleId = useId();
  const descriptionId = useId();

  return (
    <div
      className={`admin-ui-empty-state ${compact ? "compact" : ""} ${className}`.trim()}
      role="status"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
    >
      {icon ? <span className="admin-ui-empty-state-icon" aria-hidden="true">{icon}</span> : null}
      <div>
        <strong id={titleId}>{title}</strong>
        {description ? <p id={descriptionId}>{description}</p> : null}
      </div>
      {action ? <div className="admin-ui-empty-state-action">{action}</div> : null}
    </div>
  );
}

export type FormSectionProps = CommonProps & {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
};

export function FormSection({
  title,
  description,
  actions,
  children,
  className = "",
}: FormSectionProps) {
  const titleId = useId();

  return (
    <section className={`admin-ui-form-section ${className}`.trim()} aria-labelledby={titleId}>
      <header>
        <div>
          <h2 id={titleId}>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {actions ? <div className="admin-ui-form-section-actions" aria-label={`${title}操作`}>{actions}</div> : null}
      </header>
      <div className="admin-ui-form-section-body">{children}</div>
    </section>
  );
}

export type StickyActionBarProps = CommonProps & {
  label?: string;
  status?: ReactNode;
  primary?: ReactNode;
  secondary?: ReactNode;
  children?: ReactNode;
};

export function StickyActionBar({
  label = "页面操作",
  status,
  primary,
  secondary,
  children,
  className = "",
}: StickyActionBarProps) {
  return (
    <div className={`admin-ui-sticky-action-bar ${className}`.trim()} role="region" aria-label={label}>
      {status ? <div className="admin-ui-sticky-action-status" role="status">{status}</div> : null}
      <div className="admin-ui-sticky-action-controls">
        {children}
        {secondary}
        {primary}
      </div>
    </div>
  );
}

export type EvidenceChipProps = CommonProps & {
  label: string;
  source?: string;
  pageLabel?: string;
  href?: string;
  onActivate?: () => void;
  ariaLabel?: string;
};

export function EvidenceChip({
  label,
  source,
  pageLabel,
  href,
  onActivate,
  ariaLabel,
  className = "",
}: EvidenceChipProps) {
  const content = (
    <>
      <span>{label}</span>
      {source ? <small>{source}</small> : null}
      {pageLabel ? <b>{pageLabel}</b> : null}
    </>
  );
  const classes = `admin-ui-evidence-chip ${href || onActivate ? "interactive" : ""} ${className}`.trim();
  const accessibleLabel = ariaLabel ?? [label, source, pageLabel].filter(Boolean).join("，");

  if (href) {
    return <Link className={classes} href={href} aria-label={accessibleLabel}>{content}</Link>;
  }
  if (onActivate) {
    return <button className={classes} type="button" onClick={onActivate} aria-label={accessibleLabel}>{content}</button>;
  }
  return <span className={classes} aria-label={accessibleLabel}>{content}</span>;
}

export type ConfidenceBarProps = CommonProps & {
  value: number;
  label?: string;
};

export function ConfidenceBar({
  value,
  label = "候选置信度",
  className = "",
}: ConfidenceBarProps) {
  const normalizedValue = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
  const percent = Math.round(normalizedValue * 100);

  return (
    <div className={`admin-ui-confidence ${className}`.trim()}>
      <span>{label}</span>
      <span
        className="admin-ui-confidence-track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${percent}%`}
      >
        <i style={{ width: `${percent}%` }} aria-hidden="true" />
      </span>
      <strong>{percent}%</strong>
    </div>
  );
}

export type CandidateCardProps = CommonProps & {
  title: string;
  value: ReactNode;
  normalizedValue?: ReactNode;
  source?: ReactNode;
  confidence?: number;
  status?: { label: string; tone?: StatusTone };
  evidence?: ReactNode;
  evidenceSummary?: string;
  conflicts?: ReactNode;
  actions?: ReactNode;
};

export function CandidateCard({
  title,
  value,
  normalizedValue,
  source,
  confidence,
  status,
  evidence,
  evidenceSummary = "查看证据与评分",
  conflicts,
  actions,
  className = "",
}: CandidateCardProps) {
  const titleId = useId();

  return (
    <article className={`admin-ui-candidate-card ${className}`.trim()} aria-labelledby={titleId}>
      <header>
        <h3 id={titleId}>{title}</h3>
        {status ? <StatusBadge label={status.label} tone={status.tone} /> : null}
      </header>
      <div className="admin-ui-candidate-value">
        <strong>{value}</strong>
        {normalizedValue ? <p><span>规范值</span>{normalizedValue}</p> : null}
        {source ? <small>{source}</small> : null}
      </div>
      {typeof confidence === "number" ? <ConfidenceBar value={confidence} /> : null}
      {evidence ? (
        <details className="admin-ui-candidate-evidence">
          <summary>{evidenceSummary}</summary>
          <div className="admin-ui-candidate-evidence-body" aria-label="候选证据">{evidence}</div>
        </details>
      ) : null}
      {conflicts ? <div className="admin-ui-candidate-conflicts" role="alert">{conflicts}</div> : null}
      {actions ? <footer aria-label={`${title}候选操作`}>{actions}</footer> : null}
    </article>
  );
}
