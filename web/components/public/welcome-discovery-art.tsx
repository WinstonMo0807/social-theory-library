import type { WelcomeDiscovery } from "@/lib/welcome";
import styles from "./welcome-discovery-art.module.css";

// Original, deliberately non-biographical illustrations. Names come only from
// the public projection; the drawings do not assert dates, quotations or links.
function ProfileDrawing() {
  return <svg viewBox="0 0 180 210" fill="none" aria-hidden="true">
    <path className={styles.portraitWash} d="M19 197V88a71 71 0 0 1 142 0v109Z" />
    <path className={styles.portraitRule} d="M10 197h160M24 188V89a66 66 0 0 1 132 0v99M36 178V91a54 54 0 0 1 108 0v87" />
    <g stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M43 190c2-26 10-37 34-44l3-19m27-4 2 22c22 7 31 19 34 45" />
      <path d="M71 86c-10-9-8-24 2-32 15-13 39-6 44 11 3 9 1 18 2 25l9 15-11 5c0 13-6 23-18 25-9 1-18-5-22-12" />
      <path d="M71 87c-7-7-12-4-11 5 0 8 6 13 12 11l5 20M66 78c12 0 17-9 21-17 6 11 19 15 31 16M109 89l7 1m-7 2h1m6 25-11-1" />
      <path d="m77 145 15 14 17-14M77 145l-9 13 17 18 7-17 12 17 15-18-10-13M92 159v31M55 175l-3 15m76-18 6 18" />
      <path opacity=".35" d="m69 66 8-7m-10 15 14-13m-8 17 11-11m-5 66 11 9m-12-15 15 11M61 163l-7 18m12-22-8 27m54-33 13 23m-10-20 13 25" />
    </g>
    <path className={styles.portraitRule} d="M16 32h22M27 21v22M144 168h21M155 158v21" />
  </svg>;
}

function TopicDrawing({ variant }: { variant: number }) {
  return <svg viewBox="0 0 100 64" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
    {variant === 0 ? <><path d="M6 56h88M12 56V24l17-11 17 11v32M27 56V37h9v19M54 56V8h28v48M60 17h5m7 0h4m-16 9h5m7 0h4m-16 9h5m7 0h4M6 24l23-17 23 17" /><circle cx="85" cy="12" r="5" /></> : null}
    {variant === 1 ? <><path d="M15 30 40 13l42 15-21 23-46-21m25-17 21 38m-46-21 67-2" />{[[15,30],[40,13],[82,28],[61,51]].map(([x,y]) => <circle key={x} cx={x} cy={y} r="6" fill="var(--story-sheet)" />)}<circle cx="49" cy="31" r="11" /></> : null}
    {variant === 2 ? <>{[0,1,2,3,4].map(i => <path key={i} d={`M${9+i*17} 5c-18 17 26 32 0 54M5 ${9+i*11}c27-16 50 18 87 0`} />)}</> : null}
  </svg>;
}

export function ScholarDiscoveryArt({ discovery }: { discovery: WelcomeDiscovery }) {
  const person = discovery.scholars[0];
  return <div className={styles.scholarArt}>
    <div className={styles.archiveCard}>
      <div className={styles.archiveTab}>学者</div>
      <div className={styles.portrait}><ProfileDrawing /></div>
      <strong>{person?.name || "思想的来处"}</strong>
      <span>{person?.originalName && person.originalName !== person.name ? person.originalName : "生平与著述"}</span>
    </div>
    <div className={styles.archiveContent}>
      <div className={styles.lifeTrail}><span>生平</span><i /><span>著述</span><i /><span>论争</span></div>
      <div className={styles.manuscript}>
        <span className={styles.marginNote}>研究问题</span>
        <strong>所处的时代，<br />提出的问题。</strong>
        <div className={styles.indexSlips}><span>思想背景</span><span>代表作品</span><span>学术对话</span></div>
      </div>
      <div className={styles.archiveReferences}>
        <div className={styles.miniVolumes} aria-hidden="true"><i /><i /><i /></div>
        <span>{discovery.scholars.length > 1 ? discovery.scholars.slice(1, 3).map(entry => entry.name).join("、") : "由学者走进作品"}</span>
        <span aria-hidden="true">↗</span>
      </div>
    </div>
  </div>;
}

export function TheoryDiscoveryArt({ discovery }: { discovery: WelcomeDiscovery }) {
  return <div className={styles.theoryArt}>
    <div className={styles.theoryQuestion}><span>同一个问题</span><strong>如何理解社会？</strong></div>
    <div className={styles.theoryBranches} aria-hidden="true"><i /><i /><i /></div>
    <div className={styles.theoryCards}>
      {(["行动", "制度", "文化"] as const).map((lens, index) => <div className={styles.theoryCard} key={lens}>
        <div className={styles.lensDrawing} data-lens={index}><i /><i /><i /><b /></div>
        <strong>{discovery.theories[index]?.name || lens}</strong>
        <span>{["从概念出发", "阅读代表论著", "比较不同解释"][index]}</span>
      </div>)}
    </div>
    <div className={styles.theoryFoot}><span>概念</span><i /><span>原典</span><i /><span>论争</span></div>
  </div>;
}

export function EditorialDiscoveryArt({ discovery }: { discovery: WelcomeDiscovery }) {
  const topics = discovery.topics.length ? discovery.topics.slice(0, 3).map(topic => topic.name) : ["日常生活", "社会关系", "文化与认同"];
  return <div className={styles.editorialArt}>
    <div className={styles.topicShelf}>
      <span className={styles.sectionLabel}>主题</span>
      {topics.map((topic, index) => <div className={styles.topicCard} key={topic}><TopicDrawing variant={index} /><strong>{topic}</strong><span aria-hidden="true">↗</span></div>)}
    </div>
    <div className={styles.issueDesk}>
      <span className={styles.sectionLabel}>特别策划</span>
      <div className={styles.issueSpread}>
        <div className={styles.issueCover}><span>专题阅读</span><strong>{discovery.issue?.title || <>把阅读<br />连成问题</>}</strong><div className={styles.issueComposition} aria-hidden="true"><i /><i /><i /><b /></div></div>
        <div className={styles.issueContents}><strong>从问题出发</strong><div><span>提出问题</span><i /></div><div><span>并置阅读</span><i /></div><div><span>回到原文</span><i /></div><span className={styles.issueArrow} aria-hidden="true">↗</span></div>
      </div>
    </div>
  </div>;
}
