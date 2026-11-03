"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, ArrowUp, ArrowUpRight, BookOpen, Bookmark, Check, ChevronDown, Copy, Download, FileText, Info, MapPin, Plus, SlidersHorizontal, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { submitSearchOnEnter } from "@/lib/search-submit-key";
import { policies, exampleQuestions, policyCitation, type Policy } from "@/lib/policy-demo/data";
import { emptyFilters, type Filters, type Hit, type SearchResult } from "@/lib/policy-demo/search";
import styles from "./policy.module.css";

type View = "discover" | "research" | "coverage";
const researchAngles = [
  { title: "劳动与社会保障", text: "从劳动关系、收入分配到平台责任", query: exampleQuestions[0] },
  { title: "算法与数字治理", text: "理解算法规则中的权利与边界", query: exampleQuestions[2] },
  { title: "中央与地方", text: "把相近议题放回不同的制度情境", query: exampleQuestions[1] },
];

export function PolicyWorkspace({ libraryUrl = "" }: { libraryUrl?: string }) {
  const [view, setView] = useState<View>("discover");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [history, setHistory] = useState<SearchResult[]>([]);
  const [saved, setSaved] = useState<Hit[]>([]);
  const [selected, setSelected] = useState<{ policy: Policy; locator?: string } | null>(null);
  const [notice, setNotice] = useState("");
  const [mode, setMode] = useState<"evidence" | "compare">("evidence");
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(""), 4500); return () => clearTimeout(timer); }, [notice]);

  async function search(value: string, nextFilters = filters, newTopic = false) {
    if (value.trim().length < 2 || busy) return;
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    setBusy(true); setError(""); setQuery(value.trim()); setView("research");
    try {
      const response = await fetch("/policy/query", { method: "POST", headers: { "content-type": "application/json" }, signal: request.signal, body: JSON.stringify({ query: value.trim(), previous: newTopic ? "" : result?.context || "", filters: nextFilters }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "检索暂时不可用，请重试。");
      if (request.signal.aborted) return;
      const next = payload as SearchResult;
      setResult(next); setHistory(items => [...items, next].slice(-12)); setFilters(next.filters); setQuery("");
      requestAnimationFrame(() => resultHeading.current?.focus());
    } catch (reason) {
      if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "无法连接检索服务，请重试。");
    } finally { if (controller.current === request) setBusy(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void search(query); }
  function newResearch() { controller.current?.abort(); setBusy(false); setView("discover"); setResult(null); setHistory([]); setQuery(""); setFilters(emptyFilters); setError(""); }
  function toggleSave(hit: Hit) { setSaved(items => items.some(row => row.passage.id === hit.passage.id) ? items.filter(row => row.passage.id !== hit.passage.id) : [...items, hit]); }
  async function copy(text: string) {
    try { await navigator.clipboard.writeText(text); setNotice("引用已复制，请按投稿要求核对格式。"); }
    catch { setNotice("浏览器未允许复制，请在原文侧窗中选择引用文字手动复制。"); }
  }
  function exportSources() {
    if (!saved.length) return;
    const content = `政策研究材料\n仅含本次选取的公开政策节选。政策规定不能单独证明执行效果。\n\n${saved.map((hit, index) => `${index + 1}. ${policyCitation(hit.policy, hit.passage.locator)}\n\n${hit.passage.text}`).join("\n\n")}`;
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "STL-政策研究材料.txt"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice("已导出选中材料与官方出处。");
  }
  const documentCount = new Set(result?.hits.map(hit => hit.policy.id)).size;
  const activeScope = [filters.region, filters.kind, filters.from || filters.to ? `${filters.from || "不限"} 至 ${filters.to || "不限"}` : "不限年份"].join(" / ");

  function composer(compact = false) {
    return <form className={`${styles.composer} ${compact ? styles.compactComposer : ""}`} onSubmit={submit}>
      <label className={styles.visuallyHidden} htmlFor={compact ? "policy-followup" : "policy-question"}>{compact ? "继续追问政策" : "输入政策研究问题"}</label>
      <textarea ref={input} id={compact ? "policy-followup" : "policy-question"} value={query} maxLength={500} rows={compact ? 2 : 3} onChange={event => setQuery(event.target.value)} onKeyDown={submitSearchOnEnter} placeholder={compact ? "继续追问，也可以限定地区、比较条款……" : "描述你的研究问题，或输入政策名称、文号……"} />
      <div className={styles.composerBottom}><button type="button" className={styles.filterTrigger} aria-expanded={advanced} onClick={() => setAdvanced(value => !value)}><SlidersHorizontal size={16} /><span>{filters.region === "全部地区" ? "检索范围" : filters.region}</span><ChevronDown size={14} /></button><span className={styles.composerHint}>Enter 提问 · Shift + Enter 换行</span><button type="submit" className={styles.submit} disabled={busy || query.trim().length < 2} aria-label={compact ? "发送追问" : "开始政策检索"}>{busy ? <span className={styles.spinner} /> : <ArrowUp size={21} />}</button></div>
      {advanced ? <div className={styles.filters}><label>地区<select value={filters.region} onChange={event => setFilters({ ...filters, region: event.target.value })}>{["全部地区", "全国", "上海", "浙江", "绍兴"].map(value => <option key={value}>{value}</option>)}</select></label><label>文件类型<select value={filters.kind} onChange={event => setFilters({ ...filters, kind: event.target.value })}>{["全部类型", "法律", "部门规章", "行政规范性文件"].map(value => <option key={value}>{value}</option>)}</select></label><label>成文起始<input type="date" value={filters.from} onChange={event => setFilters({ ...filters, from: event.target.value })} /></label><label>成文截止<input type="date" value={filters.to} onChange={event => setFilters({ ...filters, to: event.target.value })} /></label><p>筛选在下次提问时生效；地区指文件制定或适用地域，不是转载网站所在地。</p></div> : null}
    </form>;
  }

  return <div className={styles.page} data-type-mode="productive">
    <div className={styles.subnav}><button className={styles.productName} onClick={newResearch}>政策库<span>研究预览</span></button><nav aria-label="政策库导航">{([["discover", "政策发现"], ["research", "研究工作台"], ["coverage", "收录范围"]] as const).map(([key, label]) => <button key={key} aria-current={view === key ? "page" : undefined} onClick={() => setView(key)}>{label}</button>)}</nav><a className={styles.backToLibrary} href={`${libraryUrl}/explore/opinions`}>回到观点检索<ArrowUpRight size={15} /></a></div>

    {view === "discover" ? <>
      <section className={styles.hero}>
        <div className={styles.heroCopy}><h1>读懂政策，<br />追问制度。</h1><p>从一个研究问题出发，找到政策原文、<br className={styles.desktopBreak} />地方差异与可以核对的引用。</p><div className={styles.heroSource}><span className={styles.sourceDot} />公开来源 · 原文可追溯</div></div>
        <div className={styles.questionArea}>{composer()}<div className={styles.sampleNote}><Info size={14} /><span>研究预览收录 {policies.length} 份真实文件的节选，体验提问、比较与引用。</span><button onClick={() => setView("coverage")}>查看范围</button></div><div className={styles.suggestions}><p>也可以从这里开始</p>{exampleQuestions.map(question => <button key={question} disabled={busy} onClick={() => void search(question, emptyFilters, true)}><span>{question}</span><ArrowUpRight size={17} /></button>)}</div></div>
      </section>
      <section className={styles.angles}><div className={styles.sectionHeading}><h2>让政策进入你的研究</h2><p>同一份文件，可以回应不同的问题。</p></div><div className={styles.angleGrid}>{researchAngles.map(angle => <button key={angle.title} onClick={() => void search(angle.query, emptyFilters, true)}><span className={styles.angleTitle}>{angle.title}<ArrowUpRight size={20} /></span><span>{angle.text}</span></button>)}</div></section>
      <section className={styles.browse}><div className={styles.sectionHeading}><h2>从中央规定，读到地方实践</h2><button onClick={() => setView("coverage")}>浏览样本<ArrowRight size={16} /></button></div><div className={styles.policyList}>{policies.slice(0, 3).map(policy => <button key={policy.id} onClick={() => setSelected({ policy })}><span className={styles.level}>{policy.level}</span><div><strong>{policy.title}</strong><span>{policy.issuer} · {policy.number}</span></div><time>{policy.date}</time><ArrowUpRight size={18} /></button>)}</div></section>
    </> : view === "coverage" ? <section className={styles.coverage}><div className={styles.sectionHeading}><div><h1>每一份材料，都有来处。</h1><p>当前为 {policies.length} 份文件、{policies.reduce((sum, policy) => sum + policy.passages.length, 0)} 处原文节选。核对日期：2026年11月3日。</p></div><button onClick={newResearch}>开始研究<ArrowUpRight size={17} /></button></div><div className={styles.coverageNote}><Info size={19} /><p>这是用于体验的有限样本，不代表全国或某一地区的完整覆盖。原文链接、成文日期、文件类型与出处均独立展示；现行效力与历史修订尚未建立持续核验。</p></div><div className={styles.coverageTable}>{policies.map(policy => <button key={policy.id} onClick={() => setSelected({ policy })}><span>{policy.level}<small>{policy.region}</small></span><span><strong>{policy.title}</strong><small>{policy.sourceLabel}</small></span><span>{policy.kind}<small>{policy.date}</small></span><ArrowUpRight size={17} /></button>)}</div></section> : <section className={styles.research}>
      <aside className={styles.researchNav}><button className={styles.newResearch} onClick={newResearch}><Plus size={17} />新的研究问题</button><h2>本次研究</h2>{history.length ? <ol>{history.map((item, index) => <li key={`${index}:${item.query}`}><button aria-current={result === item ? "step" : undefined} onClick={() => { if (busy) return; setResult(item); setFilters(item.filters); }}><span>{index + 1}</span>{item.query}</button></li>)}</ol> : <p>从一个问题开始，<br />在原文之间继续追问。</p>}<div className={styles.scopeSummary}><MapPin size={16} /><span>当前检索范围<br /><strong>{activeScope}</strong></span></div><button className={styles.coverageLink} onClick={() => setView("coverage")}>了解样本覆盖<ArrowUpRight size={14} /></button></aside>
      <div className={styles.conversation}>
        {result ? <>
          <div className={styles.resultMeta}><span>政策研究</span><span>{documentCount} 份文件 · {result.hits.length} 处节选</span></div><h1 ref={resultHeading} tabIndex={-1} className={styles.questionTitle}>{result.query}</h1>
          {result.context !== result.query ? <p className={styles.contextNote}>承接上轮问题继续检索，保留当前范围。</p> : null}
          <div className={styles.answerIntro}><BookOpen size={20} /><div><strong>{/效果|有效吗|证明|因果/.test(result.query) ? "这些文件提供制度依据，尚不能证明实际效果。" : result.hits.length ? "先从这些政策原文进入问题。" : "当前样本中没有找到足够相关的原文。"}</strong><p>{result.hits.length ? "下面保留文件的原始表述与适用范围。研究视角由样本编者整理，不能替代政策正文或法律适用判断。" : "可以调整关键词或筛选条件，也可以查看本 Demo 的收录范围。没有命中不代表现实中不存在相关政策。"}</p></div></div>
          <div className={styles.resultTabs}><div><button aria-pressed={mode === "evidence"} onClick={() => setMode("evidence")}>原文证据</button><button aria-pressed={mode === "compare"} onClick={() => setMode("compare")}>地区比较</button></div><span>{result.engine === "semantic" ? "语义重排" : "关键词检索"}</span></div>
          {mode === "evidence" ? <div className={styles.evidenceList}>{result.hits.map((hit, index) => <article key={hit.passage.id} className={styles.evidence}><div className={styles.evidenceMeta}><span className={styles.referenceNumber}>{index + 1}</span><span>{hit.policy.region}</span><span>{hit.policy.kind}</span><time>{hit.policy.date}</time></div><button className={styles.evidenceTitle} onClick={() => setSelected({ policy: hit.policy, locator: hit.passage.locator })}>{hit.policy.title}<ArrowUpRight size={17} /></button><p className={styles.locator}>{hit.passage.locator}</p><blockquote>{hit.passage.text}</blockquote><div className={styles.lens}><span>研究视角</span>{hit.passage.lens}</div><div className={styles.evidenceActions}><button onClick={() => setSelected({ policy: hit.policy, locator: hit.passage.locator })}><FileText size={15} />核对来源</button><button onClick={() => void copy(policyCitation(hit.policy, hit.passage.locator))}><Copy size={15} />引用</button><button aria-pressed={saved.some(row => row.passage.id === hit.passage.id)} onClick={() => toggleSave(hit)}>{saved.some(row => row.passage.id === hit.passage.id) ? <Check size={15} /> : <Plus size={15} />}{saved.some(row => row.passage.id === hit.passage.id) ? "已选入材料" : "选入材料"}</button></div></article>)}</div> : <div className={styles.comparison}><p>按文件所属地域并列原文；本页只呈现样本，不据此推断地方之间的政策优劣。</p>{[...new Set(result.hits.map(hit => hit.policy.region))].map(region => <section key={region}><h2><MapPin size={17} />{region}</h2>{result.hits.filter(hit => hit.policy.region === region).slice(0, 2).map(hit => <button key={hit.passage.id} onClick={() => setSelected({ policy: hit.policy, locator: hit.passage.locator })}><strong>{hit.passage.lens}</strong><p>{hit.passage.text}</p><small>{hit.policy.number} · {hit.passage.locator}<ArrowUpRight size={14} /></small></button>)}</section>)}</div>}
          <p className={styles.engineNote}><Info size={14} />{result.notice}</p>
          {result.hits.length ? <div className={styles.followups}><p>沿着这个问题继续</p>{["只看上海的规定", "比较中央和地方的政策责任", "这些能证明政策已经产生效果吗？"].map(question => <button key={question} disabled={busy} onClick={() => void search(question)}>{question}<ArrowUpRight size={15} /></button>)}</div> : null}
        </> : <div className={styles.researchEmpty}><BookOpen size={34} /><h1>把问题放在前面。</h1><p>输入你的研究问题，或选择一个示例开始。<br />检索范围限于当前 {policies.length} 份真实政策样本。</p>{exampleQuestions.map(question => <button key={question} disabled={busy} onClick={() => void search(question, emptyFilters, true)}>{question}<ArrowUpRight size={16} /></button>)}</div>}
        {busy ? <div role="status" className={styles.loading}><span className={styles.spinner} /><span>正在检索政策原文并核对排序…</span><button onClick={() => { controller.current?.abort(); setBusy(false); }}>取消</button></div> : null}{error ? <p className={styles.error} role="alert">{error}<button onClick={() => void search(query || result?.query || exampleQuestions[0])}>重试</button></p> : null}
        <div className={styles.followupComposer}>{composer(true)}<p>本页为政策节选检索演示，尚未接入自由生成式回答。</p></div>
      </div>
      <aside className={styles.materials}><header><h2><Bookmark size={17} />研究材料</h2><span>{saved.length}</span></header>{saved.length ? <><div className={styles.savedList}>{saved.map(hit => <div key={hit.passage.id}><button className={styles.savedTitle} onClick={() => setSelected({ policy: hit.policy, locator: hit.passage.locator })}>{hit.policy.title}<small>{hit.passage.locator}</small></button><button className={styles.removeSaved} aria-label={`移除${hit.passage.locator}`} onClick={() => toggleSave(hit)}><X size={14} /></button></div>)}</div><button className={styles.export} onClick={exportSources}><Download size={16} />导出材料与引用</button></> : <div className={styles.materialsEmpty}><FileText size={28} /><p>把有用的条款留在这里。</p><span>点击原文下方的「选入材料」，<br />将依据与出处一起带走。</span></div>}<p className={styles.materialsNote}>仅在当前页面暂存，刷新后清空。</p><div className={styles.researchReminder}><h3>从政策到论证</h3><p>政策规定说明了制度如何设计。执行程度、受益分布与实际效果，还需要经验材料。</p><a href={`${libraryUrl}/explore/opinions`}>到书库寻找理论原文<ArrowUpRight size={14} /></a></div></aside>
    </section>}

    <footer className={styles.footer}><span>社会理论书库 · 政策研究</span><span>公开原文，审慎引用。</span><button onClick={() => setView("coverage")}>关于本次预览<ArrowUpRight size={14} /></button></footer>
    {notice ? <div className={styles.toast} role="status"><Check size={16} />{notice}</div> : null}
    <Dialog open={!!selected} onRequestClose={() => setSelected(null)} className={styles.sourceDrawer} aria-labelledby="policy-source-title"><header><span><FileText size={17} />原文与出处</span><button aria-label="关闭原文" onClick={() => setSelected(null)}><X size={21} /></button></header>{selected ? <div className={styles.sourceBody}><div className={styles.sourceBadges}><span>{selected.policy.level} · {selected.policy.region}</span><span>{selected.policy.kind}</span></div><h2 id="policy-source-title">{selected.policy.title}</h2><dl><div><dt>发布机关</dt><dd>{selected.policy.issuer}</dd></div><div><dt>发文字号</dt><dd>{selected.policy.number}</dd></div><div><dt>成文日期</dt><dd>{selected.policy.date}</dd></div>{selected.policy.effective ? <div><dt>文本载明施行日</dt><dd>{selected.policy.effective}</dd></div> : null}{selected.policy.expires ? <div><dt>文本载明有效期至</dt><dd>{selected.policy.expires}</dd></div> : null}<div><dt>原文来源</dt><dd>{selected.policy.sourceLabel}</dd></div></dl><a className={styles.officialLink} href={selected.policy.source} target="_blank" rel="noreferrer">打开官方完整原文<ArrowUpRight size={17} /></a><p className={styles.sourceNote}>{selected.policy.note}</p><h3>已收录的原文节选</h3>{selected.policy.passages.map(passage => <section className={styles.sourcePassage} data-selected={passage.locator === selected.locator || undefined} key={passage.id}><h4>{passage.locator}</h4><p>{passage.text}</p></section>)}<section className={styles.citationBlock}><h3>引用信息</h3><p>{policyCitation(selected.policy, selected.locator)}</p><button onClick={() => void copy(policyCitation(selected.policy, selected.locator))}><Copy size={15} />复制引用</button><small>这是带来源的引用草稿，尚未按具体期刊格式排版。</small></section></div> : null}</Dialog>
  </div>;
}
