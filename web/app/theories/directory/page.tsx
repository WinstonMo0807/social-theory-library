import type { Metadata } from "next";
import Link from "next/link";
import { Search } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { KnowledgeNodeCard, TheoryEmpty, nodeTypeLabels } from "@/components/theory-system-ui";
import { loadDisciplines, loadTheorySystemNodes } from "@/lib/server-api";

export const metadata: Metadata = { title: "理论知识目录", description: "浏览公开的理论传统、子学科、概念、争论和研究问题。" };

const allowedTypes = ["theory_tradition", "subdiscipline", "concept", "debate", "research_problem"] as const;

export default async function TheoryDirectoryPage({ searchParams }: { searchParams: Promise<{ type?: string; discipline?: string; q?: string }> }) {
  const params = await searchParams;
  const nodeType = allowedTypes.includes(params.type as typeof allowedTypes[number]) ? params.type! : "theory_tradition";
  const [nodes, disciplines] = await Promise.all([loadTheorySystemNodes({ type: nodeType, discipline: params.discipline, q: params.q }), loadDisciplines()]);
  return <><main className="page-shell theory-system-page theory-directory-page">
    <div className="theory-breadcrumb"><Link href="/theories">探索理论流派</Link><span>/</span><strong>理论知识目录</strong></div>
    <header><p className="eyebrow">规范知识节点</p><h1>{nodeTypeLabels[nodeType]}</h1><p>只展示已经审核并发布的规范条目。别名会指向同一个知识节点。</p></header>
    <nav className="theory-tab-list">{allowedTypes.map((value) => <Link className={nodeType === value ? "active" : ""} href={`/theories/directory?type=${value}`} key={value}>{nodeTypeLabels[value]}</Link>)}</nav>
    <form className="theory-directory-filters" action="/theories/directory"><input type="hidden" name="type" value={nodeType} /><label><span>所属学科</span><select name="discipline" defaultValue={params.discipline || ""}><option value="">全部学科</option>{disciplines.map((item) => <option key={item.id} value={item.slug}>{item.name}</option>)}</select></label><label className="directory-search"><Search size={17} /><input name="q" defaultValue={params.q || ""} placeholder="搜索名称、别名或外文名" /></label><button type="submit">应用筛选</button></form>
    {nodes.length ? <section className="theory-node-grid">{nodes.map((node) => <KnowledgeNodeCard key={node.id} node={node} />)}</section> : <TheoryEmpty title="没有符合条件的公开条目" detail="调整学科或关键词后再次查询。" />}
  </main><SiteFooter /></>;
}
