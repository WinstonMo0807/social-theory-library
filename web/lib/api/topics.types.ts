// Existing public presentation contracts. Only schema-backed imports are generated.
import type { Work, Scholar, TheorySchool } from "../data";
import type { PublicKnowledgeNodeLink, PublicCuratedClaimGroups } from "./curation.types";
import type { ApiScholar } from "./people.types";
import type { ApiWork } from "./public-catalog";
import type { ApiTheorySchool } from "./theories.types";

export type ApiTopic = {
  id: string;
  slug: string;
  name: string;
  description: string;
  problem_statement: string;
  core_questions: string[];
  research_dimensions: string[];
  methods: string[];
  formation_context: string;
  hero_image: string;
  disciplines: { id: string; name: string; slug: string; is_primary: boolean }[];
  subdisciplines: { id: string; name: string; slug: string; relation_label: string }[];
  linked_theories: { id: string; name: string; slug: string; relation_label: string }[];
  knowledge_nodes?: PublicKnowledgeNodeLink[];
  key_concepts: string[];
  timeline: [string, string, string][];
  work_count: number;
  works?: ApiWork[];
  scholars?: ApiScholar[];
  theories?: ApiTheorySchool[];
  passages?: {
    id: string;
    asset_id: string;
    title: string;
    page_index: number;
    printed_label: string;
    snippet: string;
  }[];
  curated_claims?: PublicCuratedClaimGroups;
  curated?: {
    hero_caption: string;
    foundational_works: ApiWork[];
    recent_works: ApiWork[];
    related_scholars: { id: string; name: string; slug: string }[];
    linked_theories: { id: string; name: string; slug: string }[];
    reading_paths: {
      title: string;
      description: string;
      level: string;
      works: ApiWork[];
    }[];
    featured_passage_id: string;
    featured_passage_reason?: string;
    featured_passage_evidence?: Record<string, unknown>;
  };
};

export type LibraryTopic = {
  evidenceCuration?: import("./evidence-curation.types").PublishedEvidenceCuration;
  id: string;
  slug: string;
  name: string;
  description: string;
  problemStatement: string;
  coreQuestions: string[];
  researchDimensions: string[];
  methods: string[];
  formationContext: string;
  heroImage: string;
  disciplines: { id: string; name: string; slug: string; is_primary: boolean }[];
  subdisciplines: { id: string; name: string; slug: string; relation_label: string }[];
  linkedTheories: { id: string; name: string; slug: string; relation_label: string }[];
  knowledgeNodes: PublicKnowledgeNodeLink[];
  concepts: string[];
  timeline: [string, string, string][];
  works: Work[];
  scholars: Scholar[];
  theories: TheorySchool[];
  passages: {
    id: string;
    assetId: string;
    title: string;
    pageIndex: number;
    printedLabel: string;
    snippet: string;
  }[];
  workCount: number;
  curatedClaims: PublicCuratedClaimGroups;
  curated: {
    heroCaption: string;
    foundationalWorks: Work[];
    recentWorks: Work[];
    relatedScholars: { id: string; name: string; slug: string }[];
    linkedTheories: { id: string; name: string; slug: string }[];
    readingPaths: {
      title: string;
      description: string;
      level: string;
      works: Work[];
    }[];
    featuredPassageId: string;
    featuredPassageReason: string;
    featuredPassageEvidence: Record<string, unknown>;
  };
};

// PDF68–71 public routes use the following paginated contract.
import type { EvidenceCurationItem } from "./evidence-curation.types";
import type { PublicReadingPath } from "./reading-paths.types";
import type { PublicScholarCard, ScholarPage, ScholarRevision, ScholarWork } from "./scholars.types";

export type TopicSection = "overview" | "questions" | "works" | "scholars" | "concepts" | "articles" | "paths" | "evidence";
export type TopicSearchParams = Record<string, string | string[] | undefined>;
export type TopicPage<T> = ScholarPage<T>;
export type TopicLink = { id: string; slug: string; name: string; href: string };
export type TopicHierarchy = TopicLink & { parent_id: string | null; child_count: number; descendant_count: number; count: number };
export type PublicTopicCard = TopicLink & {
  description: string; problem_statement: string; hero_image: string; tags: string[]; matched_alias: string;
  parent: TopicLink | null; work_count: number; edition_count: number; scholar_count: number;
  question_count: number; profile_state: "available" | "sparse";
};
export type TopicDirectory = TopicPage<PublicTopicCard> & {
  query: string; filters: { parent: string; parents: string[]; discipline: string; subdiscipline: string; theory: string; sort: "relevance" | "name" | "works" | "updated" };
  hierarchy: TopicHierarchy[]; selected_parent: TopicLink | null; selected_parents: TopicLink[];
  recommendations: { revision_id: string | null; source: string; results: PublicTopicCard[] };
  disambiguation: PublicTopicCard[]; overlap_notice: string;
};
export type TopicKnowledge = TopicLink & {
  node_type: "research_problem" | "debate" | "concept"; summary: string; relation_label: string;
  work_count: number; discussion_count: number; response_count: number; count_notice: string;
};
export type TopicWork = Omit<ScholarWork, "edition_id" | "catalog_revision_id" | "source_status"> & {
  edition_id: string | null; catalog_revision_id: string | null;
  source_status: "available" | "no_fulltext" | "planned";
  source_notice: string; selection: "related" | "foundational" | "disputed";
  issue_id: string | null; issue_item_id: string | null;
};
export type TopicArticle = { id: string; slug: string; title: string; summary: string; href: string; cover_url: string; public_byline: string; published_at: string | null };
export type TopicUnavailable = { id: string; kind: "question" | "concept" | "work" | "scholar" | "article" | "path"; status: "unavailable"; notice: string };
export type TopicLegacyWork = { id: string; title: string; href: string; notice: string };
export type PublicTopicDetail = PublicTopicCard & {
  public_revision: ScholarRevision; breadcrumbs: TopicLink[]; children: TopicLink[];
  introduction: { description: string; problem_statement: string; formation_context: string; core_questions: string[]; research_dimensions: string[]; methods: string[] };
  counts: Record<Exclude<TopicSection, "overview">, number>;
  questions: TopicPage<TopicKnowledge>; works: TopicPage<TopicWork>; scholars: TopicPage<PublicScholarCard>;
  concepts: TopicPage<TopicKnowledge>; articles: TopicPage<TopicArticle>; paths: TopicPage<PublicReadingPath>;
  evidence: TopicPage<EvidenceCurationItem>; featured_quote: EvidenceCurationItem | null;
  unavailable_links: TopicUnavailable[]; unavailable_notice: string; discussion_notice: string;
  feedback_href: string; graph_href: string; research_href: string;
  filters: { section: TopicSection; question_type: "all" | "research_problem" | "debate"; availability: "all" | "readable" | "no_fulltext" | "planned"; reading: "all" | "foundational" | "disputed"; sort: "relevance" | "published" | "title" };
  work_facets: { all: number; readable: number; no_fulltext: number; planned: number };
  legacy: { timeline: Record<string, string | number>[]; research_dimensions: string[]; methods: string[]; subdisciplines: TopicLink[]; linked_theories: TopicLink[]; theory_nodes: TopicLink[];
    curated_works: { foundational: TopicLegacyWork[]; recent: TopicLegacyWork[] };
    reading_paths: { title: string; description: string; level: string; works: TopicLegacyWork[]; unavailable_work_ids: string[]; notice: string }[];
    related_scholars: { id: string; profile_id: string; name: string; href: string; identity_kind: "person"; notice: string }[] };
};
