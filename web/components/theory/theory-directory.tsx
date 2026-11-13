"use client";

import { LoadingState } from "@/components/ui/loading-state";
import { MediaPlacement } from "@/components/media-placement";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSyncExternalStore, useTransition } from "react";
import {
  ArrowLeft, ArrowRight, BookOpen, ChevronDown, ChevronRight, Clock3,
  FileQuestion, List, Network, Search, TriangleAlert, UserRound, X,
} from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import {
  theoryDirectoryHref, theoryDirectoryKinds, theoryDirectoryLabels,
  type TheoryDirectoryFailure, type TheoryDirectoryFilters, type TheoryDirectoryResponse,
  type TheoryDirectorySelectionState,
} from "@/lib/api/theory-directory.types";
import styles from "./theory-directory.module.css";

const mobileQuery = "(max-width: 800px)";
function subscribeMobile(callback: () => void) {
  const query = window.matchMedia(mobileQuery);
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}
const mobileSnapshot = () => window.matchMedia(mobileQuery).matches;
const serverSnapshot = () => false;

function SelectedEntry({ selection, filters, parentName, backHref, onRetry, pending }: {
  selection: TheoryDirectorySelectionState; filters: TheoryDirectoryFilters;
  parentName: string; backHref: string; onRetry: () => void; pending: boolean;
}) {
  if (selection.status === "none") return <div className={styles.chooseEntry}>
    <BookOpen size={28} strokeWidth={1.3} aria-hidden="true" />
    <h2>选择一个条目</h2><p>从目录中选择理论、研究领域或概念，查看简介、关联学者与原文。</p>
  </div>;
  if (selection.status === "unavailable") return <div className={styles.selectionState} role="status">
    <FileQuestion size={30} strokeWidth={1.3} aria-hidden="true" />
    <h2>来源未发布或已不可用</h2><p>该条目当前不可公开读取。你可以继续浏览已有内容。</p>
    <Link className={styles.secondary} href={theoryDirectoryHref(filters, { selected: "" })} scroll={false}>显示已有内容</Link>
  </div>;
  if (selection.status === "error") return <div className={styles.selectionState} role="alert">
    <TriangleAlert size={28} strokeWidth={1.3} aria-hidden="true" />
    <h2>条目暂时无法加载</h2><p>目录仍可浏览。请稍后重试，核对当前条目。</p>
    <button className={styles.secondary} type="button" onClick={onRetry} disabled={pending}>重新加载条目</button>
  </div>;
  const entry = selection.data;
  return <div className={styles.entry}>
    <Link className={styles.back} href={backHref} scroll={false}><ArrowLeft size={17} />返回上级</Link>
    <h2>{entry.name}</h2>
    <p className={styles.entryKind}>{parentName || theoryDirectoryLabels[entry.kind]}</p>
    {entry.foreign_name ? <p className={styles.foreignName}>{entry.foreign_name}</p> : null}
    {entry.summary ? <p className={styles.summary}>{entry.summary}</p> : null}
    {entry.period_label ? <p className={styles.period}>{entry.period_label}</p> : null}
    <section className={styles.scholars} aria-label="相关学者">
      <h3>相关学者</h3>
      {entry.scholars.length ? entry.scholars.map(scholar => <Link href={scholar.href} key={scholar.id}>
        {scholar.portrait_url ? <MediaPlacement uses={scholar.portrait_media?.display_uses} fallback={<span className={styles.portraitEmpty} aria-hidden="true"><UserRound size={23} /></span>}><img src={scholar.portrait_url} alt="" loading="lazy" /></MediaPlacement> : <span className={styles.portraitEmpty} aria-hidden="true"><UserRound size={23} /></span>}
        <span><strong>{scholar.name}</strong>{scholar.original_name ? <small>{scholar.original_name}</small> : null}</span><ChevronRight size={17} />
      </Link>) : <p className={styles.missing}>尚无已确认并公开的学者关联。</p>}
    </section>
    <section className={styles.concepts} aria-label="关联概念">
      <h3>关联概念</h3>
      {entry.concepts.length ? <div>{entry.concepts.map(concept => <Link href={concept.href} key={concept.id}>{concept.name}</Link>)}</div> : <p className={styles.missing}>尚无已确认并公开的概念关联。</p>}
    </section>
    {!entry.source_href ? <p className={styles.sourceNotice}>当前没有可公开定位的原文，条目资料仍可阅读。</p> : null}
    <div className={styles.entryActions}>
      <Link className={styles.primary} href={entry.href}>查看{entry.kind === "subdiscipline" ? "领域" : "条目"}详情<ArrowRight size={17} /></Link>
      {entry.source_href
        ? <Link className={styles.secondary} href={entry.source_href} target="_blank" rel="noopener noreferrer" title={entry.source_title}>{entry.source_kind === "evidence" ? "查看原文依据" : "查看馆藏原文"}<ArrowRight size={17} /></Link>
        : <span className={styles.disabledAction}><BookOpen size={15} />原文暂未提供</span>}
    </div>
  </div>;
}

export function TheoryDirectory({
  directory, failure, filters, selection,
}: {
  directory: TheoryDirectoryResponse | null; failure: TheoryDirectoryFailure;
  filters: TheoryDirectoryFilters; selection: TheoryDirectorySelectionState;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const mobile = useSyncExternalStore(subscribeMobile, mobileSnapshot, serverSnapshot);
  const retry = () => startTransition(() => router.refresh());
  const clearSelectionHref = theoryDirectoryHref(filters, { selected: "" });
  const parentIndex = directory?.breadcrumbs.findIndex(item => item.id === directory.parent?.id) ?? -1;
  const ancestor = parentIndex > 0 ? directory?.breadcrumbs[parentIndex - 1] : null;
  const backHref = directory?.parent
    ? theoryDirectoryHref(filters, { parent: ancestor?.id || "", selected: "", page: 1 })
    : clearSelectionHref;
  const selectedGroup = directory?.groups.find(group => group.items.some(item => item.slug === filters.selected));
  const detailProps = { selection, filters, parentName: selectedGroup?.parent?.name || "", backHref, onRetry: retry, pending };
  const closeDrawer = () => {
    startTransition(() => router.replace(clearSelectionHref, { scroll: false }));
  };
  const selectedDiscipline = directory?.disciplines.find(item => item.slug === filters.discipline);
  const viewQuery = new URLSearchParams();
  if (filters.discipline) viewQuery.set("discipline", filters.discipline);
  if (filters.q) viewQuery.set("q", filters.q);
  const viewSuffix = viewQuery.size ? `?${viewQuery}` : "";
  const graphQuery = new URLSearchParams();
  if (filters.discipline) graphQuery.set("discipline", filters.discipline);
  if (selection.status === "available" && selection.data.kind !== "subdiscipline") graphQuery.set("center", selection.data.slug);
  const graphSuffix = graphQuery.size ? `?${graphQuery}` : "";
  const searchLabel = filters.type === "subdiscipline" ? "搜索子学科、理论或主题" : "搜索理论、概念或学者";

  return <article className={styles.page} aria-busy={pending}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/theories">理论流派</Link><ChevronRight size={14} /><span>理论目录</span></nav>
    <header className={styles.header}><h1>理论目录</h1></header>
    <form className={styles.search} action="/theories/directory" role="search" aria-label="搜索理论目录">
      <input type="hidden" name="type" value={filters.type} />
      {filters.discipline ? <input type="hidden" name="discipline" value={filters.discipline} /> : null}
      {filters.parent ? <input type="hidden" name="parent" value={filters.parent} /> : null}
      <Search size={22} strokeWidth={1.6} aria-hidden="true" />
      <input type="search" name="q" key={filters.q} defaultValue={filters.q} placeholder={`${searchLabel}…`} aria-label={searchLabel} maxLength={240} />
      <button type="submit" className={styles.primary}>搜索</button>
    </form>
    <nav className={styles.views} aria-label="理论浏览方式">
      <Link href={theoryDirectoryHref(filters)} aria-current="page"><List size={19} />目录</Link>
      <Link href={`/theories/timeline${viewSuffix}`}><Clock3 size={19} />时间线</Link>
      <Link href={`/theories/graph${graphSuffix}`}><Network size={19} />关系图</Link>
    </nav>
    <div className={styles.columns}>
      <aside className={styles.disciplines} aria-label="学科与条目类型">
        <section data-content-section className={styles.discipline}>
          <header data-section-heading>全部学科<ChevronDown size={16} /></header>
          <nav aria-label="全部学科的条目类型">{theoryDirectoryKinds.map(kind => <Link
            key={kind} aria-current={!filters.discipline && filters.type === kind ? "page" : undefined}
            href={theoryDirectoryHref(filters, { discipline: "", type: kind, parent: "", page: 1, selected: "" })} scroll={false}
          >{theoryDirectoryLabels[kind]}</Link>)}</nav>
        </section>
        {directory?.disciplines.map(discipline => <section data-content-section className={styles.discipline} key={discipline.id}>
          <header data-section-heading>{discipline.name}<ChevronDown size={16} /></header>
          <nav aria-label={`${discipline.name}的条目类型`}>{theoryDirectoryKinds.map(kind => <Link
            key={kind} aria-current={filters.discipline === discipline.slug && filters.type === kind ? "page" : undefined}
            href={theoryDirectoryHref(filters, { discipline: discipline.slug, type: kind, parent: "", page: 1, selected: "" })} scroll={false}
          >{theoryDirectoryLabels[kind]}</Link>)}</nav>
        </section>)}
        {!directory ? <p className={styles.missing}>学科目录待重新加载。</p> : null}
      </aside>

      <section className={styles.results} aria-labelledby="directory-results-heading">
        <div className={styles.resultHeader}>
          <h2 id="directory-results-heading">{filters.q ? "搜索结果" : directory?.parent?.name || `${selectedDiscipline?.name || "全部学科"} · ${theoryDirectoryLabels[filters.type]}`}</h2>
          {directory ? <p>共 {directory.count} 个公开条目{filters.q ? `，关键词“${filters.q}”` : ""}。{directory.parent ? "此处列出直属条目。" : "按已确认层级展示本页条目。"}{filters.q ? "展开直属条目时清除关键词。" : ""}</p> : null}
        </div>
        {directory?.parent ? <nav className={styles.path} aria-label="当前目录层级">
          <Link href={theoryDirectoryHref(filters, { parent: "", page: 1, selected: "" })} scroll={false}>全部条目</Link>
          {directory.breadcrumbs.map(item => <span key={item.id}><ChevronRight size={12} /><Link href={theoryDirectoryHref(filters, { parent: item.id, page: 1, selected: "" })} aria-current={item.id === directory.parent?.id ? "location" : undefined} scroll={false}>{item.name}</Link></span>)}
        </nav> : null}
        {directory?.hierarchy_truncated ? <p className={styles.sourceNotice}>部分上级层级暂未完整展示，可返回全部条目继续查找。</p> : null}
        {failure ? <div className={styles.resultState} role="alert">
          <TriangleAlert size={31} strokeWidth={1.3} aria-hidden="true" />
          <h3>{failure === "unavailable" ? "目录来源当前不可用" : failure === "invalid" ? "目录条件无法识别" : "目录暂时无法加载"}</h3>
          <p>{failure === "unavailable" ? "所选学科、上级条目或页码当前不可用。可以返回现有公开目录。" : failure === "invalid" ? "请清除筛选，再从公开目录重新选择。" : "请稍后重试。"}</p>
          <div><button type="button" onClick={retry} disabled={pending} className={styles.secondary}>重新加载</button><Link className={styles.secondary} href="/theories/directory">显示已有内容</Link></div>
        </div> : directory?.count === 0 ? <div className={styles.resultState} role="status">
          <FileQuestion size={34} strokeWidth={1.3} aria-hidden="true" /><h3>没有匹配结果</h3>
          <p>{directory.parent && !filters.q ? "当前上级条目下没有已公开的直属条目。" : "请尝试调整关键词或移除筛选条件。"}</p>
          <Link className={styles.secondary} href={theoryDirectoryHref(filters, { q: "", discipline: "", parent: "", page: 1, selected: "" })}>清除筛选</Link>
        </div> : directory ? <>
          {directory.groups.map(group => <section data-content-section className={styles.group} key={group.id || "ungrouped"}>
            <header data-section-heading><span>{group.title}</span><ChevronDown size={17} /></header>
            {group.parent && !directory.parent ? <Link className={styles.groupChildren} href={theoryDirectoryHref(filters, { parent: group.parent.id, q: "", page: 1, selected: "" })} scroll={false}>浏览直属条目<ArrowRight size={12} /></Link> : null}
            <ul>{group.items.map(item => <li key={item.id} data-selected={filters.selected === item.slug || undefined}>
              <Link className={styles.item} href={theoryDirectoryHref(filters, { selected: item.slug })} scroll={false} aria-current={filters.selected === item.slug ? "true" : undefined}>
                <span>{item.name}</span><ChevronRight size={17} />
              </Link>
              {item.child_count > 0 ? <Link className={styles.children} href={theoryDirectoryHref(filters, { parent: item.id, q: "", page: 1, selected: "" })} scroll={false} aria-label={`展开${item.name}的${item.child_count}个直属条目`}>{item.child_count}<List size={13} /></Link> : null}
            </li>)}</ul>
          </section>)}
          {directory.total_pages > 1 ? <nav className={styles.pagination} aria-label="目录分页">
            {directory.page > 1 ? <Link href={theoryDirectoryHref(filters, { page: directory.page - 1, selected: "" })} scroll={false}><ArrowLeft size={14} />上一页</Link> : <span />}
            <span>第 {directory.page} / {directory.total_pages} 页</span>
            {directory.page < directory.total_pages ? <Link href={theoryDirectoryHref(filters, { page: directory.page + 1, selected: "" })} scroll={false}>下一页<ArrowRight size={14} /></Link> : <span />}
          </nav> : null}
        </> : null}
      </section>
      {!mobile ? <aside className={styles.detailPanel} aria-label="所选条目详情"><SelectedEntry {...detailProps} /></aside> : null}
    </div>
    {pending ? <LoadingState className={styles.loading} role="status">正在读取当前资料…</LoadingState> : null}
    {mobile ? <Dialog open={selection.status !== "none"} onRequestClose={closeDrawer} className={styles.drawer} aria-label="所选条目详情">
      <div className={styles.drawerHandle} aria-hidden="true" />
      <button className={styles.closeDrawer} type="button" onClick={closeDrawer} aria-label="关闭条目详情" disabled={pending}><X size={20} /></button>
      {pending ? <LoadingState className={styles.loading} role="status">正在读取当前资料…</LoadingState> : null}
      <SelectedEntry {...detailProps} />
    </Dialog> : null}
  </article>;
}
