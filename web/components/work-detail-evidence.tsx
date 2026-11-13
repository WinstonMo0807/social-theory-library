import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { SectionHeading } from "./ui";
import type { Work } from "@/lib/data";

export function WorkDetailEvidence({ work, preview }: { work: Work; preview: boolean }) {
  const curatedGroups = [
    { key: "core_viewpoint", title: "核心观点", claims: work.curatedClaims?.core_viewpoint ?? [] },
    { key: "major_criticism", title: "主要批评", claims: work.curatedClaims?.major_criticism ?? [] },
    { key: "major_response", title: "主要回应", claims: work.curatedClaims?.major_response ?? [] },
  ] as const;
  return <>
        {curatedGroups.map((group) => group.claims.length ? (
          <section className={`detail-section work-curated-claims work-curated-${group.key}`} key={group.key}>
            <SectionHeading title={group.title} />
            <div className="work-curated-claim-list">
              {group.claims.map((claim) => (
                <article key={claim.id}>
                  {claim.title ? <h3>{claim.title}</h3> : null}
                  <p className="work-curated-proposition">{claim.proposition}</p>
                  {claim.editorial_note ? <p className="work-curated-note">{claim.editorial_note}</p> : null}
                  <section data-content-section className="work-curated-evidence">
                    <header data-section-heading>查看依据 <span>{claim.evidence.length} 条馆藏原文</span></header>
                    <div>
                      {claim.evidence.map((evidence) => {
                        const author = evidence.source.authors?.join("、");
                        const pageLabel = evidence.locator.printed_page_label
                          ? `印刷页 ${evidence.locator.printed_page_label} · PDF 第 ${evidence.locator.page} 页`
                          : `PDF 第 ${evidence.locator.page} 页`;
                        return (
                          <blockquote key={evidence.id}>
                            <p>{evidence.text}</p>
                            <footer>
                              <span>{author ? `${author} · ` : ""}《{evidence.source.work_title}》 · {pageLabel}</span>
                              {preview ? <span>预览中不打开公开 Reader</span> : (
                                <Link href={evidence.reader_url}>
                                  查看原文 <ArrowRight size={14} />
                                </Link>
                              )}
                            </footer>
                          </blockquote>
                        );
                      })}
                    </div>
                  </section>
                </article>
              ))}
            </div>
          </section>
        ) : null)}
        {work.theoryAssociations?.length ? (
          <section className="detail-section work-theory-associations">
            <SectionHeading title="理论关联" />
            <div className="work-theory-association-list">
              {work.theoryAssociations.map((association) => (
                <article key={association.id}>
                  <header>
                    <div>
                      <span>{association.role_label}</span>
                      <h2>{preview ? association.node.name : <Link href={`/theories/nodes/${association.node.slug}`}>{association.node.name}</Link>}</h2>
                      {association.node.foreign_name ? <p>{association.node.foreign_name}</p> : null}
                    </div>
                    <small>人工审核通过</small>
                  </header>
                  {association.evidence.length ? (
                    <div className="work-theory-evidence-list">
                      {association.evidence.slice(0, 3).map((evidence) => (
                        <div key={evidence.id}>
                          <p>{evidence.quote}</p>
                          {preview ? <span>PDF 第 {evidence.page_number} 页</span> : (
                            <Link href={evidence.reader_href}>
                              PDF 第 {evidence.page_number}{evidence.page_end && evidence.page_end !== evidence.page_number ? `–${evidence.page_end}` : ""} 页
                              <ArrowRight size={14} />
                            </Link>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : <p className="empty-state">该关系已确认，页码证据仍待补充。</p>}
                </article>
              ))}
            </div>
          </section>
        ) : null}

  </>;
}
