import type { components } from "./generated/schema";
import type { EvidenceCurationItem } from "./evidence-curation.types";
import type { PublicReadingPath } from "./reading-paths.types";
import type { TimelineEvent } from "./timeline.types";
import type { ScholarProse } from "./scholar-prose";

export type ScholarSection = "overview" | "works" | "concepts" | "questions" | "timeline" | "relations" | "topics" | "paths" | "sources" | "evidence";
export type ScholarSearchParams = Record<string, string | string[] | undefined>;
export type ScholarPage<T> = { count: number; page: number; page_size: number; total_pages: number; next: string | null; previous: string | null; results: T[] };
export type ScholarFacet = { value: string; label: string; count: number };
export type ScholarLink = { id: string; slug: string; name: string; href: string };
export type ScholarRevision = { token: string; id: string | null; number: number | null; published_at: string | null; change_note: string };
export type ScholarPerson = {
  id: string; preferred_name: string; original_name: string; aliases: string[];
  birth_year: number | null; death_year: number | null; biography: string;
  portrait: string; portrait_media: components["schemas"]["PublicCoverMedia"] | null;
};
export type PublicScholarCard = {
  id: string; person_id: string; slug: string; href: string; person: ScholarPerson;
  short_description: string; affiliations: string[]; key_concerns: string[];
  nationalities: string[]; occupations: string[]; matched_alias: string;
  fields: ScholarLink[]; schools: ScholarLink[]; work_count: number; authored_work_count: number;
  profile_state: "available" | "sparse";
};
export type PublicScholarDirectory = ScholarPage<PublicScholarCard> & {
  query: string; filters: { field: string[]; period: string[]; school: string[]; sort: "relevance" | "name" | "birth" | "works" };
  facets: { fields: ScholarFacet[]; periods: ScholarFacet[]; schools: ScholarFacet[] };
  period_notice: string;
  recommendations: { revision_id: string | null; source: string; title: string; results: PublicScholarCard[] };
  curated_topics: { id: string; slug: string; title: string; summary: string; href: string; image_url: string }[];
  related_topics: ScholarLink[];
};
export type ScholarChapter = {
  title: string; asset_id: string; document_revision_id: string;
  outline_revision_id: string; outline_node_id: string;
  page_start: number; page_end: number; reader_href: string;
};
export type ScholarContributionScope = { kind: "edition" | "chapter"; status: "available" | "unavailable"; chapters: ScholarChapter[]; notice: string };
export type ScholarWork = {
  id: string; edition_id: string; catalog_revision_id: string; title: string; original_title: string;
  href: string; cover_url: string; cover_media?: components["schemas"]["PublicCoverMedia"] | null; document_type: string; language: string; publication_year: number | null;
  version_label: string; roles: string[]; role_labels: string[];
  contributions: { person_id: string; name: string; role: string; role_label: string; scope: ScholarContributionScope }[];
  source_status: "available" | "no_fulltext"; reader_href: string; is_essential: boolean; is_recommended?: boolean; recommendation_reason?: string;
};
export type ScholarKnowledge = ScholarLink & {
  node_type: string; summary: string; relation_label: string; relation_source: "person_relation" | "published_work_relation";
  source_count: number; scholar_count: number;
};
export type ScholarRelationRow = {
  assertion_id?: string; assertion?: import("@/components/public/knowledge-page-content").KnowledgeAssertion;
  source_material?: components["schemas"]["RelationAnchorMaterial"] | null;
  id: string; source_scholar: string; target_scholar: string; source_name: string; target_name: string;
  source_slug: string; target_slug: string; relation_type: string; relation_label: string;
  direction: "directed" | "bidirectional" | "undirected"; summary: string; source: string; status: string;
};
export type ScholarProfileSource = { id: string; title: string; url: string; fields: string[]; note: string };
export type PublicScholarDetail = PublicScholarCard & {
  profile_prose?: ScholarProse;
  public_revision: ScholarRevision; period_notice: string;
  graph_href: string; research_href: string;
  counts: Record<Exclude<ScholarSection, "overview">, number>;
  recommended_works: ScholarWork[]; works: ScholarPage<ScholarWork>; concepts: ScholarPage<ScholarKnowledge>; questions: ScholarPage<ScholarKnowledge>;
  timeline: ScholarPage<TimelineEvent>; relations: ScholarPage<ScholarRelationRow>;
  topics: ScholarPage<ScholarLink & { description: string }>; paths: ScholarPage<PublicReadingPath>;
  sources: ScholarPage<ScholarProfileSource>; evidence: ScholarPage<EvidenceCurationItem>;
  featured_quote: EvidenceCurationItem | null;
  disambiguation: PublicScholarCard[];
  candidate_access: { allowed: boolean; requested: boolean; notice: string; review_href: string };
  candidate_relations: ScholarPage<ScholarRelationRow> | null;
  filters: { section: ScholarSection; role: string[]; relation_type: string[]; relation_direction: "all" | "incoming" | "outgoing" };
  facets: { roles: ScholarFacet[]; relation_types: ScholarFacet[] };
};
