import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { TheorySectionHeading } from "@/components/theory-system-ui";

type PublicClaim = {
  id: string;
  title: string;
  proposition: string;
  editorial_note: string;
  position: "direct" | "support" | "oppose" | "qualify";
  evidence: Array<{
    id: string;
    text: string;
    source: { work_title: string; authors: string[] };
    locator: { page: number; printed_page_label: string };
    reader_url: string;
  }>;
};

const positionLabels: Record<PublicClaim["position"], string> = {
  direct: "直接相关",
  support: "支持",
  oppose: "相斥",
  qualify: "限定",
};

export function CuratedClaimSections({
  groups,
  debate = false,
}: {
  groups: Record<string, PublicClaim[]>;
  debate?: boolean;
}) {
  const sections = debate
    ? [{ key: "debate_position", title: "争论立场" }]
    : [
        { key: "core_viewpoint", title: "核心观点" },
        { key: "major_criticism", title: "主要批评" },
        { key: "major_response", title: "主要回应" },
      ];
  return sections.map(({ key, title }) => {
    const claims = groups[key] ?? [];
    if (!claims.length) return null;
    return (
      <section className={`theory-node-curated work-curated-claims work-curated-${key}`} key={key}>
        <TheorySectionHeading title={title} />
        <div className="work-curated-claim-list">
          {claims.map((claim) => (
            <article key={claim.id}>
              <header>
                {claim.title ? <h3>{claim.title}</h3> : null}
                {debate ? <span className={`claim-position claim-position-${claim.position}`}>{positionLabels[claim.position]}</span> : null}
              </header>
              <p className="work-curated-proposition">{claim.proposition}</p>
              {claim.editorial_note ? <p className="work-curated-note">{claim.editorial_note}</p> : null}
              <details className="work-curated-evidence">
                <summary>查看依据 <span>{claim.evidence.length} 条馆藏原文</span></summary>
                <div>
                  {claim.evidence.map((evidence) => {
                    const author = evidence.source.authors?.join("、");
                    const locator = evidence.locator.printed_page_label
                      ? `印刷页 ${evidence.locator.printed_page_label} · PDF 第 ${evidence.locator.page} 页`
                      : `PDF 第 ${evidence.locator.page} 页`;
                    return (
                      <blockquote key={evidence.id}>
                        <p>{evidence.text}</p>
                        <footer>
                          <span>{author ? `${author} · ` : ""}《{evidence.source.work_title}》 · {locator}</span>
                          <Link href={evidence.reader_url}>查看原文 <ArrowRight size={14} /></Link>
                        </footer>
                      </blockquote>
                    );
                  })}
                </div>
              </details>
            </article>
          ))}
        </div>
      </section>
    );
  });
}
