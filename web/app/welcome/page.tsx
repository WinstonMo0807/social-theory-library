import { LibraryEntryTransition } from "@/components/public/library-entry-transition";
import { HomeFeatureStory } from "@/components/public/home-feature-story";
import { loadHomeViewData } from "@/lib/api/home.server";
import { SiteFooterView } from "@/components/public/site-footer-view";
import { welcomeDiscovery } from "@/lib/welcome";

export const dynamic = "force-dynamic";

export const metadata = { title: "欢迎", description: "从社会理论原典出发，寻找观点、核对引文，留下自己的思考。" };

export default async function WelcomePage({ searchParams }: { searchParams: Promise<{ compare?: string }> }) {
  const [home, params] = await Promise.all([loadHomeViewData(), searchParams]);
  const { config, works } = home;
  return <><LibraryEntryTransition /><HomeFeatureStory
    books={config.welcome?.edition_ids == null ? works.slice(0, 3) : config.welcome_books || []}
    content={config.welcome}
    discovery={welcomeDiscovery(home)}
    initialCopy={params.compare === "1" ? 0 : Math.floor(Math.random() * 3)}
    closingImage={config.home_hero_image || "/editorial/generated-20261030/home.webp"}
    brandConfig={{ site_name: config.site_name, wordmark_lines: config.wordmark_lines }}
    compareCopy={params.compare === "1"}
  /><SiteFooterView config={config} /></>;
}
