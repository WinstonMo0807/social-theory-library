"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { ArrowRight, BookOpen, Check, FileText, FolderOpen, NotebookPen, Pause, Play, Plus, RotateCcw, Search } from "lucide-react";
import styles from "./home-feature-story.module.css";

type StoryBook = { id: string; title: string; author: string; coverImage?: string };
const chapters = [
  { title: "先提出你的问题", text: "用自己的话检索观点，也可以沿着学者、流派与主题找到书。", href: "/explore/opinions", action: "检索观点" },
  { title: "读到观点的来处", text: "从原文节选打开 PDF，连同前后文一起阅读。", href: "/explore/original", action: "查找原文" },
  { title: "让引文有据可查", text: "回到具体版本与页码，核对原文，再决定如何引用。", href: "/account/citation-audits", action: "核对引文" },
  { title: "留下自己的思考", text: "把材料、笔记与阅读计划保存在读者中心，下次接着读。", href: "/account", action: "进入读者中心" },
];

function TextLines({ highlighted = false }: { highlighted?: boolean }) {
  return <div className={styles.lines} data-highlighted={highlighted || undefined}>
    <i /><i /><i /><i /><i />
  </div>;
}

// These are illustrations of the workflow, never generated quotations or query results.
function StoryScene({ chapter, books }: { chapter: number; books: StoryBook[] }) {
  const book = books[0];
  return <div className={styles.scene} data-scene={chapter} aria-hidden="true">
    {chapter === 0 ? <>
      <div className={styles.question}><Search size={21} strokeWidth={1.5} /><span>社会如何被理解？</span><ArrowRight size={20} /></div>
      <div className={styles.bookShelf}>{(books.length ? books : [{ id: "empty", title: "社会理论", author: "" }]).map((entry) => <div className={styles.book} key={entry.id}>
        {entry.coverImage ? <img src={entry.coverImage} alt="" loading="lazy" width={124} height={178} /> : <div className={styles.bookFallback}><BookOpen size={32} strokeWidth={1} /><span>{entry.title}</span></div>}
        <strong>{entry.title}</strong><span>{entry.author}</span>
      </div>)}</div>
      <div className={styles.discoveryTerms}><span>学者</span><i /><span>理论</span><i /><span>主题</span></div>
    </> : null}
    {chapter === 1 ? <div className={styles.readingDesk}>
      <div className={styles.sourceSlip}><BookOpen size={21} strokeWidth={1.4} /><span>{book?.title || "原文阅读"}</span></div>
      <div className={styles.openPages}><div className={styles.paperPage}><span className={styles.paperHeading}>原文</span><TextLines /><TextLines highlighted /><TextLines /></div><div className={styles.paperPage}><span className={styles.paperHeading}>前后文</span><TextLines /><TextLines /><TextLines /></div></div>
    </div> : null}
    {chapter === 2 ? <div className={styles.citationDesk}>
      <div className={styles.citationSheet}><span className={styles.paperHeading}>引文</span><TextLines highlighted /><TextLines /><span className={styles.citationRule} /></div>
      <div className={styles.sourceCard}><FileText size={23} strokeWidth={1.3} /><strong>{book?.title || "引用来源"}</strong><span>{book?.author}</span><div className={styles.sourceFields}><span>作者与版本</span><span>原文与页码</span><span>引用上下文</span></div></div>
    </div> : null}
    {chapter === 3 ? <div className={styles.researchDesk}>
      <div className={styles.researchFolder}><FolderOpen size={26} strokeWidth={1.2} /><span>我的研究</span><div className={styles.folderTabs}><span>原文</span><span>书单</span><span>阅读计划</span></div><TextLines /></div>
      <div className={styles.notebook}><NotebookPen size={25} strokeWidth={1.2} /><span>笔记</span><TextLines /><TextLines highlighted /></div>
    </div> : null}
  </div>;
}

function GrainField() {
  const id = useId().replace(/:/g, "");
  return <svg className={styles.grain} viewBox="0 0 1200 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs><pattern id={id} width="19" height="17" patternUnits="userSpaceOnUse" patternTransform="rotate(12)">
      <circle cx="2" cy="3" r="1.4" /><circle cx="12" cy="6" r=".9" /><circle cx="7" cy="13" r="1.1" /><circle cx="17" cy="15" r=".65" />
    </pattern></defs>
    <g fill={`url(#${id})`}>
      <path d="M-160 70C120-180 310-80 440 110S640 420 910 260 1210 230 1380 500L1300 740C1000 380 940 520 710 540S380 530 250 290 50 120-120 350Z" />
      <path opacity=".45" d="M-110 460C110 200 210 460 420 460S690 40 940 10 1160 110 1330-70L1330 160C1110 420 1000 140 840 230S650 690 380 640 160 370-110 690Z" />
    </g>
  </svg>;
}

function WorkflowDemo({ books }: { books: StoryBook[] }) {
  const ref = useRef<HTMLElement>(null);
  const [canAnimate, setCanAnimate] = useState(false);
  const [paused, setPaused] = useState(false);
  const [replay, setReplay] = useState(0);
  const book = books[0];

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let inView = false;
    const update = () => setCanAnimate(inView && !document.hidden && !preference.matches);
    const observer = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; update(); }, { threshold: .15 });
    observer.observe(node);
    preference.addEventListener("change", update);
    document.addEventListener("visibilitychange", update);
    return () => { observer.disconnect(); preference.removeEventListener("change", update); document.removeEventListener("visibilitychange", update); };
  }, []);

  return <figure ref={ref} className={styles.demo} data-playing={canAnimate && !paused} aria-label="功能演示：提出问题，查找文献，阅读原文，保存材料与笔记">
    <div className={styles.timeline} key={replay} aria-hidden="true">
      <GrainField /><div className={styles.demoFrame} />
      <div className={`${styles.demoPanel} ${styles.askPanel}`}>
        <span className={styles.demoEyebrow}><Search size={17} /> 观点检索</span>
        <div className={styles.typedQuestion}><span>技术进步会带来更大的社会公平吗？</span></div>
        <div className={styles.askTools}><span><Plus size={16} /> 选择文献</span><span className={styles.sendArrow}><ArrowRight size={20} /></span></div>
      </div>
      <div className={`${styles.demoPanel} ${styles.workingPanel}`}><span className={styles.spinner} /><span>正在寻找相关原文</span></div>
      <div className={`${styles.demoPanel} ${styles.resultsPanel}`}>
        <div className={styles.demoBar}><Search size={17} /><span>从相关文献开始</span><span>原文节选</span></div>
        <div className={styles.demoResults}>{books.length ? books.map((entry, index) => <div className={styles.resultRow} key={entry.id} data-row={index}>
          {entry.coverImage ? <img src={entry.coverImage} alt="" width={46} height={64} /> : <BookOpen size={28} />}
          <div><strong>{entry.title}</strong><span>{entry.author}</span><TextLines highlighted={index === 0} /></div><ArrowRight size={17} />
        </div>) : <div className={styles.emptyIllustration}><BookOpen size={32} /><span>查找文献与原文</span><TextLines highlighted /></div>}</div>
      </div>
      <div className={`${styles.demoPanel} ${styles.readerPanel}`}>
        <div className={styles.demoBar}><BookOpen size={17} /><span>{book?.title || "原文阅读"}</span><span>原文与出处</span></div>
        <div className={styles.readerBody}><div><strong>原文</strong><TextLines /><TextLines highlighted /><TextLines /></div><aside><FileText size={23} /><strong>回到原文</strong><span>查看前后文</span><span>核对版本与页码</span><span>复制引用</span></aside></div>
      </div>
      <div className={`${styles.demoPanel} ${styles.savedPanel}`}>
        <div className={styles.demoBar}><FolderOpen size={17} /><span>我的研究</span><Check size={17} /></div>
        <div className={styles.savedBody}><div><NotebookPen size={25} /><strong>阅读笔记</strong><TextLines highlighted /></div><div><BookOpen size={25} /><strong>参考文献</strong>{books.slice(0, 3).map(entry => <span key={entry.id}>{entry.title}</span>)}</div></div>
        <div className={styles.savedFooter}><Check size={16} /> 材料与思考，一起留下</div>
      </div>
    </div>
    <figcaption>功能演示</figcaption>
    <div className={styles.playback}><button type="button" aria-label={paused ? "播放演示" : "暂停演示"} onClick={() => setPaused(value => !value)}>{paused ? <Play size={17} /> : <Pause size={17} />}</button><button type="button" aria-label="重新播放演示" onClick={() => { setReplay(value => value + 1); setPaused(false); }}><RotateCcw size={17} /></button></div>
  </figure>;
}

export function HomeFeatureStory({ books, closingTitle, closingImage }: { books: StoryBook[]; closingTitle: string[]; closingImage: string }) {
  return <div className={styles.story}>
    <section className={styles.hero} aria-labelledby="welcome-title">
      <div className={styles.heroCopy}><h1 id="welcome-title">{closingTitle.map((line, index) => <span key={index}>{line}</span>)}</h1><p>从社会理论原典出发，寻找观点，留下自己的思考。</p><Link href="/" className={styles.primary}>进入书库 <ArrowRight size={21} aria-hidden="true" /></Link></div>
      <WorkflowDemo books={books} />
      <nav className={styles.topicTrail} aria-label="探索书库"><Link href="/scholars">学者</Link><Link href="/theories">理论流派</Link><Link href="/topics">主题</Link><Link href="/explore/original">原文</Link><Link href="/recommendations">特别策划</Link></nav>
    </section>
    <section className={styles.philosophy} aria-labelledby="welcome-philosophy"><GrainField /><div><h2 id="welcome-philosophy">回到原文，理解思想的来处。</h2><p>让观点有出处，让不同的解释相遇。<br />在阅读与追问中，形成自己的判断。</p></div></section>
    <section className={styles.features} id="library-features" aria-labelledby="welcome-features">
      <header className={styles.sectionHeading}><h2 id="welcome-features">从一个问题，<br />到一次深入阅读。</h2><p>检索、阅读、核对与整理，在同一座书库里接续。</p></header>
      {chapters.map((chapter, index) => <article className={styles.featureRow} key={chapter.href} aria-labelledby={`welcome-feature-${index}`}>
        <div className={styles.featureCopy}><h3 id={`welcome-feature-${index}`}>{chapter.title}</h3><p>{chapter.text}</p><Link href={chapter.href} className={styles.textLink}>{chapter.action} <ArrowRight size={18} aria-hidden="true" /></Link></div>
        <div className={styles.visual}><StoryScene chapter={index} books={books} /></div>
      </article>)}
      <div className={styles.discoveryGrid}>
        <article><Link href="/theories" className={styles.discoveryImage} aria-label="探索理论"><img src="/editorial/generated-20261030/theories.webp" alt="" width={1024} height={640} loading="lazy" /></Link><h3>沿着思想的脉络</h3><p>从学者、流派与主题，发现彼此相连的作品。</p><Link href="/theories" className={styles.textLink}>探索理论 <ArrowRight size={18} aria-hidden="true" /></Link></article>
        <article><Link href="/recommendations" className={styles.discoveryImage} aria-label="阅读策划"><img src="/editorial/generated-20261030/editorial.webp" alt="" width={1024} height={640} loading="lazy" /></Link><h3>换一个角度读世界</h3><p>跟随特别策划，把分散的阅读连成一个问题。</p><Link href="/recommendations" className={styles.textLink}>阅读策划 <ArrowRight size={18} aria-hidden="true" /></Link></article>
      </div>
    </section>
    <section className={styles.principles} aria-labelledby="welcome-principles"><div className={styles.sectionHeading}><h2 id="welcome-principles">理解，从有据可查开始。</h2></div><div className={styles.principleGrid}>
      <div><h3>保留出处</h3><p>辨认作者、版本与页码，回到观点出现的地方。</p></div><div><h3>读见上下文</h3><p>节选是阅读的起点，前后的论述同样重要。</p></div><div><h3>容纳不同解释</h3><p>沿着不同学者与流派，比较他们如何提出问题。</p></div><div><h3>留下自己的判断</h3><p>让笔记与材料一起保存，思考可以继续生长。</p></div>
    </div></section>
    <section className={styles.invitation} aria-labelledby="welcome-invitation"><div><h2 id="welcome-invitation">给思想一点时间。</h2><p>一本书、一段原文、一个尚未解答的问题。<br />从感兴趣的地方开始，慢慢读下去。</p><Link href="/explore" className={styles.textLink}>浏览馆藏 <ArrowRight size={18} aria-hidden="true" /></Link></div><img src={closingImage} alt="" width={1536} height={1024} loading="lazy" /></section>
    <section className={styles.faq} aria-labelledby="welcome-faq"><h2 id="welcome-faq">你可能想知道</h2><div>
      <details><summary>需要登录才能阅读吗？<Plus size={20} aria-hidden="true" /></summary><p>公开馆藏可以直接检索与阅读。登录后，可以在读者中心保存自己的阅读资料。</p></details>
      <details><summary>怎样核对一段引文？<Plus size={20} aria-hidden="true" /></summary><p>从原文节选打开对应文件，查看版本、页码与前后文；也可以在读者中心使用引文核对。</p></details>
      <details><summary>我的笔记和阅读资料保存在哪里？<Plus size={20} aria-hidden="true" /></summary><p>登录后在读者中心管理笔记、书单与阅读计划。私人资料按账户权限访问。</p></details>
    </div></section>
    <section className={styles.closing} aria-labelledby="welcome-enter"><GrainField /><h2 id="welcome-enter">下一本书，<br />下一次理解。</h2><Link href="/" className={styles.primary}>进入书库 <ArrowRight size={21} aria-hidden="true" /></Link></section>
  </div>;
}
