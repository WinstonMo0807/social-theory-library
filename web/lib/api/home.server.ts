import { adaptApiScholar, adaptApiTopic, adaptApiWork } from "../public-data-adapters";
import { defaultSiteConfig } from "../site-config";
import { serverRequest } from "./server-request";
import type { HomeResponse } from "./home.types";
import type { HomeViewData } from "@/components/public/home-public-view";

export async function loadHomeViewData(): Promise<HomeViewData> {
  const payload = await serverRequest<HomeResponse>("/catalog/home/");
  return {
    config: payload.config ?? defaultSiteConfig,
    works: payload.works.map(adaptApiWork), randomWorks: payload.random_works.map(adaptApiWork),
    scholars: payload.scholars.map(adaptApiScholar), topics: payload.topics.map(adaptApiTopic),
    issue: payload.issue, issues: payload.issues, issueCount: payload.issue_count,
    hotSearches: payload.hot_searches, sections: payload.sections,
  };
}
