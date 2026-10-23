import type { SiteConfig } from "../site-config";
import type { ApiWork } from "./public-catalog";
import type { ApiScholar } from "./people.types";
import type { ApiTopic } from "./topics.types";
import type { EditorialCurator, RecommendationIssue } from "./recommendation-issues.types";

export type HomeSection = { status: "ready" | "empty" | "unavailable"; source: string; count: number | null; message: string };
export type HomeSections = Record<"works" | "random_works" | "scholars" | "topics" | "issues" | "hot_searches" | "config", HomeSection> & {home_layout?: HomeSection};
export type HomeArea = "featured" | "scholars" | "topics";
export type HomeTarget = {type: "issue" | "scholar" | "topic" | "edition"; id: string};
export type HomeSlot = {id: string; target: HomeTarget; title: string; description: string; cover_rendition_id: string | null; visible: boolean};
export type HomeLayout = Record<HomeArea, HomeSlot[] | null>;
export type HomeCard = {curator?:EditorialCurator|null;id: string; title: string; description: string; href: string; image_url: string; label: string; available: boolean; visible: boolean; source_title?:string; source_description?:string; source_image_url?:string};
export type HomeLayoutPreview = Record<HomeArea, HomeCard[] | null>;
export type HomeResponse = {
  home_layout?: HomeLayoutPreview | null;
  schema_version: "4.0"; visibility: "public"; status: "ready" | "empty" | "partial" | "unavailable";
  config: SiteConfig | null; works: ApiWork[]; random_works: ApiWork[]; scholars: ApiScholar[];
  topics: ApiTopic[]; issues: RecommendationIssue[]; issue: RecommendationIssue | null;
  issue_count: number | null; hot_searches: string[]; sections: HomeSections;
};
