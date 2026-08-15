import type { Metadata } from "next";
import Link from "next/link";
import { Network, Search } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { TheoryGraphExplorer } from "@/components/theory-graph-explorer";
import { loadDisciplines, loadLocalTheoryGraph, loadTheorySystemNodes } from "@/lib/server-api";

export const metadata: Metadata = { title: "社会理论图谱", description: "以一个理论为中心，浏览经过人工确认的局部理论关系。" };

type GraphParams = { center?: string; discipline?: string; node_type?: string; relation_type?: string; start_year?: string; end_year?: string; has_collection?: string; depth?: string; limit?: string };

const relationTypes = [
  ["inherited_from", "继承"], ["revises", "修正"], ["criticizes", "批判"], ["competes_with", "竞争"],
  ["synthesizes", "综合"], ["branches_from", "分化"], ["borrows_concept_from", "概念借用"],
  ["transferred_to", "跨学科传播"], ["influenced_by", "受到影响"], ["overlaps_with", "部分重叠"],
] as const;

export default async function TheoryGraphPage({ searchParams }: { searchParams: Promise<GraphParams> }) {
  const params = await searchParams;
  const depth = params.depth === "2" ? 2 : 1;
  const limit = Math.min(Math.max(Number(params.limit || 20) || 20, 1), 30);
  const [graph, disciplines, theories] = await Promise.all([
    loadLocalTheoryGraph({ center: params.center, discipline: params.discipline, node_type: params.node_type, relation_type: params.relation_type, start_year: Number(params.start_year) || undefined, end_year: Number(params.end_year) || undefined, has_collection: params.has_collection, depth, limit }),
    loadDisciplines(),
    loadTheorySystemNodes({ type: "theory_tradition", discipline: params.discipline }),
  ]);

  return (
    <>
      <main className="page-shell theory-system-page theory-graph-page">
        <div className="theory-breadcrumb"><Link href="/theories">探索理论流派</Link><span>/</span><strong>社会理论图谱</strong></div>
        <section className="theory-graph-heading"><div><p className="eyebrow">局部关系浏览</p><h1>社会理论图谱</h1><p>以当前理论为中心，查看一至两层经过人工审核的理论、学者与馆藏关系。</p></div><nav className="theory-view-mode"><Link href="/theories">学科脉络</Link><Link href="/theories/timeline">历史时间轴</Link><Link className="active" href="/theories/graph">理论图谱</Link></nav></section>
        <form className="theory-graph-filters" action="/theories/graph">
          <label><span>学科</span><select name="discipline" defaultValue={params.discipline || ""}><option value="">全部学科</option>{disciplines.map((item) => <option value={item.slug} key={item.id}>{item.name}</option>)}</select></label>
          <label><span>中心理论</span><select name="center" defaultValue={params.center || ""}><option value="">自动选择</option>{theories.map((item) => <option value={item.slug} key={item.id}>{item.canonical_name_zh}</option>)}</select></label>
          <label><span>关系类型</span><select name="relation_type" defaultValue={params.relation_type || ""}><option value="">全部关系</option>{relationTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          <label><span>节点类型</span><select name="node_type" defaultValue={params.node_type || ""}><option value="">全部类型</option><option value="theory_tradition">理论传统</option><option value="subdiscipline">子学科</option><option value="concept">核心概念</option><option value="debate">理论争论</option><option value="research_problem">研究问题</option></select></label>
          <label><span>起始年份</span><input name="start_year" inputMode="numeric" defaultValue={params.start_year || ""} placeholder="不限" /></label>
          <label><span>结束年份</span><input name="end_year" inputMode="numeric" defaultValue={params.end_year || ""} placeholder="不限" /></label>
          <label><span>馆藏范围</span><select name="has_collection" defaultValue={params.has_collection || ""}><option value="">全部节点</option><option value="true">仅看有馆藏</option></select></label>
          <label><span>展开层级</span><select name="depth" defaultValue={String(depth)}><option value="1">一层</option><option value="2">两层</option></select></label>
          <label className="graph-limit"><span>节点上限</span><select name="limit" defaultValue={String(limit)}><option value="12">12</option><option value="20">20</option><option value="30">30</option></select></label>
          <button type="submit"><Search size={17} />应用筛选</button>
          <Link href="/theories/graph"><Network size={17} />重置</Link>
        </form>
        {graph.truncated ? <p className="theory-graph-notice">当前视图已达到 {graph.limit} 个节点上限。请缩小关系类型或更换中心理论后继续浏览。</p> : null}
        <TheoryGraphExplorer graph={graph} />
      </main>
      <SiteFooter />
    </>
  );
}
