"use client";

import { UserRound, ChevronDown } from "lucide-react";
import { authorityRequest, type AuthorityDetail } from "@/lib/api/person-authority.client";
import { RecycleControl } from "@/components/admin/recycle-control";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ActionButton } from "@/components/action-feedback";
import { PageHeader } from "@/components/admin-ui";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { ApiRequestError, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { useApiResource } from "@/lib/api/use-api-resource";
import {
  asRecord, canConfirmPersonMerge, isPersonId, mergePerson, personApi, personPage, rollbackPerson,
  rollbackState, textValue, type MergeHistory, type MergeInput, type PersonDuplicates, type PersonMerge,
  type PersonPreview, type PersonSearch, type PersonSummary, type PersonBusinessImpact,
} from "@/lib/api/person-resolution";
import styles from "./person-resolution.module.css";

const mergeKey=(owner:string)=>`stl-person-merge-command:${owner}`;
type PendingMerge={source:string;input:MergeInput};
function pendingMerge(owner:string):PendingMerge|null{
  const raw=sessionStorage.getItem(mergeKey(owner));if(!raw)return null;
  const row=asRecord(JSON.parse(raw)),input=asRecord(row.input);
  if(typeof row.source!=="string"||!isPersonId(row.source)||typeof input.target_person!=="string"||!isPersonId(input.target_person)||typeof input.idempotency_key!=="string"||!isPersonId(input.idempotency_key)||typeof input.fingerprint!=="string"||! /^[a-f0-9]{64}$/.test(input.fingerprint)||input.confirmed!==true)throw Error("原合并请求记录不完整，请保留本页并核对操作历史。");
  return {source:row.source,input:{target_person:input.target_person,fingerprint:input.fingerprint,idempotency_key:input.idempotency_key,confirmed:true}};
}
function retainMerge(owner:string,source:string,input:MergeInput){
  const previous=pendingMerge(owner);
  if(previous&&(previous.source!==source||previous.input.idempotency_key!==input.idempotency_key))throw Error("另一次合并尚未确认，请先使用上方的原请求核对入口。");
  sessionStorage.setItem(mergeKey(owner),JSON.stringify({source,input}));window.dispatchEvent(new Event("stl-person-merge-request"));
}
function clearMerge(owner:string,id:string){
  if(pendingMerge(owner)?.input.idempotency_key===id){sessionStorage.removeItem(mergeKey(owner));window.dispatchEvent(new Event("stl-person-merge-request"));}
}
const mergeRejected=(reason:unknown)=>reason instanceof ApiRequestError&&!(reason instanceof PrivateOwnerVerificationError)&&[400,401,403,404,409].includes(reason.status);

export function PersonMergeRecovery({owner}:{owner:string}){
  const router=useRouter(),active=useActiveView(),sending=useRef(false);
  const [original,setOriginal]=useState<PendingMerge|null>(null),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
  useEffect(()=>{let alive=true;const read=()=>{if(!alive)return;try{setOriginal(pendingMerge(owner));}catch(reason){setMessage(reason instanceof Error?reason.message:"无法读取原请求。");}};queueMicrotask(read);window.addEventListener("stl-person-merge-request",read);return()=>{alive=false;window.removeEventListener("stl-person-merge-request",read);};},[owner]);
  async function recover(){if(!original||sending.current)return;sending.current=true;setBusy(true);setMessage("");try{
    const result=await mergePerson(original.source,original.input,getServerSessionCredential()??"",owner);
    if(!active.current)return;
    if(result.source_person_id!==original.source||result.target_person_id!==original.input.target_person)throw Error("合并操作结果与原人物不一致，请保留请求继续核对。");
    clearMerge(owner,original.input.idempotency_key);router.push(personPage(original.source,"",result.id));router.refresh();
  }catch(reason){if(!active.current)return;if(mergeRejected(reason)){try{clearMerge(owner,original.input.idempotency_key);}catch{setMessage("请求已被拒绝，浏览器暂不能清除原编号，请核对操作记录。");return;}}setMessage(reason instanceof Error?reason.message:"原请求暂未确认。");}finally{sending.current=false;if(active.current)setBusy(false);}}
  if(!original&&!message)return null;
  return <aside className={styles.notice} role="status"><strong>人物合并结果核对</strong>{original?<><p>上次确认的合并尚未收到完整操作结果。只保留人物编号、核对版本和原请求号；继续时使用同一请求，已执行的操作不会再次合并。</p><button type="button" disabled={busy} onClick={()=>void recover()}>{busy?"正在核对…":"按原编号核对并继续"}</button></>:null}{message?<p>{message}</p>:null}</aside>;
}

const statusLabels: Record<string, string> = { verified: "已核验", draft: "草稿", needs_review: "待核验", merged: "已合并", archived: "已归档", rejected: "未采用" };
const fieldLabels: Record<string, string> = {
  id: "记录编号", person_id: "人物编号", scholar_id: "学者档案编号", preferred_name: "标准名称称", original_name: "原文名称",
  birth_year: "出生年", death_year: "逝世年", authority_status: "核验状态", biography: "人物介绍", aliases: "原始别名",
  external_ids: "外部标识符", short_description: "档案简介", slug: "页面名称", name: "名称", title: "标题", term: "词条",
  role: "署名职责", approved: "已确认", is_verified: "已核验", language: "语言", variant_type: "名称类型", source_kind: "来源类型",
  source: "原始来源", source_ref: "来源依据", editorial_status: "编辑状态", review_status: "审核状态", status: "状态",
  work_id: "作品编号", edition_id: "版本编号", node_id: "知识节点编号", topic_id: "主题编号", discipline_id: "学科编号",
  subdiscipline_id: "子学科编号", theory_school_id: "旧理论编号", proposition: "观点", description: "说明", start_year: "开始年",
  end_year: "结束年", event_type: "事件类型", timeline: "学术经历", affiliations: "机构", key_concerns: "主要关切",
  revision: "修订号", catalog_revision_id: "书目修订编号", public_slug: "公开页面名称", publication_mode: "发布方式",
  displayable: "允许展示", public_active: "公开检索有效", admin_resolvable: "后台可解析", trust_level: "信任级别", term_type: "词条类型",
};

function useActiveView() {
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  return active;
}

function Failure({ message, retry, label = "重新读取" }: { message: string; retry: () => void; label?: string }) {
  return <div className={styles.notice} role="alert"><p>{message}</p><ActionButton className="button secondary" onClick={retry}>{label}</ActionButton></div>;
}

function PersonLabel({ person }: { person: PersonSummary }) {
  return <><strong>{person.preferred_name}</strong><span>{[person.original_name, person.birth_year === null ? "出生年未填写" : `${person.birth_year}年出生`, statusLabels[person.authority_status] || person.authority_status].filter(Boolean).join(" · ")}</span></>;
}

export function PersonPicker({ sourceId = "", credential }: { sourceId?: string; credential: string }) {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, error, loading, retry } = useApiResource<PersonSearch>(personApi.search(submitted), credential);
  const label = sourceId ? "查找其他保留人物" : "查找馆内人物";
  function search(event: FormEvent) { event.preventDefault(); if (submitted === query.trim()) retry(); else setSubmitted(query.trim()); }
  return <section className={`admin-panel ${styles.panel}`} aria-label={label}>
    <h2>{label}</h2>
    <form className={styles.search} onSubmit={search}><label>{label}<input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={200} placeholder="输入名称或已核验译名" /></label><button className="button secondary" type="submit">查找</button></form>
    {error ? <Failure message={error} retry={retry} /> : loading ? <p role="status">正在读取人物…</p> : data ? <>
      <ul className={styles.people}>{data.results.filter((row) => row.id !== sourceId).map((row) => <li key={row.id}><Link prefetch={false} href={sourceId ? personPage(sourceId, row.id) : personPage(row.id)}><PersonLabel person={row} /><b>{sourceId ? "设为保留人物" : "检查重复记录"}</b></Link></li>)}</ul>
      {!data.results.some((row) => row.id !== sourceId) ? <p>未找到符合条件的其他人物，请换一个名称查找。</p> : null}
      {data.has_more ? <p>这里只显示前20项，请补充名称缩小范围。</p> : null}
    </> : null}
  </section>;
}

function Details({ value }: { value: unknown }) {
  return <dl className={styles.fields}>{Object.entries(asRecord(value)).map(([field, item]) => <div key={field}><dt>{fieldLabels[field] || field}</dt><dd>{textValue(item)}</dd></div>)}</dl>;
}

export function History({ sourceId, credential }: { sourceId: string; credential: string }) {
  const { data, error, loading, retry } = useApiResource<MergeHistory[]>(personApi.history(sourceId), credential);
  return <section className={`admin-panel ${styles.panel}`} aria-label="最近合并记录"><div className={styles.heading}><h2>最近合并记录</h2><ActionButton className="button secondary" onClick={retry}>刷新操作记录</ActionButton></div>
    <p>网络中断或重新打开页面后，可在这里核对已保存的操作。最多显示最近20次。</p>
    {error ? <Failure message={error} retry={retry} /> : loading ? <p role="status">正在读取操作记录…</p> : data?.length ? <ul className={styles.rows}>{data.map((row) => <li key={row.id}><Link prefetch={false} href={personPage(sourceId, "", row.id)}>{row.rolled_back_at ? "已撤回的合并" : "已执行的合并"} · {new Date(row.created_at).toLocaleString("zh-CN")}</Link><small>{row.id}</small></li>)}</ul> : <p>暂无已保存的合并记录。仅此列表为空不能证明仍在传输的请求未执行。</p>}
  </section>;
}

function SourceWorkspace({ sourceId, targetId, allowed, credential }: { sourceId: string; targetId: string; allowed: boolean; credential: string }) {
  const { data, error, loading, retry } = useApiResource<PersonDuplicates>(personApi.duplicates(sourceId), credential);
  return <>
    <Link prefetch={false} href={personPage()}>重新选择来源人物</Link>
    {error ? <Failure message={error} retry={retry} /> : loading ? <p role="status">正在检查疑似重复…</p> : data ? <>
      <section className={`admin-panel ${styles.panel}`} aria-label="来源人物"><h2>来源人物</h2><div className={styles.identity}><PersonLabel person={data.source} /><RecycleControl kind="person" id={data.source.id} name={data.source.preferred_name} onDeleted={() => window.location.assign(personPage())} /></div><p>确认合并后，来源记录仍保留，其无冲突引用归入保留人物。</p></section>
      {!allowed ? <p className={styles.notice}>当前账户可以查重。影响预览、合并与撤回仅向书库所有者开放。</p> : null}
      <section className={`admin-panel ${styles.panel}`} aria-label="疑似重复人物"><h2>疑似重复人物</h2><p>名称或标识符相同只是核对线索，不能直接认定为同一个人。</p>
        {data.results.length ? <ul className={styles.people}>{data.results.map((row) => <li key={row.person.id}><div className={styles.identity}><PersonLabel person={row.person} />
          {row.matches.map((match, i) => <span key={i}>{asRecord(match).kind === "name" ? "名称匹配" : "标识符匹配"} {textValue(asRecord(match).values)}</span>)}
          {row.identity_conflicts.length ? <span>有 {row.identity_conflicts.length} 项身份差异，需要核对</span> : null}
          {allowed ? <Link prefetch={false} className="button secondary" href={personPage(sourceId, row.person.id)}>保留此人物并查看影响</Link> : null}</div></li>)}</ul> : <p>未找到名称或标识符匹配的其他人物。这不代表馆内没有重复记录。</p>}
        {data.has_more ? <p>候选超过20项，请用下方查找核对具体人物。</p> : null}
      </section>
      {allowed ? <><details open={!targetId}><summary>{targetId ? "更换保留人物" : "没有合适候选？查找其他人物"}</summary><PersonPicker sourceId={sourceId} credential={credential} /></details>{targetId ? <PreviewLoader key={`${sourceId}:${targetId}`} sourceId={sourceId} targetId={targetId} credential={credential} /> : null}</> : null}
    </> : null}
    {allowed ? <History sourceId={sourceId} credential={credential} /> : null}
  </>;
}

function AuthorityPortrait({id,name}:{id:string;name:string}) {
  const user=useAdminSession(),owner=user?String(user.id):"";
  const [url,setUrl]=useState("");
  useEffect(()=>{if(!owner||!isPersonId(id))return;const controller=new AbortController();setUrl("");void authorityRequest<AuthorityDetail>(owner,id+"/workspace/",{signal:controller.signal}).then(value=>{if(!controller.signal.aborted&&value.id===id)setUrl(normalizePublicResourceUrl(value.portrait_url));}).catch(()=>{if(!controller.signal.aborted)setUrl("");});return()=>controller.abort();},[owner,id]);
  return <div className={styles.portrait}>{url?<img src={url} alt={name+"肖像"} onError={()=>setUrl("")}/>:<UserRound size={42} strokeWidth={1}/>}</div>;
}
function PreviewFacts({ preview }: { preview: PersonPreview }) {
  const source = asRecord(preview.source), target = asRecord(preview.target);
  return <>
    <div className={styles.identityCompare}>
      {([{label:"候选 A",note:"保留人物",person:target,rows:"target_rows"},{label:"候选 B",note:"待合并记录",person:source,rows:"source_rows"}] as const).map(({label,note,person,rows},index)=><section key={label} className={index?styles.compareSource:styles.compareTarget}><header><h3>{label}</h3><span>{note}</span></header><div className={styles.compareIdentity}><AuthorityPortrait id={String(person.id)} name={textValue(person.preferred_name)}/><dl className={styles.fields}>{["preferred_name","original_name"].map(field=><div key={field}><dt>{fieldLabels[field]}</dt><dd>{textValue(person[field])}</dd></div>)}<div><dt>常用异名</dt><dd className={styles.aliases}>{preview.references.filter(group=>asRecord(group).model==="catalog.PersonNameVariant").flatMap(group=>{const values=asRecord(group)[rows];return Array.isArray(values)?values:[];}).map((row,at)=><details key={at}><summary>{textValue(asRecord(row).name)}</summary><p>{asRecord(row).is_verified?"已核验":"待核验"} · {textValue(asRecord(row).source_note)}</p></details>)}</dd></div></dl></div><details className={styles.personDetails} open><summary>展开详细信息 <ChevronDown size={12}/></summary><dl className={styles.fields}>{["birth_year","death_year","country_region","biography","external_ids"].map(field=><div key={field}><dt>{field==="country_region"?"国别／地区":fieldLabels[field]}</dt><dd>{textValue(person[field])}</dd></div>)}</dl></details></section>)}
      <aside className={styles.compareResult}><h3>比对结果</h3><strong>{preview.identity_conflicts.length?"身份信息存在差异":"当前字段未发现明确冲突"}</strong>{preview.identity_conflicts.map((item,index)=><p key={index}>{fieldLabels[textValue(asRecord(item).field)]||textValue(asRecord(item).field)}：{textValue(asRecord(item).source)} / {textValue(asRecord(item).target)}</p>)}<p>请结合原始署名与来源核对，名称相近不能单独证明同一身份。</p><strong>保留方向</strong><p>候选 B 的无冲突引用归入候选 A。双方原始基础资料和历史记录保留。</p></aside>
    </div>
    <p>涉及 {preview.affected_works.length} 部作品、{preview.affected_edition_count} 个版本和 {preview.publication_revision_count} 条历史公开修订。历史修订不会被覆盖。</p>
    {preview.business_impact ? <BusinessImpact impact={preview.business_impact} /> : null}
    <details><summary>查看作品与版本</summary><ul className={styles.rows}>{preview.affected_works.map((value, i) => <li key={i}><strong>{textValue(asRecord(value).title)}</strong><small>{textValue(asRecord(value).id)}</small></li>)}</ul>{preview.affected_editions.map((value, i) => <details key={i}><summary>版本 {textValue(asRecord(value).id)}</summary><Details value={value} /></details>)}</details>
    <details><summary>查看历史公开修订</summary>{preview.publication_revisions.map((value, i) => <Details key={i} value={value} />)}</details>
    <section aria-label="关联影响"><h3>关联影响</h3><p>下方为双方现有引用。学者档案的下游引用保持原编号，只随同一份档案保留。</p>
      {preview.references.map((value, i) => { const row = asRecord(value); return <details key={i} className={styles.reference}><summary>{textValue(row.label)} · 来源 {textValue(row.source_count)} 项 · 保留人物 {textValue(row.target_count)} 项{Array.isArray(row.collisions) && row.collisions.length ? " · 存在重复关系" : ""}{row.truncated ? " · 未完整显示" : ""}</summary>
        <div className={styles.comparison}>{["source_rows", "target_rows"].map((key) => <section key={key}><h4>{key === "source_rows" ? "来源人物" : "保留人物"}</h4>{Array.isArray(row[key]) && row[key].length ? row[key].map((item: unknown, index: number) => <Details key={index} value={item} />) : <p>无相关记录</p>}</section>)}</div>
      </details>; })}
    </section>
    <details><summary>活动检索词条 · 来源 {preview.lexicon_entries.source} 项 · 保留人物 {preview.lexicon_entries.target} 项</summary>
      {!preview.lexicon_entries.available ? <p role="alert">{preview.lexicon_entries.error || "检索词典状态待核实"}</p> : <div className={styles.comparison}>{[preview.lexicon_entries.source_rows, preview.lexicon_entries.target_rows].map((rows, i) => <section key={i}><h4>{i === 0 ? "来源人物" : "保留人物"}</h4>{rows.length ? rows.map((row) => <Details key={row.id} value={row} />) : <p>当前没有活动词条</p>}</section>)}</div>}
    </details>
    {preview.identity_conflicts.length ? <section><h3>身份差异</h3>{preview.identity_conflicts.map((value, i) => <Details key={i} value={value} />)}</section> : null}
    <ul>{(preview.execution_guidance || []).map((line) => <li key={line}>{line}</li>)}</ul>
  </>;
}

export function BusinessImpact({ impact }: { impact: PersonBusinessImpact }) {
  return <section aria-label="作品职责与公开位置"><h3>作品、职责与公开位置</h3><p>只合并人物身份；下列作者、译者及编者职责保持不变。相似名称不等于同一人物。</p><ul className={styles.rows}>{impact.editions.map((row) => <li key={row.edition_id}><strong>{row.title}</strong><span>{row.edition_label}</span><p>{row.roles.map((role) => `${role.name}：${role.role_label}${role.approved ? "（已确认）" : "（待确认）"}`).join("；") || "此版本通过其他条目关系受到影响"}</p><p>{row.publication.detail}</p><div className={styles.actions}><Link prefetch={false} href={row.editor_url}>核对当前版本与署名</Link><Link prefetch={false} href={row.publication_url}>查看发布更新</Link>{row.publication.public_url ? <Link prefetch={false} href={row.publication.public_url} target="_blank">核验公开位置</Link> : null}</div></li>)}</ul>{!impact.editions.length ? <p>没有需要更新的作品版本；人物和学者关系仍按影响预览处理。</p> : null}
    {impact.events.length ? <details open><summary>公开更新的实际处理结果</summary>{impact.events.map((event) => <article key={event.id}><strong>{event.title} · {event.status_label}</strong><p>{event.deliveries.map((row) => `${row.label}：${row.status}（来源修订${row.source_revision}）`).join("；")}</p>{event.error_code ? <p>异常 {event.error_code}，请从原发布记录检查并恢复。</p> : null}<Link prefetch={false} href={event.inspect_url}>查看关联处理</Link><small> 事件 {event.id}</small></article>)}</details> : null}</section>;
}

export function PreviewLoader({ sourceId, targetId, credential }: { sourceId: string; targetId: string; credential: string }) {
  const resource = useApiResource<PersonPreview>(personApi.preview(sourceId, targetId), credential);
  return <section className={`admin-panel ${styles.panel} ${styles.mergePreview}`} aria-label="合并影响预览"><h2>合并候选比较与影响</h2>
    {resource.error ? <Failure message={resource.error} retry={resource.retry} label="重新预览" /> : resource.loading ? <p role="status">正在核对双方资料与关联…</p> : resource.data ? <MergeReview key={resource.data.fingerprint} preview={resource.data} sourceId={sourceId} targetId={targetId} credential={credential} refresh={resource.retry} /> : null}
  </section>;
}

function MergeReview({ preview, sourceId, targetId, credential, refresh }: { preview: PersonPreview; sourceId: string; targetId: string; credential: string; refresh: () => void }) {
  const user = useAdminSession();
  const router = useRouter();
  const active = useActiveView();
  const sending = useRef(false);
  const attempt = useRef<MergeInput | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [failure, setFailure] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const eligible = canConfirmPersonMerge(preview, sourceId, targetId);
  async function submit() {
    if (sending.current || !eligible || (!confirm && !attempt.current)) return;
    const input = attempt.current ?? { target_person: targetId, fingerprint: preview.fingerprint, confirmed: true, idempotency_key: createRequestKey() };
    try { retainMerge(String(user?.id||""),sourceId,input); } catch(reason) { setFailure(reason instanceof Error?reason.message:"无法保存原合并请求，尚未提交。"); return; }
    attempt.current = input;
    sending.current = true;
    setBusy(true); setFailure("");
    try {
      const result = await mergePerson(sourceId, input, credential, String(user?.id || ""));
      if (!active.current) return;
      if(result.source_person_id!==sourceId||result.target_person_id!==targetId)throw Error("合并操作结果与当前人物不一致，请查询原请求。");
      clearMerge(String(user?.id||""),input.idempotency_key);
      router.replace(personPage(sourceId, "", result.id));
    } catch (reason) {
      if (!active.current) return;
      // An HTTP error after a committed write or a lost response is not proof
      // of failure. Reuse the exact body/key until the outcome is known.
      const knownRejection = mergeRejected(reason);
      if(knownRejection){try{clearMerge(String(user?.id||""),input.idempotency_key);attempt.current=null;}catch{setFailure("合并被拒绝，但浏览器暂不能清除原请求，请保留本页。");setUncertain(true);return;}}
      setUncertain(!knownRejection);
      setFailure(reason instanceof Error ? reason.message : "未收到完整操作结果。");
      setConfirm(false);
    } finally { sending.current = false; if (active.current) setBusy(false); }
  }
  return <>
    <PreviewFacts preview={preview} />
    {preview.review_issues.length ? <div className={styles.notice} role="alert"><h3>需要先处理</h3><ul>{preview.review_issues.map((issue, i) => <li key={i}>{textValue(asRecord(issue).detail)}</li>)}</ul></div> : null}
    {!preview.complete_reference_listing ? <p role="alert">当前影响范围不完整，不能执行合并。</p> : null}
    {failure ? <div className={styles.notice} role="alert"><p>{failure}</p>{uncertain ? <><p>操作结果尚未确认。可刷新下方操作记录，或用原请求重试。不要把网络中断当作合并失败。</p><ActionButton className="button" state={busy ? "pending" : "idle"} onClick={() => void submit()}>重试同一次合并</ActionButton></> : <ActionButton className="button secondary" onClick={refresh}>重新预览并核对</ActionButton>}</div> : null}
    <div className={styles.actions}><ActionButton className="button secondary" disabled={busy || uncertain} onClick={refresh}>重新读取影响</ActionButton><ActionButton className="button" disabled={!eligible || busy || Boolean(failure)} onClick={() => setConfirm(true)}>核对完成，准备合并</ActionButton></div>
    <p>保留人物的基础资料不自动改写。原文件、来源记录、历史公开内容和读者私人笔记保留。合并后检索及公开书目仍需等待处理完成。</p>
    <ConfirmDialog open={confirm} title="确认合并人物" description={`将「${textValue(asRecord(preview.source).preferred_name)}」的无冲突引用归入「${textValue(asRecord(preview.target).preferred_name)}」。请确认这是同一人物，且保留方向正确。`} confirmLabel={busy ? "正在合并…" : "确认是同一人物并合并"} pending={busy} details={["目标人物基础资料保持原值，来源资料不删除。", "若后续有人修改相关资料，撤回可能被阻止。"]} onCancel={() => setConfirm(false)} onConfirm={submit} />
  </>;
}

export function RecordWorkspace({ recordId, credential }: { recordId: string; credential: string }) {
  const resource = useApiResource<PersonMerge>(personApi.record(recordId), credential);
  return <section className={`admin-panel ${styles.panel}`} aria-label="人物合并操作记录"><h2>人物合并操作记录</h2>
    {resource.error ? <Failure message={resource.error} retry={resource.retry} label="重新读取操作" /> : resource.loading ? <p role="status">正在核对操作与当前撤回条件…</p> : resource.data ? <RecordReview key={`${resource.data.id}:${resource.data.status}:${rollbackState(resource.data).fingerprint}`} record={resource.data} credential={credential} refresh={resource.retry} /> : null}
  </section>;
}

function RecordReview({ record, credential, refresh }: { record: PersonMerge; credential: string; refresh: () => void }) {
  const user = useAdminSession();
  const active = useActiveView();
  const sending = useRef(false);
  const [busy, setBusy] = useState(false), [confirm, setConfirm] = useState(false), [failure, setFailure] = useState("");
  const reversal = rollbackState(record);
  async function rollback() {
    if (sending.current || !confirm || !reversal.canRollback) return;
    sending.current = true; setBusy(true); setFailure("");
    try { await rollbackPerson(record.id, { confirmed: true, fingerprint: reversal.fingerprint }, credential, String(user?.id || "")); if (active.current) refresh(); }
    catch (reason) { if (active.current) { setFailure(reason instanceof Error ? reason.message : "未收到撤回结果。"); setConfirm(false); } }
    finally { sending.current = false; if (active.current) setBusy(false); }
  }
  return <>
    <h3 aria-live="polite">{record.status === "rolled_back" ? "本次合并已撤回" : record.status === "applied" ? "人物合并已记录" : "操作状态待核实"}</h3>
    <p>{record.status === "rolled_back" ? "本次移动的引用已恢复。" : "来源记录保留，合并关系已保存。"}公开书目与检索更新需等待处理完成，这里不表示已经公开生效。</p>
    <p>{record.source_name || "来源人物"} → {record.target_name || "保留人物"}</p>
    {record.business_impact ? <BusinessImpact impact={record.business_impact} /> : null}
    <dl className={styles.fields}><div><dt>操作编号</dt><dd>{record.id}</dd></div><div><dt>来源人物</dt><dd><Link prefetch={false} href={personPage(record.source_person_id)}>{record.source_person_id}</Link></dd></div><div><dt>保留人物</dt><dd><Link prefetch={false} href={personPage(record.target_person_id)}>{record.target_person_id}</Link></dd></div><div><dt>执行时间</dt><dd>{new Date(record.created_at).toLocaleString("zh-CN")}</dd></div>{record.rolled_back_at ? <div><dt>撤回时间</dt><dd>{new Date(record.rolled_back_at).toLocaleString("zh-CN")}</dd></div> : null}</dl>
    <details><summary>引用移动及处理记录</summary><Details value={record.moved_counts} /><p>受影响版本 {record.affected_edition_ids.length} 个，合并处理记录 {record.event_ids.length} 条，撤回处理记录 {record.rollback_event_ids.length} 条。</p><Details value={{ edition_ids: record.affected_edition_ids, merge_event_ids: record.event_ids, rollback_event_ids: record.rollback_event_ids }} /></details>
    {record.status !== "rolled_back" ? <><h3>撤回本次合并</h3><p>只恢复本次移动的引用。如果人物或相关编辑内容已有后续修改，系统会拒绝覆盖。</p>{reversal.blockers.length ? <ul role="alert">{reversal.blockers.map((line) => <li key={line}>{line}</li>)}</ul> : null}
      {!reversal.canRollback && !reversal.blockers.length ? <p role="alert">当前撤回资格待核实，请重新读取操作。</p> : null}
      <ActionButton className="button secondary" disabled={busy || !reversal.canRollback || Boolean(failure)} onClick={() => setConfirm(true)}>准备撤回本次合并</ActionButton></> : null}
    {failure ? <div role="alert" className={styles.notice}><p>{failure}</p><p>请重新读取操作，核对撤回是否已经完成及当前条件，不要假定请求失败。</p></div> : null}
    <div className={styles.actions}><ActionButton className="button secondary" disabled={busy} onClick={refresh}>重新读取操作及撤回条件</ActionButton><Link prefetch={false} href={personPage(record.source_person_id)}>返回来源人物</Link></div>
    <ConfirmDialog open={confirm} title="确认撤回本次合并" description="恢复本次迁移的引用与来源人物状态。既有文件和读者私人笔记不受影响，公开内容仍需等待恢复处理。" confirmLabel={busy ? "正在撤回…" : "确认撤回本次合并"} pending={busy} onCancel={() => setConfirm(false)} onConfirm={rollback} />
  </>;
}

export function PersonResolutionWorkspace() {
  const user = useAdminSession();
  const params = useSearchParams();
  const sourceId = params.get("source") || "", targetId = params.get("target") || "", recordId = params.get("record") || "";
  const allowed = hasAdminCapability(user, "can_merge_authority");
  const credential = user ? getServerSessionCredential() : null;
  const valid = [sourceId, targetId, recordId].every((value) => !value || isPersonId(value)) && (!targetId || Boolean(sourceId));
  return <div className={`admin-page ${styles.workspace}`}><PageHeader title="人物查重与整理" description="核对重复作者及学者资料，确认影响范围后再合并。" actions={<Link prefetch={false} href="/admin/knowledge" className="button secondary">返回馆内知识</Link>} />
    {allowed&&user?<PersonMergeRecovery key={user.id} owner={String(user.id)}/>:null}
    {!credential ? <p role="status">等待验证管理会话…</p> : !valid ? <p role="alert">人物或操作编号无效，请从馆内人物列表重新选择。<Link prefetch={false} href={personPage()}>返回列表</Link></p> : <div key={`${user?.id}:${allowed}`} className={styles.content}>{recordId ? allowed ? <RecordWorkspace key={recordId} recordId={recordId} credential={credential} /> : <p role="alert">合并记录与撤回仅向书库所有者开放。</p> : sourceId ? <SourceWorkspace key={sourceId} sourceId={sourceId} targetId={targetId} allowed={allowed} credential={credential} /> : <PersonPicker credential={credential} />}</div>}
  </div>;
}
