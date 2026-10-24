// Existing public presentation contracts. Only schema-backed imports are generated.
import type { components } from "./generated/schema";

export type TheoryDisciplineCompact = {
  id: string;
  code: string;
  name: string;
  foreign_name: string;
  slug: string;
  description: string;
  hero_image: string;
  cover_media?: components["schemas"]["PublicCoverMedia"] | null;
};

export type TheoryPersonLink = {
  id: string;
  name: string;
  original_name: string;
  birth_year: number | null;
  death_year: number | null;
  portrait_url: string;
  portrait_media?: components["schemas"]["PublicCoverMedia"] | null;
  scholar_slug: string;
  relation_label: string;
  is_representative: boolean;
  sort_order: number;
};

export type TheoryWorkCompact = {
  edition_id?: string;
  catalog_revision_id?: string | null;
  document_revision_id?: string | null;
  source_status?: "available" | "unavailable";
  id: string;
  slug: string;
  title: string;
  subtitle: string;
  document_type: string;
  language: string;
  author: string;
  year: number | null;
  publisher: string;
  cover_url: string;
  cover_media?: components["schemas"]["PublicCoverMedia"] | null;
  asset_id: string | null;
  reader_href: string | null;
  detail_href: string | null;
};

export type KnowledgeNodeListItem = {
  id: string;
  node_type: "theory_tradition" | "subdiscipline" | "concept" | "debate" | "research_problem";
  canonical_name_zh: string;
  canonical_name_en: string;
  slug: string;
  summary: string;
  core_questions: string[];
  start_year: number | null;
  end_year: number | null;
  period_label: string;
  primary_discipline: TheoryDisciplineCompact | null;
  related_disciplines: TheoryDisciplineCompact[];
  status: string;
  sort_order: number;
  aliases_count: number;
  work_count: number;
  relation_count: number;
  representative_scholars: TheoryPersonLink[];
  cover_url: string;
  cover_media?: components["schemas"]["PublicCoverMedia"] | null;
  updated_at: string;
};

export type TheoryEvidence = {
  document_revision_id?: string | null;
  id: string;
  work: string;
  work_title: string;
  file: string;
  node: string | null;
  node_name: string;
  relation_role: string;
  page_number: number;
  page_end: number | null;
  printed_page_label: string;
  quote: string;
  bounding_box: Record<string, unknown>;
  extraction_method: string;
  ocr_confidence: number | null;
  semantic_confidence: number | null;
  review_status: string;
  reader_href: string;
};

export type TheoryWorkRelation = {
  id: string;
  work: string;
  work_data: TheoryWorkCompact | null;
  node: string;
  node_name: string;
  node_slug: string;
  role: string;
  role_label: string;
  is_primary: boolean;
  strength: string;
  confidence: number;
  status: string;
  source: string;
  evidence: TheoryEvidence[];
};

export type NormalizedKnowledgeRelation = {
  evidence?: TheoryEvidence[];
  id: string;
  source_node: string;
  source_name: string;
  source_slug: string;
  source_node_type?: string;
  target_node: string;
  target_name: string;
  target_slug: string;
  target_node_type?: string;
  relation_type: string;
  relation_label: string;
  direction: string;
  description: string;
  evidence_source: string;
  confidence: number;
  status: string;
};

export type TheoryConceptUsage = {
  id: string;
  term: string; language: string; usage_type: string; interpretation: string; attribution_note: string;
  title: string; explanatory_object: string; period: string; context: string;
  author: { id: string; name: string; original_name: string; birth_year: number | null; death_year: number | null;
    portrait_url: string;
  portrait_media?: components["schemas"]["PublicCoverMedia"] | null; scholar_slug: string } | null;
  source: { id: string; work_id: string; work_title: string; edition_id: string; edition_label: string;
    asset_id: string; document_revision_id: string; page_start: number; page_end: number;
    printed_label: string; text: string; reader_url: string };
};

export type KnowledgeNodeDetail = KnowledgeNodeListItem & {
  prose?: import("./node-editorial").NodeEditorialDetails["prose"];
  public_detail?: {configured: boolean; revision_id: string | null; usages: TheoryConceptUsage[]; unavailable_usage_count: number};
  evidenceCuration?: import("./evidence-curation.types").PublishedEvidenceCuration;
  aliases: { id: string; alias: string; language: string; alias_type: string; normalized_alias: string }[];
  discipline_links: {
    id: string;
    discipline: TheoryDisciplineCompact;
    relation_type: string;
    discipline_specific_summary: string;
    sort_order: number;
    status: string;
  }[];
  subdiscipline_links: Array<{
    id: string;
    subdiscipline: {
      id: string;
      name: string;
      foreign_name: string;
      slug: string;
      discipline_id: string;
    };
    is_primary: boolean;
    relation_role: string;
    source: string;
    confidence: number;
    sort_order: number;
    status: string;
  }>;
  topic_links: Array<{
    id: string;
    topic: { id: string; name: string; slug: string };
    relation_label: string;
    source: string;
    confidence: number;
    sort_order: number;
    status: string;
  }>;
  definition: string;
  basic_propositions: string[];
  theoretical_boundary: string;
  direct_relations: NormalizedKnowledgeRelation[];
  work_groups: Record<string, TheoryWorkRelation[]>;
  evidence: TheoryEvidence[];
  curated_claims: Record<
    "core_viewpoint" | "major_criticism" | "major_response" | "debate_position",
    Array<{
      id: string;
      kind: string;
      kind_label: string;
      title: string;
      proposition: string;
      editorial_note: string;
      qualifiers: unknown[];
      position: "direct" | "support" | "oppose" | "qualify";
      evidence: Array<{
        id: string;
        text: string;
        source: { work_title: string; authors: string[] };
        locator: { page: number; printed_page_label: string };
        reader_url: string;
        claim_role: string;
        claim_role_label: string;
      }>;
    }>
  >;
  published_at: string | null;
};

export type NormalizedTimelineEvent = {
  start_date?: string | null;
  end_date?: string | null;
  id: string;
  title: string;
  description: string;
  event_type: string;
  start_year: number | null;
  end_year: number | null;
  date_label: string;
  date_precision?: "unknown" | "year" | "approximate" | "range" | "day" | "month";
  source: string;
  evidence_page: number | null;
  evidence_printed_label: string;
  evidence_text: string;
  relations: { relation_type: string; type: string; id: string; name: string; slug?: string }[];
  reader_href: string | null;
};

export type NormalizedReadingPathItem = import("./reading-paths.types").PathMaterial;
export type NormalizedReadingPath = import("./reading-paths.types").PublicReadingPath;

export type TheorySystemOverview = {
  featured_nodes?: KnowledgeNodeListItem[];
  disciplines: (TheoryDisciplineCompact & {
    counts: Partial<Record<"theory_traditions" | "subdisciplines" | "works", number>>;
  })[];
  browse: Partial<Record<"theory_traditions" | "subdisciplines" | "debates", number>>;
  reading_paths: NormalizedReadingPath[];
  recent: {
    nodes: KnowledgeNodeListItem[];
    timeline_events: NormalizedTimelineEvent[];
    work_relations: TheoryWorkRelation[];
  };
};

export type TheoryDisciplinePage = {
  discipline: TheoryDisciplineCompact;
  counts: Partial<Record<"theory_traditions" | "subdisciplines" | "debates" | "scholars" | "works", number>>;
  active_type: string;
  nodes: KnowledgeNodeListItem[];
  lineage: NormalizedTimelineEvent[];
  reading_paths: NormalizedReadingPath[];
};

export type LocalTheoryGraph = {
  center: string | null;
  nodes: Array<{
    id: string;
    kind: "knowledge_node" | "scholar" | "work";
    node_type?: string;
    name: string;
    foreign_name?: string;
    slug?: string;
    summary?: string;
    period_label?: string;
    is_center?: boolean;
    work?: TheoryWorkCompact | null;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    relation_type: string;
    relation_label: string;
    direction: string;
    description?: string;
  }>;
  depth: number;
  limit: number;
  truncated: boolean;
};
