import { loadWorks } from "@/lib/api/catalog.server";
import { loadRecommendedScholars, loadRecommendations, recommendationWorks, recommendationSlugs } from "@/lib/api/recommendations.server";
import { loadRecommendationIssues } from "@/lib/api/recommendation-issues.server";
import { loadSiteConfig } from "@/lib/api/site.server";
import { loadHotSearches } from "@/lib/api/search.server";
import { loadTopic, loadTopics } from "@/lib/api/topics.server";
import { loadScholars } from "@/lib/api/people.server";

export async function loadHomeViewData() {
  const recommendationsPromise = loadRecommendations();
  const [works, topics, config, recommendations, hotSearches, selectedScholars, scholars, issues] = await Promise.all([
    loadWorks(), loadTopics(), loadSiteConfig(), recommendationsPromise, loadHotSearches(),
    recommendationsPromise.then(bundle => loadRecommendedScholars(bundle, 6)), loadScholars(), loadRecommendationIssues(),
  ]);
  const selectedTopics = recommendationSlugs(recommendations, "home_topics", "topic");
  const topicsBySlug = new Map(topics.map(topic => [topic.slug, topic]));
  // A curated topic can be outside the first directory page. Resolve the exact
  // public detail rather than silently dropping a valid selection.
  const resolvedTopics = selectedTopics.length ? await Promise.all(selectedTopics.slice(0, 5).map(slug => topicsBySlug.get(slug) ?? loadTopic(slug))) : topics.slice(0, 5);
  const shownTopics = resolvedTopics.filter((topic): topic is NonNullable<typeof topic> => topic !== null);
  const random = recommendationWorks(recommendations, "home_random");
  const scholarPool = [...selectedScholars, ...scholars.filter(scholar => !selectedScholars.some(selected => selected.slug === scholar.slug))];
  return { config, works, topics: shownTopics, scholars: scholarPool, randomWorks: random.length ? random : works, issue: issues.current, hotSearches };
}
