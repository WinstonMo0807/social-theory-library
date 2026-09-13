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
