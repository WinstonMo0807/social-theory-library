import { HomeFeatureStory } from "@/components/public/home-feature-story";
import { loadHomeViewData } from "@/lib/api/home.server";

export const metadata = { title: "欢迎", description: "从社会理论原典出发，寻找观点、核对引文，留下自己的思考。" };

export default async function WelcomePage() {
  const { config, works } = await loadHomeViewData();
  return <HomeFeatureStory
    books={works.slice(0, 3).map(({ id, title, author, coverImage }) => ({ id, title, author, coverImage }))}
    closingTitle={[config.home_title_left_lines.join(""), config.home_title_right_lines.join("")]}
    closingImage={config.home_hero_image || "/editorial/generated-20261030/home.webp"}
  />;
}
