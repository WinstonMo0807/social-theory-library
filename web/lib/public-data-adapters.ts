import type { Scholar, TheorySchool, Work } from "./data";
import type {
  ApiScholar,
  ApiTopic,
  ApiWork,
  LibraryTopic,
  PublicCuratedClaimGroups,
  PublicKnowledgeNodeLink,
} from "./server-api";

const coverStyles: Work["cover"][] = ["dark", "paper", "cream", "line"];

export function adaptApiWork(value: ApiWork, index = 0): Work {
  const authorContributions = value.edition?.contributors.filter((row) => row.role === "author") ?? [];
  return {
    id: value.edition?.readable_asset?.id ?? value.id,
    workId: value.id,
    editionId: value.edition?.id,
    slug: value.edition?.public_slug ?? value.id,
    title: value.title,
    originalTitle: value.subtitle || undefined,
    author: authorContributions.map((row) => row.person.preferred_name).join("、") || "责任者待补",
    year: String(value.edition?.publication_year ?? "出版年不详"),
    kind: ({
      book: "图书",
      journal_article: "期刊论文",
      thesis: "学位论文",
      report: "研究报告",
    } satisfies Record<ApiWork["document_type"], Work["kind"]>)[value.document_type],
    school: value.theories[0]?.name ?? value.topics[0]?.name ?? "社会理论",
    summary: value.abstract || "本馆已收录全文，简介待编辑。",
    cover: coverStyles[index % coverStyles.length],
    coverImage: value.cover || value.recommendation_image || undefined,
    pages: value.edition?.readable_asset?.page_count ?? 0,
    language: value.language,
    authors: authorContributions.map((row) => ({
      name: row.person.preferred_name,
      slug: row.person.scholar_slug,
    })),
    theories: value.theories,
    topics: value.topics,
    theoryAssociations: value.theory_associations ?? [],
    curatedClaims: value.curated_claims,
    outline: value.outline ?? [],
  };
}

export function adaptApiScholar(value: ApiScholar): Scholar {
  const birth = value.person.birth_year;
  const death = value.person.death_year;
  return {
    id: value.person.id,
    slug: value.slug,
    name: value.person.preferred_name,
    originalName: value.person.original_name || value.person.preferred_name,
    portrait: value.person.portrait || undefined,
    years: birth ? `${birth}—${death ?? ""}` : "",
    school: "本馆收录学者",
    concerns: value.key_concerns ?? [],
    biography: value.person.biography || value.short_description || "本馆已建立该学者与馆藏作品的关系。",
  };
}

export type ScholarDetailData = {
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
    keyConcepts: Array<{ name?: string; description?: string; source?: string } | string>;
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
};

export function adaptApiScholarDetail(payload: ApiScholar): ScholarDetailData {
  return {
    scholar: adaptApiScholar(payload),
    shortDescription: payload.short_description || payload.person.biography || "本馆已建立该学者与馆藏作品的关系。",
    works: (payload.works ?? []).map(adaptApiWork),
    affiliations: payload.affiliations ?? [],
    timeline: payload.timeline ?? [],
    featuredQuote: payload.featured_quote ?? "",
    quoteSource: payload.quote_source ?? "",
    curatedClaims: payload.curated_claims ?? {
      core_viewpoint: [],
      major_criticism: [],
      major_response: [],
    },
    knowledgeNodes: payload.knowledge_nodes ?? [],
    curated: {
      essentialWorks: (payload.curated?.essential_works ?? []).map(adaptApiWork),
      keyConcepts: payload.curated?.key_concepts ?? [],
      conceptMap: payload.curated?.concept_map ?? [],
      network: payload.curated?.network ?? [],
      frequentlyReadScholars: payload.curated?.frequently_read_scholars ?? [],
      relatedTheories: payload.curated?.related_theories ?? [],
    },
  };
}

export function adaptApiTopic(payload: ApiTopic): LibraryTopic {
  return {
    id: payload.id,
    slug: payload.slug,
    name: payload.name,
    description: payload.description,
    problemStatement: payload.problem_statement,
    coreQuestions: payload.core_questions ?? [],
    researchDimensions: payload.research_dimensions ?? [],
    methods: payload.methods ?? [],
    formationContext: payload.formation_context,
    heroImage: payload.hero_image,
    disciplines: payload.disciplines ?? [],
    subdisciplines: payload.subdisciplines ?? [],
    linkedTheories: payload.linked_theories ?? [],
    knowledgeNodes: payload.knowledge_nodes ?? [],
    concepts: payload.key_concepts ?? [],
    timeline: payload.timeline ?? [],
    works: (payload.works ?? []).map(adaptApiWork),
    scholars: (payload.scholars ?? []).map(adaptApiScholar),
    theories: (payload.theories ?? []).map((school) => ({
      slug: school.slug,
      name: school.name,
      description: school.description,
      books: school.work_count,
      scholars: school.scholars?.length ?? 0,
      symbol: school.symbol || school.name.slice(0, 2),
    } satisfies TheorySchool)),
    passages: (payload.passages ?? []).map((passage) => ({
      id: passage.id,
      assetId: passage.asset_id,
      title: passage.title,
      pageIndex: passage.page_index,
      printedLabel: passage.printed_label,
      snippet: passage.snippet,
    })),
    workCount: payload.work_count,
    curatedClaims: payload.curated_claims ?? {
      core_viewpoint: [],
      major_criticism: [],
      major_response: [],
    },
    curated: {
      heroCaption: payload.curated?.hero_caption ?? "",
      foundationalWorks: (payload.curated?.foundational_works ?? []).map(adaptApiWork),
      recentWorks: (payload.curated?.recent_works ?? []).map(adaptApiWork),
      relatedScholars: payload.curated?.related_scholars ?? [],
      linkedTheories: payload.curated?.linked_theories ?? [],
      readingPaths: (payload.curated?.reading_paths ?? []).map((path) => ({
        ...path,
        works: (path.works ?? []).map(adaptApiWork),
      })),
      featuredPassageId: payload.curated?.featured_passage_id ?? "",
      featuredPassageReason: payload.curated?.featured_passage_reason ?? "",
      featuredPassageEvidence: payload.curated?.featured_passage_evidence ?? {},
    },
  };
}
