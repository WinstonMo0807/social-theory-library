"use client";

import Link from "next/link";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useCallback, useState } from "react";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { replayRequest, type ReplayTurn } from "@/lib/api/research-replay.client";
import styles from "./research-replay.module.css";

type Page = { owner_id: string; project_id: string; count: number; page: number; total_pages: number };
type TurnPage = Page & { parent_id: string | null; results: Array<ReplayTurn & { child_count: number }> };
type Project = { id: string; title: string; revision: number; archived: boolean; created_at: string; turn_id: string | null };
type ProjectPage = Page & { parent: Project | null; origin_unavailable: boolean; results: Project[] };
const date = (value: string) => new Date(value).toLocaleDateString("zh-CN");

function Pager({ page, pages, change }: { page: number; pages: number; change: (page: number) => void }) {
  return pages > 1 ? <nav className={styles.branchPager} aria-label="当前层级分页"><button disabled={page <= 1} onClick={() => change(page - 1)}>上一页</button><span>{page}/{pages}</span><button disabled={page >= pages} onClick={() => change(page + 1)}>下一页</button></nav> : null;
}

export function TurnBranches({ id, owner, active, parent = "", ancestors = [], onSelect }: { id: string; owner: string; active: string; parent?: string; ancestors?: string[]; onSelect: (id: string) => void }) {
  const [page, setPage] = useState(1), [expanded, setExpanded] = useState<string[]>([]);
  const load = useCallback((url: string, signal: AbortSignal) => replayRequest<TurnPage>(owner, url, { signal }), [owner]);
  const resource = usePersistentWorkspace<TurnPage>(`/reading/research-projects/${id}/replay-tree/?${new URLSearchParams({ page: String(page), ...(parent ? { parent_id: parent } : {}) })}`, owner, undefined, load);
  const data = resource.error ? null : resource.data;
  if (resource.error) return <p role="alert">{resource.error}<button onClick={resource.reload}>重新读取分支</button></p>;
  if (!data) return <p role="status">正在读取这一层轮次…</p>;
  return <><ol className={styles.branchList}>{data.results.map(turn => {
    const open = expanded.includes(turn.id), circular = ancestors.includes(turn.id), deep = ancestors.length >= 30;
    return <li key={turn.id} data-current={turn.id === active}><div className={styles.branchRow}>
      {turn.child_count && !circular && !deep ? <button className={styles.branchToggle} aria-expanded={open} aria-label={`${open ? "收起" : "展开"}${turn.title}的后续轮次`} onClick={() => setExpanded(values => open ? values.filter(value => value !== turn.id) : [...values, turn.id])}>{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</button> : <span className={styles.branchToggle} />}
      <button onClick={() => onSelect(turn.id)} aria-pressed={turn.id === active}><strong>{turn.title}</strong><small>{date(turn.created_at)} · {turn.material_count} 条起始选材{turn.child_count ? ` · ${turn.child_count} 个后续轮次` : ""}</small></button></div>
      {circular ? <p>该路径存在循环，按时间列表仍可核对原记录。</p> : deep && turn.child_count ? <p>层级较深，请从这一步继续展开。<Link href={`/account/research/${id}/history?turn=${turn.id}`}>打开此轮次</Link></p> : open ? <TurnBranches id={id} owner={owner} active={active} parent={turn.id} ancestors={[...ancestors, turn.id]} onSelect={onSelect} /> : null}
    </li>;
  })}</ol>{!data.results.length ? <p className={styles.branchHint}>{parent ? "此轮没有后续分支。" : "当前没有可展开的起始轮次。全部记录可从时间列表核对。"}</p> : null}<Pager page={page} pages={data.total_pages} change={value => { setPage(value); setExpanded([]); }} /></>;
}

export function ProjectBranches({ id, owner, ancestors = [] }: { id: string; owner: string; ancestors?: string[] }) {
  const [page, setPage] = useState(1), [expanded, setExpanded] = useState<string[]>([]);
  const load = useCallback((url: string, signal: AbortSignal) => replayRequest<ProjectPage>(owner, url, { signal }), [owner]);
  const resource = usePersistentWorkspace<ProjectPage>(`/reading/research-projects/${id}/replay-tree/?view=projects&page=${page}`, owner, undefined, load);
  const data = resource.error ? null : resource.data;
  if (resource.error) return <p role="alert">{resource.error}<button onClick={resource.reload}>重新读取研究关联</button></p>;
  if (!data) return <p role="status">正在核对本人派生研究…</p>;
  return <div className={styles.projectBranches}>
    {!ancestors.length ? data.parent ? <p>来自研究 <Link href={`/account/research/${data.parent.id}/history${data.parent.turn_id ? `?turn=${data.parent.turn_id}` : ""}`}>{data.parent.title}</Link>{!data.parent.turn_id ? "（原轮次已不存在）" : ""}</p> : data.origin_unavailable ? <p>原研究当前不可用，这份研究与已保存笔记仍保留。</p> : <p>这份研究没有记录其他研究的分支来源。</p> : null}
    <p className={styles.branchHint}>直接派生研究 {data.count} 份 · 仅本人可见</p>
    <ul>{data.results.map(project => {
      const open = expanded.includes(project.id), circular = [...ancestors, id].includes(project.id), deep = ancestors.length >= 12;
      return <li key={project.id}><Link href={`/account/research/${project.id}/history`}>{project.title}</Link><small>{project.archived ? "已归档 · " : ""}{date(project.created_at)}</small>
        {project.turn_id ? <Link href={`/account/research/${id}/history?turn=${project.turn_id}`}>回到来源轮次</Link> : <small>原轮次已不存在</small>}
        {!circular && !deep ? <button aria-expanded={open} onClick={() => setExpanded(values => open ? values.filter(value => value !== project.id) : [...values, project.id])}>{open ? "收起下级" : "查看下级"}</button> : <small>{circular ? "已返回路径中的研究，请通过链接单独查看。" : "层级较深，可打开这份研究继续。"}</small>}
        {open && !circular && !deep ? <ProjectBranches id={project.id} owner={owner} ancestors={[...ancestors, id]} /> : null}
      </li>;
    })}</ul>
    <Pager page={page} pages={data.total_pages} change={value => { setPage(value); setExpanded([]); }} />
  </div>;
}
