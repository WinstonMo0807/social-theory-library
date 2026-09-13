// Compatibility exports for existing imports. New consumers import their exact API domain.
// Implementations, private transport and presentation-only types live separately in lib/api.
export type { ApiWork, ReaderManifest, ReaderOutlineItem } from "./api/public-catalog";
export type { PublicCuratedClaim, PublicCuratedClaimGroups, PublicKnowledgeNodeLink } from "./api/curation.types";
export type { ApiScholar } from "./api/people.types";
export type { ApiTheorySchool, TheoryTimelineEvent, TheoryGraph, TheoryDirectoryFilters } from "./api/theories.types";
export type { ApiTopic, LibraryTopic } from "./api/topics.types";
export type { Discipline, Subdiscipline } from "./api/taxonomy.types";
export type { AboutPageBlock, SiteStats } from "./api/site.types";
export type { RecommendationItem, RecommendationPlacement, RecommendationBundle } from "./api/recommendations.types";
export type { DirectoryPage } from "./api/pagination";
export type { TheoryDisciplineCompact, TheoryPersonLink, TheoryWorkCompact, KnowledgeNodeListItem, TheoryEvidence, TheoryWorkRelation, NormalizedKnowledgeRelation, KnowledgeNodeDetail, NormalizedTimelineEvent, NormalizedReadingPathItem, NormalizedReadingPath, TheorySystemOverview, TheoryDisciplinePage, LocalTheoryGraph } from "./api/knowledge.types";
export type { ScopedSearchResult, ScopedSearchEnvelope, SearchFacetOption, SearchFilters, SemanticSearchResult, SemanticSearchPayload, ViewpointStance, ViewpointSearchResult, ViewpointFacetOption, ViewpointFacets, ViewpointSearchPayload } from "./api/search.types";
export { ServerApiError } from "./api/server-request";
export { loadSiteConfig, loadSiteStats, loadAboutBlocks } from "./api/site.server";
export { loadDisciplines, loadSubdisciplinePage, loadSubdisciplines, loadSubdiscipline, loadKnowledgeMatrix } from "./api/taxonomy.server";
export { loadTheorySystemOverview, loadTheorySystemNodes, loadKnowledgeNode, loadTheoryDisciplinePage, loadNormalizedTheoryTimeline, loadNormalizedTheoryTimelinePage, loadLocalTheoryGraph, loadNormalizedReadingPaths, loadNormalizedReadingPath } from "./api/knowledge.server";
export { loadScopedSearch, loadHotSearches, loadSearch, loadSemanticSearch, loadViewpointSearch } from "./api/search.server";
export { loadTheoryTimeline, loadTheoryGraph, loadTheorySchools, loadTheorySchoolPage, loadTheoryEntity, loadTheorySchool } from "./api/theories.server";
export { loadRecommendations, recommendationWorks, recommendationSlugs, loadRecommendedScholars } from "./api/recommendations.server";
export { adaptWork, loadWorks, loadCatalogOverview, loadWork } from "./api/catalog.server";
export { loadScholarPage, loadScholars, loadScholar } from "./api/people.server";
export { loadTopics, loadTopicPage, loadTopic } from "./api/topics.server";
export { loadReaderManifest } from "./api/reader.server";
