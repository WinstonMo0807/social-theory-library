import Link from "next/link";
import { ArrowDown, ArrowRight } from "lucide-react";
import { HomeFeatureStory } from "@/components/public/home-feature-story";
import { SiteFooter } from "@/components/site-footer";
import { loadHomeViewData } from "@/lib/api/home.server";
import styles from "./welcome.module.css";

export const metadata = { title: "欢迎", description: "从社会理论原典出发，寻找观点、核对引文，留下自己的思考。" };

export default async function WelcomePage() {
  const { config, works } = await loadHomeViewData();
  return <>
    <div className={`stl4-home ${styles.welcome}`}>
      <section className={styles.intro} aria-labelledby="welcome-title">
        <h1 id="welcome-title">{config.home_title_left_lines.join("")}<br />{config.home_title_right_lines.join("")}</h1>
        <p>从原典出发，寻找观点，留下自己的思考。</p>
        <div className={styles.actions}>
          <Link href="/" className={styles.enter}>进入书库 <ArrowRight size={18} aria-hidden="true" /></Link>
          <a href="#library-features">了解书库 <ArrowDown size={16} aria-hidden="true" /></a>
        </div>
      </section>
      <HomeFeatureStory books={works.slice(0, 3).map(({ id, title, author, coverImage }) => ({ id, title, author, coverImage }))} />
    </div>
    <SiteFooter />
  </>;
}
