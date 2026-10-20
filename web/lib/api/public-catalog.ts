import type { Work } from "../data";
import type { components } from "./generated/schema";
import type { OutlineNode } from "./document-outline";

export type PublicWorkCard = components["schemas"]["WorkCard"];
export type PublicWorkDetail = components["schemas"]["WorkDetail"];
export type PublicEdition = components["schemas"]["EditionCompact"];
export type ReaderAssetAccess = components["schemas"]["ReaderAssetAccess"];
export type ReaderPageContent = components["schemas"]["ReaderPageContent"];
// The directory service's source-locator JSON has a narrower runtime contract than OpenAPI's unknown field.
export type ReaderManifestPayload = Omit<components["schemas"]["ReaderManifest"], "outline"> & { outline: OutlineNode[]; document_revision_id?: string | null };
export type ReaderOutlineItem = components["schemas"]["PublicOutlineItem"];

// Core catalog fields are generated. The existing rich curation presentation
// remains an explicitly unverified compatibility adapter until EvidenceEnvelope
// has its own complete contract; it is not claimed as generated coverage.
export type ApiWork = PublicWorkCard
  & Partial<Pick<PublicWorkDetail, "outline" | "theory_associations">>
  & { curated_claims?: Work["curatedClaims"] };

type LinkedReaderScholar = Omit<ReaderManifestPayload["related_scholars"][number], "slug"> & { slug: string };

// The page's presentation model differs from the raw API only in naming and
// Work formatting. Keep these distinctions outside the network contract.
export type ReaderManifest = {
  work: Work;
  documentRevisionId?: string | null;
  outline: ReaderManifestPayload["outline"];
  scholars: LinkedReaderScholar[];
  theories: ReaderManifestPayload["related_theories"];
  topics: ReaderManifestPayload["related_topics"];
};
