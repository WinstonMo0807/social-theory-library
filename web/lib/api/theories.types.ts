// Existing public presentation contracts. Only schema-backed imports are generated.
import type { ApiScholar } from "./people.types";
import type { ApiWork } from "./public-catalog";

export type ApiTheorySchool = {
  canonical_node_url?: string;
  id: string;
  slug: string;
  name: string;
  description: string;
  symbol: string;
  foreign_name: string;
  entity_level: "tradition" | "school" | "branch";
  formation_period: string;
  core_questions: string[];
  key_themes: string[];
  hero_image: string;
  disciplines: { id: string; name: string; slug: string; role: string }[];
  subdisciplines: { id: string; name: string; slug: string; role: string }[];
  hierarchy: {
    parents: { id: string; name: string; slug: string }[];
    branches: { id: string; name: string; slug: string }[];
  };
  relations: {
    id: string;
    direction: string;
    relation_type: string;
    strength: string;
    theory: { id: string; name: string; slug: string };
    evidence_page?: number | null;
    evidence_text?: string;
  }[];
  timeline: TheoryTimelineEvent[];
  work_count: number;
  scholar_count: number;
  works?: ApiWork[];
  scholars?: ApiScholar[];
  curated?: {
    hero_caption: string;
    foundational_works: ApiWork[];
    curated_reading_works: ApiWork[];
    key_scholars: { id: string; name: string; slug: string }[];
    neighbors: {
      id: string;
      name: string;
      slug: string;
      description?: string;
      relation?: string;
      source?: string;
    }[];
    core_concepts: Array<{
      name?: string;
      description?: string;
      source?: string;
    } | string>;
    conceptual_map: Array<{
      source?: string;
      target?: string;
      relation?: string;
      description?: string;
      label?: string;
    } | string>;
  };
};

export type TheoryTimelineEvent = {
  id: string;
  title: string;
  description: string;
  event_type: string;
  start_year: number | null;
  end_year: number | null;
  date_label: string;
  orientation: string;
  image: string;
  theory: { id: string; name: string; slug: string } | null;
  discipline: { id: string; name: string; slug: string } | null;
  subdiscipline: { id: string; name: string; slug: string } | null;
  scholar: { id: string; name: string; slug: string } | null;
  work: { id: string; title: string } | null;
  evidence_page?: number | null;
  evidence_printed_label?: string;
  evidence_text?: string;
};

export type TheoryGraph = {
  nodes: {
    id: string;
    slug: string;
    name: string;
    foreign_name: string;
    entity_level: string;
    symbol: string;
    curation_level: number;
  }[];
  edges: {
    id: string;
    source: string;
    target: string;
    relation_type: string;
    strength: string;
    evidence_page?: number | null;
    evidence_text?: string;
  }[];
};

export type TheoryDirectoryFilters = {
  theme?: string;
  discipline?: string;
  hasWorks?: boolean;
  hasScholars?: boolean;
  sort?: "name" | "works";
};
