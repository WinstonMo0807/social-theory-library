import type { SiteConfig } from "../site-config";
import type { ApiWork } from "./public-catalog";
import type { ApiScholar } from "./people.types";
import type { ApiTopic } from "./topics.types";
import type { RecommendationIssue } from "./recommendation-issues.types";

export type HomeSection = { status: "ready" | "empty" | "unavailable"; source: string; count: number | null; message: string };
export type HomeSections = Record<"works" | "random_works" | "scholars" | "topics" | "issues" | "hot_searches" | "config", HomeSection>;
export type HomeResponse = {
  schema_version: "4.0"; visibility: "public"; status: "ready" | "empty" | "partial" | "unavailable";
  config: SiteConfig | null; works: ApiWork[]; random_works: ApiWork[]; scholars: ApiScholar[];
  topics: ApiTopic[]; issues: RecommendationIssue[]; issue: RecommendationIssue | null;
  issue_count: number | null; hot_searches: string[]; sections: HomeSections;
};
