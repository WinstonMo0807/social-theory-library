import type { components } from "@/lib/api/generated/schema";
import styles from "./relation-source-quote.module.css";

export function RelationSourceQuote({ material }: { material?: components["schemas"]["RelationAnchorMaterial"] | null }) {
  if (!material?.available || !material.public_eligible || !material.reader_href) return null;
  return <figure className={styles.quote}>
    <blockquote>{material.quote}</blockquote>
    <figcaption><span>{material.title}{material.edition_label ? ` · ${material.edition_label}` : ""}{material.pdf_page ? ` · PDF 第 ${material.pdf_page} 页` : ""}</span>
      <a href={material.reader_href}>阅读准确原文 ↗</a></figcaption>
  </figure>;
}
