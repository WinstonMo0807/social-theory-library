import { HomeFeatureStory } from "@/components/public/home-feature-story";
import { loadHomeViewData } from "@/lib/api/home.server";
import { SiteFooterView } from "@/components/public/site-footer-view";

export const metadata = { title: "欢迎", description: "从社会理论原典出发，寻找观点、核对引文，留下自己的思考。" };

export default async function WelcomePage({ searchParams }: { searchParams: Promise<{ compare?: string }> }) {
  const [{ config, works }, params] = await Promise.all([loadHomeViewData(), searchParams]);
  return <><HomeFeatureStory
    books={works.slice(0, 3).map(({ id, title, author, coverImage }) => ({ id, title, author, coverImage }))}
    closingImage={config.home_hero_image || "/editorial/generated-20261030/home.webp"}
    brandConfig={{ site_name: config.site_name, wordmark_lines: config.wordmark_lines }}
    compareCopy={params.compare === "1"}
  /><SiteFooterView config={config} /></>;
}
