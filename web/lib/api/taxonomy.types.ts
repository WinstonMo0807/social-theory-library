import type { components } from "./generated/schema";
// Existing public presentation contracts. Only schema-backed imports are generated.
import type { ApiWork } from "./public-catalog";
import type { TheoryWorkCompact } from "./knowledge.types";

export type Discipline = {
  id: string;
  code: string;
  name: string;
  foreign_name: string;
  slug: string;
  description: string;
  introduction: string;
  hero_image: string;
  cover_media?: components["schemas"]["PublicCoverMedia"] | null;
  sort_order: number;
  theory_count: number;
  subdiscipline_count: number;
  topic_count: number;
  work_count: number;
  scholar_count: number;
};

export type SubdisciplineSource = {
  id: string;
  work_id: string;
  edition_id: string;
  asset_id: string;
  document_revision_id: string;
  title: string;
  edition_label: string;
  quote: string;
  pdf_page: number;
  printed_page_label: string;
  reader_href: string;
  source_kind: "work_relation" | "placement_span";
};

export type SubdisciplineTheory = {
  id: string;
  name: string;
  slug: string;
  role: string;
  kind: "knowledge_node" | "legacy_theory";
  node_type: string | null;
  href: string;
  summary: string;
  cover_url: string;
  cover_media?: components["schemas"]["PublicCoverMedia"] | null;
  source: string;
  canonical_target: { id: string; slug: string; href: string } | null;
  legacy_identities: { id: string; name: string; slug: string; role: string; source: string }[];
};

export type Subdiscipline = {
  id: string;
  name: string;
  foreign_name: string;
  slug: string;
  description: string;
  hero_image: string;
  cover_media?: components["schemas"]["PublicCoverMedia"] | null;
  discipline: Discipline | null;
  parent: { id: string; name: string; slug: string } | null;
  research_object: string;
  core_questions: string[];
  formation_period: string;
  research_directions: string[];
  methods: string[];
  representative_issues: string[];
  featured: boolean;
  href: string;
  children: { id: string; name: string; slug: string; href: string }[];
  key_questions: { id: string | null; title: string; description: string; href: string | null; source: string }[];
  theories: SubdisciplineTheory[];
  topics: {
    id: string; name: string; slug: string; relation_label: string;
    description: string; hero_image: string; cover_media?: components["schemas"]["PublicCoverMedia"] | null; href: string; source: string;
  }[];
  works: ApiWork[];
  works_pagination: { count: number; page: number; total_pages: number };
  core_works: (TheoryWorkCompact & { relation_label: string; source: string; evidence: SubdisciplineSource | null })[];
  scholars: {
    id: string; person_id: string; name: string; slug: string; source_label: string;
    reason: string; confidence: number; approved: boolean; portrait_url: string; portrait_media?: components["schemas"]["PublicCoverMedia"] | null;
    summary: string; href: string; relation_label: string; source_href: string | null;
  }[];
  reading_paths: { id: string; title: string; slug: string; href: string; introduction: string; relation_label: string }[];
  sources: SubdisciplineSource[];
};

export type SubdisciplineListItem = Pick<Subdiscipline,
  "id" | "name" | "slug" | "description" | "hero_image" | "cover_media" | "research_object" | "featured" | "href"
> & { discipline: Pick<Discipline, "id" | "name" | "slug"> | null };
