import Link from "next/link";
import { ArrowRight } from "lucide-react";

export type KnowledgeMapEntry = {
  source?: string;
  target?: string;
  relation?: string;
  description?: string;
  label?: string;
} | string;

function entryParts(entry: KnowledgeMapEntry, index: number) {
  if (typeof entry === "string") {
    return {
      source: entry,
      target: "",
      relation: "相关概念",
      description: "",
    };
  }
  return {
    source: entry.source || entry.label || `概念 ${index + 1}`,
    target: entry.target || "",
    relation: entry.relation || (entry.target ? "相关" : "概念节点"),
    description: entry.description || "",
  };
}

export function KnowledgeMap({
  entries,
  emptyText = "概念关系尚待管理员编辑。",
}: {
  entries: KnowledgeMapEntry[];
  emptyText?: string;
}) {
  if (!entries.length) return <p className="empty-state">{emptyText}</p>;

  return (
    <div className="knowledge-map" aria-label="概念关系图">
      {entries.map((entry, index) => {
        const { source, target, relation, description } = entryParts(entry, index);
        return (
          <article className="knowledge-map-row" key={`${source}-${target}-${index}`}>
            <Link href={`/explore?q=${encodeURIComponent(source)}`}>{source}</Link>
            <span className="knowledge-map-edge">
              <small>{relation}</small>
              <ArrowRight aria-hidden="true" size={16} />
            </span>
            {target ? (
              <Link href={`/explore?q=${encodeURIComponent(target)}`}>{target}</Link>
            ) : (
              <span className="knowledge-map-open-node">待连接</span>
            )}
            {description ? <p>{description}</p> : null}
          </article>
        );
      })}
    </div>
  );
}
