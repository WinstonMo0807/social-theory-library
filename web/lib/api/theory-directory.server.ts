import { loadKnowledgeNode } from "./knowledge.server";
import { loadSubdiscipline } from "./taxonomy.server";
import { serverRequest } from "./server-request";
import type {
  TheoryDirectoryFilters, TheoryDirectoryKind, TheoryDirectoryResponse, TheoryDirectorySelection,
} from "./theory-directory.types";

export async function loadTheoryDirectory(filters: TheoryDirectoryFilters): Promise<TheoryDirectoryResponse> {
  const query = new URLSearchParams({ type: filters.type, page: String(filters.page) });
  for (const key of ["discipline", "parent", "q"] as const) {
    if (filters[key]) query.set(key, filters[key]);
  }
  return serverRequest<TheoryDirectoryResponse>(`/catalog/theory-system/directory/?${query}`);
}

export async function loadTheoryDirectorySelection(
  kind: TheoryDirectoryKind,
  slug: string,
): Promise<TheoryDirectorySelection | null> {
  if (kind === "subdiscipline") {
    const entry = await loadSubdiscipline(slug);
    if (!entry) return null;
    const source = entry.sources.find(item => item.reader_href)
      || entry.core_works.find(item => item.evidence?.reader_href)?.evidence;
    const work = entry.core_works.find(item => item.reader_href);
    return {
      id: entry.id, name: entry.name, slug: entry.slug, kind,
      href: entry.href, foreign_name: entry.foreign_name,
      summary: entry.description || entry.research_object, period_label: entry.formation_period,
      scholars: entry.scholars.filter(item => item.href).map(item => ({
        id: item.id, name: item.name, original_name: "", href: item.href, portrait_url: item.portrait_url,
      })),
      concepts: entry.theories.filter(item => item.kind === "knowledge_node" && item.node_type === "concept").map(item => ({
        id: item.id, name: item.name, href: item.href,
      })),
      source_href: source?.reader_href || work?.reader_href || null,
      source_title: source?.title || work?.title || "",
      source_kind: source ? "evidence" : work ? "work" : null,
    };
  }
  const node = await loadKnowledgeNode(slug);
  if (!node || node.node_type !== kind) return null;
  const workRelations = Object.values(node.work_groups).flat();
  const sources = [
    ...node.evidence.map(item => ({
      href: item.reader_href, title: `${node.canonical_name_zh} · ${item.work_title}`,
    })),
    ...node.direct_relations.flatMap(relation => (relation.evidence || []).map(item => ({
      href: item.reader_href,
      title: `${relation.source_name}与${relation.target_name} · ${relation.relation_label} · ${item.work_title}`,
    }))),
    ...workRelations.flatMap(relation => relation.evidence.map(item => ({
      href: item.reader_href, title: `${relation.node_name} · ${relation.role_label} · ${item.work_title}`,
    }))),
    ...(node.public_detail?.usages || []).map(usage => ({
      href: usage.source.reader_url, title: `${usage.author?.name || usage.term}的用法 · ${usage.source.work_title}`,
    })),
  ];
  const source = sources.find(item => item.href);
  const work = workRelations.find(item => item.work_data?.reader_href)?.work_data;
  const concepts = node.direct_relations.flatMap(relation => {
    const outgoing = relation.source_node === node.id;
    const targetKind = outgoing ? relation.target_node_type : relation.source_node_type;
    const id = outgoing ? relation.target_node : relation.source_node;
    const slug = outgoing ? relation.target_slug : relation.source_slug;
    if (targetKind !== "concept" || id === node.id || !slug) return [];
    return [{
      id, name: outgoing ? relation.target_name : relation.source_name,
      href: `/theories/nodes/${encodeURIComponent(slug)}`,
    }];
  });
  return {
    id: node.id, name: node.canonical_name_zh, slug: node.slug, kind,
    href: `/theories/nodes/${encodeURIComponent(node.slug)}`, foreign_name: node.canonical_name_en,
    summary: node.definition || node.summary, period_label: node.period_label,
    scholars: node.representative_scholars.filter(item => item.scholar_slug).map(item => ({
      id: item.id, name: item.name, original_name: item.original_name,
      href: `/scholars/${encodeURIComponent(item.scholar_slug)}`, portrait_url: item.portrait_url,
    })),
    concepts: [...new Map(concepts.map(item => [item.id, item])).values()],
    source_href: source?.href || work?.reader_href || null,
    source_title: source?.title || work?.title || "",
    source_kind: source ? "evidence" : work ? "work" : null,
  };
}
