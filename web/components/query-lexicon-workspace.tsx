"use client";

import Link from "next/link";

import { LoaderCircle, RefreshCw, Search, WandSparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { EntityPicker, type EntityValue } from "@/components/admin/forms/workflow-fields";
import type { ScopedSearchEnvelope } from "@/lib/api/search.types";
import { normalizePublicResourceUrl } from "@/lib/api";
import styles from "./lexicon-reference.module.css";
import { AdminPublicPreviewFrame } from "@/components/admin/admin-public-preview-frame";

type LexiconPayload = {
  person?: {id:string;preferred_name:string;original_name:string;birth_year:number|null;death_year:number|null;portrait:string;biography:string;scholar_slug:string|null};
  term_count?:number; offset?:number; limit?:number; has_more?:boolean;
  permissions?: { can_manage: boolean };
  initialized?: boolean;
  revision?: number | null;
  generation?: { id: string; status: string; entry_count?: number; content_hash?: string } | null;
  entries?: number;
  public_active_entries?: number;
  admin_resolvable_entries?: number;
  pending_events?: number;
  failed_events?: number;
  entities?: Array<{ entity_type: string; entries: number; public_active_entries: number; admin_resolvable_entries: number }>;
  terms?: Array<{ id: string; term: string; normalized_term: string; entity_type: string; entity_id: string; entity_label: string; language: string; term_type: string; trust_level: string; source_kind: string; public_active: boolean; admin_resolvable: boolean; provenance?: unknown }>;
};

const sourceLabels: Record<string, string> = {
  authority: "权威对象",
  canonical: "规范名称",
  verified_alias: "已验证别名",
  generated: "系统派生",
  legacy: "历史映射",
};

function dryRunText(value: unknown, depth = 0): string {
  if (depth > 3) return "…";
  if (Array.isArray(value)) return value.slice(0, 20).map((item) => dryRunText(item, depth + 1)).join("、");
  if (value && typeof value === "object") {
    const labels: Record<string, string> = { source_entity_count: "来源实体数", expected_entry_count: "预计词条数", anomaly: "异常", revision: "版本", generation: "生成批次", content_hash: "内容校验" };
    return Object.entries(value as Record<string, unknown>).slice(0, 40).map(([key, item]) => `${labels[key] ?? key}：${dryRunText(item, depth + 1)}`).join("\n");
  }
  return String(value ?? "—");
}

export function QueryLexiconWorkspace() {
  const [people, setPeople] = useState<EntityValue[]>([]);
  const personId = people.at(-1)?.id ?? "";
  const [offset, setOffset] = useState(0);
  const [checks, setChecks] = useState<Record<string,{label:string;ok:boolean;at:string}>>({});
  const activeRequest = useRef(0);
  const checking = useRef(false);
  const [query, setQuery] = useState("");
  const [previewTerm, setPreviewTerm] = useState("");
  const [payload, setPayload] = useState<LexiconPayload | null>(null);
  const [dryRun, setDryRun] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const revision = ++activeRequest.current;
    setLoading(true);
    try {
      const search = new URLSearchParams();
      if (personId) { search.set("entity_type","person");search.set("entity_id",personId); }
      else if (query.trim()) search.set("q",query.trim());
      search.set("offset",String(offset));
      const next = await apiRequest<LexiconPayload>(`/catalog/admin/query-lexicon/?${search.toString()}`, {}, getServerSessionCredential());
      if (revision !== activeRequest.current) return;
      setPayload(next);
      setMessage("");
    } catch (error) {
      if (revision === activeRequest.current) setMessage(error instanceof Error ? error.message : "检索用语读取失败。");
    } finally {
      if (revision === activeRequest.current) setLoading(false);
    }
  }, [query, personId, offset]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => { window.clearTimeout(timer);activeRequest.current += 1; };
  }, [load]);

  async function run(action: "dry_run" | "reconcile") {
    if (checking.current || busy) return;
    checking.current=true;setBusy(action);
    try {
      const result = await apiRequest<Record<string, unknown>>(
        "/catalog/admin/query-lexicon/",
        { method: "POST", body: JSON.stringify({ action }) },
        getServerSessionCredential(),
      );
      if (action === "dry_run") setDryRun(result);
      await load();
      setMessage(action === "dry_run" ? "预演已完成，词典没有被修改。" : "重建任务已进入处理任务。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "QueryLexicon 操作失败。");
    } finally {
      checking.current=false;setBusy("");
    }
  }

  async function checkTerms() {
    if (!personId || !payload || checking.current || loading) return;
    checking.current=true;setBusy("check");
    const revision=activeRequest.current;
    try {
      for (const row of payload.terms ?? []) {
        if (revision!==activeRequest.current) break;
        try {
          const parameters=new URLSearchParams({context:"scholars",visibility:"public",envelope:"1",q:row.term,limit:"2"});
          const result=await apiRequest<ScopedSearchEnvelope>(`/catalog/search/?${parameters}`);
          const scholars=result.groups.find(group=>group.context==="scholars");
          const count=scholars?.count ?? 0;
          const ok=count===1 && scholars?.results[0]?.id===personId;
          if (revision===activeRequest.current) setChecks(current=>({...current,[row.id]:{label:ok ? "1 条（同一结果）" : `${count} 条（需核对）`,ok,at:new Date().toLocaleString("zh-CN")}}));
        } catch(error) {
          if (revision===activeRequest.current) setChecks(current=>({...current,[row.id]:{label:error instanceof Error ? error.message : "检查失败",ok:false,at:new Date().toLocaleString("zh-CN")}}));
        }
      }
    } finally { checking.current=false;setBusy(""); }
  }

  return (
    <div className={`admin-v2-ops-split ${styles.layout}`}>
      <div className="admin-page">
      <header className="admin-page-title">
        <div><p>处理中心 / 检索用语</p><h1>检索用语检查</h1><span>查看不同写法是否找到同一内容。用语来自学者、理论、学科和主题，修改请前往对应编辑页。</span></div>
        <div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={15} />刷新</button>{payload?.permissions?.can_manage ? <><button className="button" type="button" onClick={() => void run("dry_run")} disabled={Boolean(busy)}><WandSparkles size={15} />预演</button><button className="button" type="button" onClick={() => void run("reconcile")} disabled={Boolean(busy)}><WandSparkles size={15} />正式同步</button></> : null}</div>
      </header>
      <fieldset disabled={Boolean(busy)} style={{border:0,padding:0}}><EntityPicker label="当前检查的学者" endpoint="/catalog/admin/people/" queryParam="search" nameField="preferred_name" values={people} onChange={values=>{activeRequest.current+=1;setPeople(values.slice(-1));setOffset(0);setPayload(null);setChecks({});setPreviewTerm("");}}/></fieldset>
      {!personId ? <div className="admin-toolbar"><label><Search size={15} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPreviewTerm(""); }} placeholder="输入姓名或检索用语" aria-label="检索用语" /></label></div> : null}
      {message ? <p className="form-message" role="status">{message}</p> : null}
      {payload && !payload.permissions?.can_manage ? <p className="form-message" role="status">当前账户为只读权限。正式同步由超级管理员执行。</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取词典状态……</p> : null}
      {payload ? <>
        {personId ? <section className={styles.person}><header><h2>当前检查的学者</h2><span>来源：学者记录（只读）</span></header><div>{payload.person?.portrait ? <img src={normalizePublicResourceUrl(payload.person.portrait)} alt={payload.person.preferred_name}/> : <span className={styles.emptyPortrait}/>}<div><h3>{payload.person?.preferred_name}</h3><p>{payload.person?.original_name}</p><p>{payload.person?.birth_year ?? "—"}—{payload.person?.death_year ?? ""}</p>{payload.person?.scholar_slug ? <Link href="/admin/scholars">前往学者列表</Link> : null}</div></div></section> : null}
        <details className={styles.technical}><summary>派生状态与全部实体覆盖</summary>        <section className="admin-panel"><header><h2>当前派生状态</h2></header><dl className="admin-stats-grid"><div><dt>内容版本</dt><dd>{payload.revision ?? "未初始化"}</dd></div><div><dt>活动生成批次</dt><dd translate="no">{payload.generation?.id ?? "—"}</dd></div><div><dt>活动词条</dt><dd>{payload.entries ?? 0}</dd></div><div><dt>公开可用词条</dt><dd>{payload.public_active_entries ?? 0}</dd></div><div><dt>后台可解析词条</dt><dd>{payload.admin_resolvable_entries ?? 0}</dd></div><div><dt>待处理变更</dt><dd>{payload.pending_events ?? 0}</dd></div><div><dt>失败同步</dt><dd>{payload.failed_events ?? 0}</dd></div></dl><p className="admin-help">公开搜索只读公开可用词条；后台候选解析可以读取后台可解析词条。草稿权威对象不会因此暴露到公网。</p></section>
        <section className="admin-panel"><header><h2>实体覆盖</h2></header><div className="admin-table-wrap"><table><thead><tr><th>实体类型</th><th>词条</th><th>公开</th><th>后台</th></tr></thead><tbody>{(payload.entities ?? []).map((row) => <tr key={row.entity_type}><td>{({ person: "学者", knowledge_node: "理论节点", discipline: "学科", subdiscipline: "子学科", topic: "主题", theory_school: "理论流派", concept: "概念" } as Record<string, string>)[row.entity_type] ?? row.entity_type}</td><td>{row.entries}</td><td>{row.public_active_entries}</td><td>{row.admin_resolvable_entries}</td></tr>)}</tbody></table></div></section>
</details>
        <section className="admin-panel"><header><h2>检索用语与结果</h2><button className="button secondary" disabled={!personId || loading || Boolean(busy)} onClick={()=>void checkTerms()}>{busy==="check" ? "检查中…" : "检查本页用语"}</button></header><div className="admin-table-wrap"><table><thead><tr><th>词条</th><th>实体</th><th>搜索结果</th><th>当前状态</th><th>来源</th></tr></thead><tbody>{(payload.terms ?? []).map((row) => <tr key={row.id}><td><button className="admin-v2-preview-term" type="button" aria-pressed={previewTerm === row.term} onClick={() => setPreviewTerm(row.term)}>{row.term}</button><small translate="no">{row.normalized_term}</small></td><td>{row.entity_label}<small>{({ person: "学者", knowledge_node: "理论节点", discipline: "学科", subdiscipline: "子学科", topic: "主题", theory_school: "理论流派", concept: "概念" } as Record<string, string>)[row.entity_type] ?? row.entity_type}</small></td><td title={checks[row.id]?.at}>{checks[row.id]?.label || "—"}</td><td>{checks[row.id] ? checks[row.id].ok ? "已核实" : "需核对" : "待检查"}</td><td>{sourceLabels[row.source_kind] ?? row.source_kind}</td></tr>)}</tbody></table></div><footer className={styles.pagination}><button type="button" disabled={loading || Boolean(busy) || !offset} onClick={()=>{setOffset(value=>Math.max(0,value-60));setPayload(null);}}>上一页</button><span>共 {payload.term_count ?? "—"} 条 · 第 {Math.floor(offset/60)+1} 页</span><button type="button" disabled={loading || Boolean(busy) || !payload.has_more} onClick={()=>{setOffset(value=>value+60);setPayload(null);}}>下一页</button></footer>{personId && !offset && !payload.has_more && payload.terms?.length && payload.terms.every(row=>checks[row.id]?.ok) ? <p className={styles.success}>本次检查中，以上不同写法均只返回当前学者。</p> : null}<p>检查结果为本次查询记录，不会自动新增、合并或发布任何用语。</p></section>
      </> : null}
      {dryRun ? <section className="admin-panel"><header><h2>最近一次预演</h2><span>只读结果</span></header><pre className="admin-readable-json">{dryRunText(dryRun)}</pre></section> : null}
      </div>
      <AdminPublicPreviewFrame title="词语搜索预览" description={previewTerm ? `公开搜索：${previewTerm}` : undefined} src={previewTerm ? `/explore/original?type=${personId ? "scholar" : "all"}&q=${encodeURIComponent(previewTerm)}` : null} emptyMessage="选择词条后预览公开搜索" />
    </div>
  );
}
