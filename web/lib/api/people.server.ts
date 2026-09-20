// Server-side public API domain. Browser components use pure adapters and type-only imports.
import { type Scholar, scholars as demoScholars, type Work, works as demoWorks } from "../data";
import { adaptApiScholar, adaptApiScholarDetail } from "../public-data-adapters";
import type { PublicCuratedClaimGroups, PublicKnowledgeNodeLink } from "./curation.types";
import { type DirectoryPage, type Paginated, directoryPage } from "./pagination";
import type { ApiScholar } from "./people.types";
import { serverRequest, allowDemoFallback, ServerApiError } from "./server-request";
import type { PublishedEvidenceCuration } from "./evidence-curation.types";

const adaptScholar = adaptApiScholar;

export async function loadScholarPage(query = "", page = 1): Promise<DirectoryPage<Scholar>> {
  try {
    const parameters = new URLSearchParams({ page: String(page) });
    if (query) parameters.set("q", query);
    const payload = await serverRequest<Paginated<ApiScholar>>(`/catalog/scholars/?${parameters.toString()}`);
    return directoryPage(
      { ...payload, results: payload.results.map(adaptScholar) },
      page,
    );
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return directoryPage({ count: demoScholars.length, results: demoScholars }, page);
  }
}

export async function loadScholars(query = ""): Promise<Scholar[]> {
  return (await loadScholarPage(query)).results;
}

export async function loadScholar(slug: string): Promise<{
  evidenceCuration?: PublishedEvidenceCuration;
  profileId?: string;
  scholar: Scholar;
  shortDescription: string;
  works: Work[];
  affiliations: string[];
  timeline: [string, string][];
  featuredQuote: string;
  quoteSource: string;
  curatedClaims: PublicCuratedClaimGroups;
  knowledgeNodes: PublicKnowledgeNodeLink[];
  curated: {
    essentialWorks: Work[];
    keyConcepts: Array<{
      name?: string;
      description?: string;
      source?: string;
    } | string>;
    conceptMap: Array<{
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
    frequentlyReadScholars: { id: string; name: string; slug: string }[];
    relatedTheories: {
      id: string;
      name: string;
      slug: string;
      description?: string;
      symbol?: string;
    }[];
  };
} | null> {
  try {
    const payload = await serverRequest<ApiScholar>(
      `/catalog/scholars/${encodeURIComponent(slug)}/`,
    );
    const evidenceCuration = await serverRequest<PublishedEvidenceCuration>(`/catalog/evidence-curation/scholar/${payload.id}/`);
    return { ...adaptApiScholarDetail(payload), evidenceCuration };
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404 && error.path === `/catalog/scholars/${encodeURIComponent(slug)}/`) return null;
    if (!allowDemoFallback) throw error;
    const scholar = demoScholars.find((item) => item.slug === slug);
    return scholar
      ? {
          scholar,
          shortDescription: scholar.biography,
          works: demoWorks.filter((work) => work.author.includes(scholar.name.split("·").at(-1) ?? scholar.name)),
          affiliations: [],
          timeline: [],
          featuredQuote: "",
          quoteSource: "",
          curatedClaims: {
            core_viewpoint: [],
            major_criticism: [],
            major_response: [],
          },
          knowledgeNodes: [],
          curated: {
            essentialWorks: [],
            keyConcepts: [],
            conceptMap: [],
            network: [],
            frequentlyReadScholars: [],
            relatedTheories: [],
          },
        }
      : null;
  }
}
