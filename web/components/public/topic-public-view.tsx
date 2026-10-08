"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { SaveTopicButton } from "@/components/save-topic-button";
import { BookCard, ScholarPortrait } from "@/components/ui";
import type { LibraryTopic } from "@/lib/api/topics.types";

function TopicHero({ topic, questions = false }: { topic: LibraryTopic; questions?: boolean }) {
  return <header className={"topic-reference-hero" + (questions ? " topic-question-hero" : "") + (topic.heroImage ? " has-image" : "")} data-edit-section="identity">
    {topic.heroImage ? <img src={topic.heroImage} alt=""/> : null}
    <div><h1>{topic.name}</h1><p>{topic.description}</p>
      {!questions ? <dl className="topic-reference-facts"><div><dt>相关图书</dt><dd>{topic.workCount}</dd></div>
        <div><dt>相关学者</dt><dd>{topic.scholars.length}</dd></div><div><dt>相关文章</dt><dd/></div></dl> : null}
    </div>
  </header>;
}

export function TopicPublicView({ topic, footer }: { topic: LibraryTopic; footer?: ReactNode }) {
  const works = topic.curated.foundationalWorks.length ? topic.curated.foundationalWorks : topic.works;
  const scholars = topic.curated.relatedScholars.length ? topic.scholars.filter(row => topic.curated.relatedScholars.some(item => item.slug === row.slug)) : topic.scholars;
  const href = (section: string) => "/topics/" + topic.slug + "/" + section;
  return <><main className="page-shell topic-reference-public topic-reference-overview">
    <TopicHero topic={topic}/>
    <div className="topic-reference-bookmark"><SaveTopicButton topicId={topic.id}/></div>
    <div className="topic-reference-overview-grid">
      <section data-edit-section="questions"><header><h2>研究问题</h2><Link href={href("questions")}>更多 <ArrowRight size={17}/></Link></header>
        <ul className="topic-reference-question-summary">{topic.coreQuestions.map((question,index)=><li key={index}><Link href={href("questions") + "#item-" + (index+1)}>{question}</Link></li>)}</ul>
      </section>
      <section data-edit-section="works"><header><h2>入门阅读</h2><Link href={href("works")}>更多 <ArrowRight size={17}/></Link></header>
        <div className="topic-reference-books">{works.slice(0,4).map(work=><BookCard work={work} dense key={work.id}/>)}</div>
      </section>
      <section className="topic-reference-representatives" data-edit-section="relations"><header><h2>代表学者</h2><Link href={href("scholars")}>更多 <ArrowRight size={17}/></Link></header>
        <div>{scholars.slice(0,4).map(scholar=><Link href={"/scholars/" + scholar.slug} key={scholar.slug}><ScholarPortrait scholar={scholar}/><span><strong>{scholar.name}</strong><small>{scholar.concerns.join("、")}</small></span></Link>)}</div>
      </section>
    </div>
  </main>{footer}</>;
}

export function TopicQuestionsPublicView({ topic }: { topic: LibraryTopic }) {
  const [selected, setSelected] = useState(0);
  const works = topic.curated.foundationalWorks.length ? topic.curated.foundationalWorks : topic.works;
  useEffect(()=>{
    const select = (event: Event) => {
      const index = (event as CustomEvent<unknown>).detail;
      if (typeof index === "number" && Number.isInteger(index)) setSelected(index);
    };
    window.addEventListener("topic-question-focus", select);
    return ()=>window.removeEventListener("topic-question-focus", select);
  },[]);
  return <main className="page-shell topic-reference-public topic-reference-question-page" data-public-page="questions">
    <TopicHero topic={topic} questions/>
    <div className="topic-reference-question-layout">
      <section className="topic-reference-question-content" data-edit-section="questions">
        <header><h2>研究对象与核心问题</h2><p>{topic.problemStatement}</p></header>
        <div>{topic.coreQuestions.map((question,index)=><article id={"item-" + (index+1)} key={index} data-edit-row={index} data-selected={selected===index || undefined}>
          <span>{index+1}</span><div><h3>{question}</h3><p className="topic-reference-question-explanation"/></div>
          <Link aria-label={"查找与" + question + "相关的馆藏"} href={"/explore?q=" + encodeURIComponent(question) + "&topic=" + encodeURIComponent(topic.slug)}><ArrowRight size={20}/></Link>
        </article>)}</div>
      </section>
      <aside><section><h2>形成与发展</h2><nav aria-label="主题相关内容">
        <Link href={"/topics/" + topic.slug + "/history"}>历史脉络 <ArrowRight size={18}/></Link>
        <Link href={"/topics/" + topic.slug + "/theory-schools"}>主要理论视角 <ArrowRight size={18}/></Link>
        <span aria-disabled="true">当代议题与新挑战 <ArrowRight size={18}/></span>
      </nav></section><section data-edit-section="works"><h2>入门阅读</h2>{works.slice(0,1).map(work=><BookCard work={work} dense key={work.id}/>)}</section></aside>
    </div>
  </main>;
}
