// Existing public presentation contracts. Only schema-backed imports are generated.
import type { PublicKnowledgeNodeLink, PublicCuratedClaimGroups } from "./curation.types";
import type { components } from "./generated/schema";
import type { ApiWork } from "./public-catalog";

type ApiPerson = {
  preferred_name: string;
  original_name: string;
  aliases: string[];
  portrait?: string;
  portrait_media?: components["schemas"]["PublicCoverMedia"] | null;
  birth_year?: number | null;
  death_year?: number | null;
  biography?: string;
  scholar_slug?: string | null;
};

export type ApiScholar = {
  slug: string;
  person: ApiPerson & { id: string };
  short_description: string;
  affiliations: string[];
  key_concerns: string[];
  timeline: [string, string][];
  featured_quote: string;
  quote_source?: string;
  works: ApiWork[];
  knowledge_nodes?: PublicKnowledgeNodeLink[];
  curated_claims?: PublicCuratedClaimGroups;
  curated?: {
    essential_works: ApiWork[];
    key_concepts: Array<{
      name?: string;
      description?: string;
      source?: string;
    } | string>;
    concept_map: Array<{
      source?: string;
      target?: string;
      relation?: string;
      description?: string;
      label?: string;
    } | string>;
    network: {
      scholar: { id: string; name: string; slug: string };
      relation: string;
      source: string;
    }[];
    frequently_read_scholars: { id: string; name: string; slug: string }[];
    related_theories: {
      id: string;
      name: string;
      slug: string;
      description?: string;
      symbol?: string;
    }[];
  };
};
