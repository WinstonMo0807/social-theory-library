"use client";

import Link from "next/link";
import { useState } from "react";
import { HomePublicView, type HomeViewData } from "@/components/public/home-public-view";
import type { RecommendationIssue } from "@/lib/api/recommendation-issues.types";

const examples = [
  ["技术、权力与人的未来", "从日常经验出发，阅读技术与社会相互塑造的过程。", "/editorial/library-architecture-hero.webp"],
  ["社会不平等与流动", "在不同的时代与社会，理解机会、结构与个人生活。", "/visual/stl4/subdisciplines/featured-shelves.webp"],
  ["地方知识与日常生活", "回到具体生活，关注经验、习惯与制度之间的关系。", "/visual/stl4/subdisciplines/featured-branches.webp"],
  ["城市中的公共生活", "街道、邻里与公共空间，如何改变人们的相遇？", "/visual/stl4/subdisciplines/topic-street-final-r2.png"],
];

export function LayoutPreview({ data }: { data: HomeViewData }) {
  const [navigation, setNavigation] = useState("inline");
  const [count, setCount] = useState(4);
  const [pictures, setPictures] = useState(true);
  const [notice, setNotice] = useState("");
  const issues: RecommendationIssue[] = examples.slice(0, count).map(([title, introduction, cover], index) => ({
    id: `layout-example-${index}`, slug: `layout-example-${index}`, title, introduction,
    issue_label: `第 ${String(count - index).padStart(2, "0")} 期`, cover_url: pictures ? cover : "",
    body_blocks: [], public_byline: "", display_from: null, published_at: null, items: [], edit_version: "",
  }));
  return <div className="stl-layout-preview" data-navigation={navigation}>
    <details className="stl-layout-controls" open>
      <summary>首页排版参考</summary>
      <div className="stl-layout-options">
        <fieldset><legend>导航位置</legend>{[["inline", "与 Logo 同行"], ["top", "顶行"]].map(([value, label]) => <label key={value}><input type="radio" name="navigation-position" value={value} checked={navigation === value} onChange={() => setNavigation(value)} />{label}</label>)}</fieldset>
        <fieldset><legend>特别策划</legend><label><span>期数</span><select value={count} onChange={event => { setCount(Number(event.target.value)); setNotice(""); }}>{[1,2,3,4].map(value => <option key={value} value={value}>{value} 期</option>)}</select></label><label><input type="checkbox" checked={pictures} onChange={event => setPictures(event.target.checked)} />显示配图</label></fieldset>
      </div>
      <footer><span>策划内容为示例</span><Link href="/home">返回首页</Link></footer>
    </details>
    {notice ? <p className="stl-layout-notice" role="status">{notice} <Link href="/recommendations">查看已发布策划</Link></p> : null}
    <div onClickCapture={event => {
      if ((event.target as Element).closest('a[href^="/recommendations/layout-example-"]')) {
        event.preventDefault(); event.stopPropagation(); setNotice("这张卡片是排版示例，尚无文章正文。");
      }
    }}>
      <HomePublicView {...data} preview issues={issues} issue={issues[0]} issueCount={count} homeLayout={{ featured: null, scholars: data.homeLayout?.scholars ?? null, topics: data.homeLayout?.topics ?? null }} />
    </div>
  </div>;
}
