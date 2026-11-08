"use client";

import { confirmAction } from "@/lib/ui-dialog";


import { LoadingState } from "@/components/ui/loading-state";
import { createRequestKey } from "../../../lib/request-key";
import Link from "next/link";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Plus, Search, ArrowLeft, ExternalLink, UserRound, MoreHorizontal, ChevronDown, Pencil, X } from "lucide-react";
import { ApiRequestError, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useApiResource } from "@/lib/api/use-api-resource";
import { authorityRequest, type AuthorityValues, type AuthorityVariant, type AuthorityInput, type AuthorityCommand, type AuthorityPreview, type AuthorityReceipt, type AuthorityDirectory, type AuthorityDetail } from "@/lib/api/person-authority.client";
import { asRecord, textValue, personApi, personPage, isPersonId, type PersonDuplicates } from "@/lib/api/person-resolution";
import { Dialog } from "@/components/ui/dialog";
import { BusinessImpact, History, PersonMergeRecovery, PersonPicker, PreviewLoader, RecordWorkspace } from "./person-resolution-workspace";
import styles from "./person-authority.module.css";
import { ScholarTagInput } from "./scholar-tag-input";
import { InlineMediaPicker } from "../curation/inline-media-picker";
import { PersonMaterialsGallery } from "./person-materials-gallery";
import { PersonContributions } from "./person-contributions";
import { SourceEditorFrame, type SourceEditorOptions } from "./source-editor-frame";

const status: Record<string, string> = { draft: "草稿", needs_review: "待核验", verified: "已核验", merged: "已合并", archived: "已归档", rejected: "未采用" };
const labels: Record<string, string> = { biographical_materials: "人物照片与生平资料", key_concerns: "研究领域", preferred_name: "标准名称", original_name: "原文名", birth_year: "生年", death_year: "卒年", biography: "人物简介", preferred_language: "标准名称语言", original_language: "原文名语言", country_region: "国别／地区", authority_note: "内部说明", external_ids: "外部标识", identifier_sources: "标识来源", authority_status: "确认状态", name_variants: "常用异名" };
const blank: AuthorityValues = { biographical_materials: [], key_concerns: [], preferred_name: "", original_name: "", birth_year: null, death_year: null, biography: "", preferred_language: "", original_language: "", country_region: "", authority_note: "", external_ids: {}, identifier_sources: {}, authority_status: "draft" };
const stamp = (value: string) => new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
const storageKey = (actor: string) => `stl-person-authority-request:${actor}`;

export function PersonAuthorityWorkspace() {
  const user = useAdminSession(), params = useSearchParams(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  if (!user) return <LoadingState role="status">正在核对编辑账户…</LoadingState>;
  const source = params.get("source") || "", target = params.get("target") || "", record = params.get("record") || "", create = params.get("new") === "1";
  if (![source, target, record].every(value => !value || isPersonId(value))) return <p role="alert">人物编号无效。<Link href={personPage()}>返回人物资料库</Link></p>;
  return <main className={styles.page} key={`${user.id}:${epoch}`}><nav className={styles.crumb} aria-label="面包屑"><Link href="/admin/knowledge">学者与知识</Link><span>›</span><Link href={personPage()}>人物资料库与身份核对</Link></nav>
    {hasAdminCapability(user,"can_merge_authority")?<PersonMergeRecovery owner={String(user.id)}/>:null}
    {record ? <><h1>人物合并操作记录</h1><RecordWorkspace recordId={record} credential={getServerSessionCredential() ?? ""} /></> : source ? <PersonView key={source} actor={String(user.id)} id={source} target={target} canMerge={hasAdminCapability(user, "can_merge_authority")} /> : create ? <PersonEditor actor={String(user.id)} original={null} /> : <Directory actor={String(user.id)} />}
  </main>;
}

function Directory({ actor }: { actor: string }) {
  const [page, setPage] = useState(1), [search, setSearch] = useState(""), [query, setQuery] = useState(""), [filter, setFilter] = useState("");
  const load = useCallback((path: string, signal: AbortSignal) => authorityRequest<AuthorityDirectory>(actor, path, { signal }), [actor]);
  const resource = usePersistentWorkspace<AuthorityDirectory>(`workspace/?${new URLSearchParams({ page: String(page), search: query, status: filter })}`, actor, undefined, load);
  const data = resource.error ? null : resource.data;
  return <><Recovery actor={actor}/><header className={styles.heading}><div><h1>人物资料库与身份核对</h1></div><Link className={styles.primary} href={`${personPage()}?new=1`}><Plus size={16} />新建人物</Link></header><section className={styles.panel}>
    <form className={styles.toolbar} onSubmit={event => { event.preventDefault(); setPage(1); setQuery(search.trim()); resource.reload(); }}><label><Search size={16} /><input aria-label="查找人物资料名或异名" value={search} onChange={event => setSearch(event.target.value)} maxLength={200} placeholder="查找标准名称、原文名或异名" /></label><select aria-label="人物状态" value={filter} onChange={event => { setFilter(event.target.value); setPage(1); }}><option value="">全部状态</option>{Object.entries(status).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button>查找</button></form>
    {resource.error ? <div role="alert" className={styles.empty}><p>{resource.error}</p><button onClick={() => { setPage(1); resource.reload(); }}>重新读取</button></div> : !data ? <LoadingState role="status">正在读取人物资料…</LoadingState> : <><div className={styles.list}>{data.results.map(row => <Link key={row.id} href={personPage(row.id)}><UserRound size={24} /><div><strong>{row.preferred_name}</strong><p>{row.original_name || "原文名尚未填写"} · {row.birth_year ?? "生年未详"}{row.death_year !== null ? `—${row.death_year}` : ""}</p></div><span>{status[row.authority_status] || "待核对"}</span><span aria-hidden>→</span></Link>)}</div>{!data.results.length ? <div className={styles.empty}><h2>暂无符合条件的人物</h2><p>可以调整筛选，或有依据地建立新的独立人物记录。</p></div> : null}<nav className={styles.pager} aria-label="人物分页"><span>{data.count} 位人物 · {page}/{data.total_pages}</span><button disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><button disabled={page >= data.total_pages} onClick={() => setPage(value => value + 1)}>下一页</button></nav></>}
  </section></>;
}

function PersonView({ actor, id, target, canMerge }: { actor: string; id: string; target: string; canMerge: boolean }) {
  const load = useCallback((path: string, signal: AbortSignal) => authorityRequest<AuthorityDetail>(actor, path, { signal }), [actor]);
  const resource = usePersistentWorkspace<AuthorityDetail>(`${id}/workspace/`, actor, undefined, load);
  const data = resource.error ? null : resource.data;
  if (resource.error) return <div className={styles.empty} role="alert"><p>{resource.error}</p><button onClick={resource.reload}>重新读取</button></div>;
  if (!data) return <LoadingState role="status">正在读取人物资料及关联…</LoadingState>;
  return <PersonEditor key={`${data.id}:${data.version}`} actor={actor} original={data} refresh={resource.reload} target={target} canMerge={canMerge} />;
}

function PersonEditor({ actor, original, refresh, target = "", canMerge = false }: { actor: string; original: AuthorityDetail | null; refresh?: () => void; target?: string; canMerge?: boolean }) {
  const [values, setValues] = useState<AuthorityValues>(original?.values || blank), [variants, setVariants] = useState<AuthorityVariant[]>(original?.variants || []), [reason, setReason] = useState("");
  const [input, setInput] = useState<AuthorityInput | null>(null), [tab, setTab] = useState(target ? "similar" : "basic"), [identifier, setIdentifier] = useState(""), [identifierValue, setIdentifierValue] = useState(""), [notice, setNotice] = useState("");
  const [activeContribution,setActiveContribution]=useState(""),[contributionNotice,setContributionNotice]=useState("");
  const [materialPicker,setMaterialPicker]=useState(false),[materialDirty,setMaterialDirty]=useState(false),[materialNotice,setMaterialNotice]=useState("");
  const [aliasEditor,setAliasEditor]=useState<number|null>(null),[identifierEditor,setIdentifierEditor]=useState<string|null>(null),[addingIdentifier,setAddingIdentifier]=useState(false);
  useUnsavedForm({values,variants,reason,identifier,identifierValue},{values:original?.values||blank,variants:original?.variants||[],reason:"",identifier:"",identifierValue:""});
  const dirty=JSON.stringify(values)!==JSON.stringify(original?.values||blank)||JSON.stringify(variants)!==JSON.stringify(original?.variants||[]);
  const readOnly = original ? !original.can_edit || original.pending_draft : false;
  const set = <K extends keyof AuthorityValues>(key: K, value: AuthorityValues[K]) => setValues(current => ({ ...current, [key]: value }));
  function submit(event: FormEvent) { event.preventDefault(); if (readOnly || activeContribution) return; setInput({ operation: original ? "update" : "create", ...(original ? { person_id: original.id, expected_version: original.version } : {}), values: {...values,key_concerns:(values.key_concerns||[]).map(value=>value.trim()).filter(Boolean)}, variants: variants.map(row => ({ ...(row.id ? { id: row.id } : {}), name: row.name, language: row.language, variant_type: row.variant_type, source_note: row.source_note, is_verified: row.is_verified, displayable: row.displayable })), reason }); }
  async function closeMaterials() { if (materialDirty && !(await confirmAction("放弃尚未保存的图片出处修改吗？"))) return; setMaterialPicker(false); setMaterialDirty(false); }
  function addMaterial(renditionId: string) {
    if (readOnly || input) return;
    const items = values.biographical_materials || [];
    if (items.some(row => row.rendition_id === renditionId)) { setMaterialNotice("这张图片已在当前人物资料中，请编辑原资料说明。"); return; }
    if (items.length >= 100) { setMaterialNotice("人物资料最多100项，请先整理已有资料。"); return; }
    set("biographical_materials", [...items, {id:createRequestKey(),rendition_id:renditionId,caption:""}]);
    setMaterialPicker(false); setMaterialDirty(false);
  }
  function addIdentifier() { const key = identifier.trim(); if (!/^[A-Za-z][A-Za-z0-9_-]{0,40}$/.test(key) || key.includes("__") || !identifierValue.trim()) { setNotice("请填写标识类别和完整值。"); return; } if (Object.hasOwn(values.external_ids, key)) { setNotice("此类别已存在，请编辑原标识。"); return; } set("external_ids", { ...values.external_ids, [key]: identifierValue.trim() }); setIdentifier(""); setIdentifierValue(""); setNotice(""); }
  const tabs = [["basic", "基本信息"], ["works", "作品与贡献"], ["similar", "相似人物与核对"], ["history", "操作历史"]];
  return <><header className={styles.heading}><div><h1>{target ? "合并候选比较" : "人物资料库与身份核对"}</h1></div><div className={styles.save}><span><i/>{dirty?"有未保存修改":original?"正式记录已保存":"新人物 · 尚未保存"}</span>{original?<small>最后保存：{stamp(original.updated_at)} · {status[original.values.authority_status]||"待核对"}</small>:null}<div>{original?.public_url ? <Link href={original.public_url} target="_blank" rel="noreferrer">查看公开学者页 <ExternalLink size={13} /></Link> : null}<button className={styles.primary} type="submit" form="person-authority-form" disabled={readOnly || Boolean(input) || Boolean(activeContribution) || tab !== "basic"}>保存条目信息</button><details data-action-menu className={styles.more} inert={Boolean(activeContribution)}><summary aria-label="更多人物操作"><MoreHorizontal size={16}/></summary><div data-menu-panel><Link href={personPage()}>返回人物库</Link><button type="button" onClick={()=>setTab("history")}>操作历史</button><button type="button" onClick={()=>setTab("similar")}>相似人物核对</button><div className={styles.mobileLanguages}><label>标准名称语言<input maxLength={24} value={values.preferred_language} disabled={readOnly||Boolean(input)} onChange={event=>set("preferred_language",event.target.value)}/></label><label>原文名语言<input maxLength={24} value={values.original_language} disabled={readOnly||Boolean(input)} onChange={event=>set("original_language",event.target.value)}/></label></div></div></details></div></div></header>
    <Recovery actor={actor} />
    {activeContribution?<p className={styles.notice}>正在编辑作品职责。请先保存职责草稿或取消编辑，再修改人物资料。</p>:contributionNotice?<p role="status">{contributionNotice}</p>:null}
    <nav className={styles.tabs} aria-label="人物资料">{tabs.map(([value, label]) => <button key={value} type="button" disabled={Boolean(activeContribution)} aria-current={tab === value ? "page" : undefined} onClick={() => setTab(value)}>{label}</button>)}</nav>
    {original?.pending_draft ? <p className={styles.notice}>关联学者有待处理草稿，请先<Link href={`/admin/scholars/${original.scholar_id}`}>回到学者编辑页</Link>完成版本核对，再修改正式人物资料。</p> : null}
    <form id="person-authority-form" onSubmit={submit} hidden={tab !== "basic"}><fieldset className={styles.editor} disabled={readOnly || Boolean(input)}><div className={styles.column}><section className={styles.panel} inert={Boolean(activeContribution)}><header className={styles.row}><h2>1. 基本信息</h2><button type="button" onClick={()=>document.getElementById("person-preferred-name")?.focus()}><Pencil size={13}/>编辑</button></header><div className={styles.identity}><div className={styles.avatar}>{original?.portrait_url ? <Image src={normalizePublicResourceUrl(original.portrait_url)} width={112} height={144} unoptimized alt={`${values.preferred_name}肖像`} /> : <UserRound size={54} strokeWidth={1} />}<span>{original ? values.preferred_name.slice(0, 4) : "新人物"}</span>{original?.scholar_id ? <Link href={`/admin/scholars/${original.scholar_id}#portrait`}>更换头像</Link> : <small>尚无关联肖像</small>}{original?.portrait_notice ? <small>{original.portrait_notice}</small> : null}</div><div className={styles.fields}>
      <label className={styles.nameField}><span>标准名称 <b aria-hidden>*</b></span><input id="person-preferred-name" required maxLength={240} value={values.preferred_name} onChange={event => set("preferred_name", event.target.value)} /></label><label className={styles.language}>语言<select value={values.preferred_language} onChange={event=>set("preferred_language",event.target.value)}><option value="">未填写</option>{[["zh","中文"],["en","英文"],["de","德文"],["fr","法文"],["ja","日文"],["ru","俄文"],["und","待核对"]].map(([code,label])=><option key={code} value={code}>{label}</option>)}{values.preferred_language&&!["zh","en","de","fr","ja","ru","und"].includes(values.preferred_language)?<option value={values.preferred_language}>{values.preferred_language}</option>:null}</select></label>
      <label className={styles.nameField}>原文名<input maxLength={240} value={values.original_name} onChange={event => set("original_name", event.target.value)} /></label><label className={styles.language}>语言<select value={values.original_language} onChange={event=>set("original_language",event.target.value)}><option value="">未填写</option>{[["zh","中文"],["en","英文"],["de","德文"],["fr","法文"],["ja","日文"],["ru","俄文"],["und","待核对"]].map(([code,label])=><option key={code} value={code}>{label}</option>)}{values.original_language&&!["zh","en","de","fr","ja","ru","und"].includes(values.original_language)?<option value={values.original_language}>{values.original_language}</option>:null}</select></label>
      <div className={styles.aliasStrip}><span>常用异名</span><div>{variants.map((variant,index)=><button key={variant.id||index} type="button" className={styles.aliasChip} onClick={()=>setAliasEditor(aliasEditor===index?null:index)}>{variant.name||"新异名"}<ChevronDown size={11}/></button>)}<button type="button" disabled={variants.length>=200} onClick={()=>{setAliasEditor(variants.length);setVariants(rows=>[...rows,{name:"",language:"und",variant_type:"alias",source_note:"",is_verified:false,displayable:false}]);}}><Plus size={13}/>添加异名</button></div></div>
      {aliasEditor!==null&&variants[aliasEditor]?<div className={styles.aliasEditing}><header><strong>异名与来源</strong><button type="button" aria-label="收起异名编辑" onClick={()=>setAliasEditor(null)}><X size={13}/></button></header><VariantEditor value={variants[aliasEditor]} onChange={value=>setVariants(rows=>rows.map((row,at)=>at===aliasEditor?value:row))} remove={!variants[aliasEditor].id?()=>{setVariants(rows=>rows.filter((_,at)=>at!==aliasEditor));setAliasEditor(null);}:undefined}/></div>:null}
      <div className={styles.lifeDates}><span>生卒年</span><div><input aria-label="生年" type="number" value={values.birth_year ?? ""} onChange={event => set("birth_year", event.target.value === "" ? null : Number(event.target.value))} /><span aria-hidden>—</span><input aria-label="卒年" type="number" value={values.death_year ?? ""} onChange={event => set("death_year", event.target.value === "" ? null : Number(event.target.value))} /></div></div><label>国别／地区<input maxLength={120} value={values.country_region} onChange={event => set("country_region", event.target.value)} /></label><div className={`${styles.full} ${styles.researchFields}`}><ScholarTagInput label="研究领域" addLabel="添加" value={values.key_concerns||[]} onChange={items=>set("key_concerns",items)}/></div><label className={styles.full}>人物简介<textarea rows={4} maxLength={10000} value={values.biography} onChange={event => set("biography", event.target.value)} /></label>
    </div></div></section>
    {original && tab === "basic" ? <section className={styles.panel}><header className={styles.row}><h2>2. 作品与贡献者职责</h2><Link href="/admin/library"><Plus size={13}/>关联作品</Link></header><PersonContributions detail={original} owner={actor} active={activeContribution} onActive={setActiveContribution} onSaved={()=>{setContributionNotice("作品职责草稿已保存，正式发布请在原书目页面核对。");refresh?.();}} disabled={readOnly||dirty||Boolean(input||reason||identifier||identifierValue)}/></section> : null}</div>
    <aside className={styles.column} inert={Boolean(activeContribution)}><section className={styles.panel}><header className={styles.row}><h2>外部标识与来源</h2><button type="button" onClick={()=>setAddingIdentifier(value=>!value)}><Plus size={13}/>添加标识</button></header>{Object.entries(values.external_ids).map(([key,value])=><div className={styles.identifier} key={key}><div className={styles.identifierSummary}><strong>{key}</strong><span>{typeof value==="object"?JSON.stringify(value):String(value)}</span><button type="button" onClick={()=>setIdentifierEditor(identifierEditor===key?null:key)} aria-label={"编辑"+key+"标识"}><Pencil size={12}/></button></div>{original?.identifiers.find(row=>row.scheme===key)?.uri?<a href={original.identifiers.find(row=>row.scheme===key)!.uri!} target="_blank" rel="noreferrer">查看来源 <ExternalLink size={11}/></a>:null}{identifierEditor===key?<><label>标识值<input value={typeof value==="string"||typeof value==="number"?String(value):JSON.stringify(value)} readOnly={typeof value!=="string"&&typeof value!=="number"} onChange={event=>set("external_ids",{...values.external_ids,[key]:event.target.value})}/></label><label>来源依据<textarea rows={2} maxLength={2000} value={values.identifier_sources[key]||""} onChange={event=>set("identifier_sources",{...values.identifier_sources,[key]:event.target.value})}/></label></>:values.identifier_sources[key]?<p>{values.identifier_sources[key]}</p>:null}</div>)}{!Object.keys(values.external_ids).length?<p className={styles.muted}>尚无外部标识，可按已核实来源添加。</p>:null}{addingIdentifier?<div className={styles.identifier}><label>新增类别<input value={identifier} onChange={event=>setIdentifier(event.target.value)} placeholder="如 viaf、isni、wikidata" maxLength={41}/></label><label>标识值<input value={identifierValue} onChange={event=>setIdentifierValue(event.target.value)} maxLength={500}/></label><button type="button" onClick={addIdentifier}>添加标识</button></div>:null}{notice?<p role="alert">{notice}</p>:null}</section><PersonMaterialsGallery items={values.biographical_materials||[]} onChange={items=>set("biographical_materials",items)} onAdd={()=>{setMaterialNotice("");setMaterialPicker(true);}}/><section className={styles.panel}><h2>4. 相关说明 <small>仅内部可见</small></h2><textarea aria-label="内部核对说明" rows={5} maxLength={5000} value={values.authority_note} onChange={event => set("authority_note", event.target.value)} /></section><section className={styles.panel}><h2>保存与影响</h2><label>确认状态<select value={values.authority_status} onChange={event => set("authority_status", event.target.value as AuthorityValues["authority_status"])}><option value="draft">草稿</option><option value="needs_review">待核验</option><option value="verified" disabled={original ? !original.can_verify : false}>已核验</option></select></label><label>本次依据与修改原因<textarea required minLength={2} maxLength={1000} rows={3} value={reason} onChange={event => setReason(event.target.value)} /></label><p className={styles.muted}>先预览变化与关联影响，再确认保存。公开书目更新沿原发布任务处理。</p><button className={styles.primary}>预览变化与影响</button></section></aside></fieldset></form>
    {materialPicker ? <Dialog open className={styles.dialog} aria-labelledby="person-material-title" onRequestClose={closeMaterials}><header className={styles.row}><h2 id="person-material-title">添加人物照片与生平资料</h2><button type="button" onClick={closeMaterials} aria-label="关闭资料选择"><X size={16}/></button></header><p>从已有素材选择或上传，填入后随人物资料预览保存。原图片比例、出处与版本保留。</p><fieldset disabled={readOnly||Boolean(input)}><InlineMediaPicker kind="card" onSelect={addMaterial} onDirtyChange={setMaterialDirty}/></fieldset>{materialNotice?<p role="status">{materialNotice}</p>:null}</Dialog>:null}
    {tab === "works" ? <section className={styles.panel}><h2>作品与贡献者职责</h2>{original ? <><PersonContributions detail={original} owner={actor} active={activeContribution} onActive={setActiveContribution} onSaved={()=>{setContributionNotice("作品职责草稿已保存，正式发布请在原书目页面核对。");refresh?.();}} disabled={readOnly||dirty||Boolean(input||reason||identifier||identifierValue)}/><BusinessImpact impact={original.impact} /></> : <p>保存独立人物后，可从原作品编目关联贡献者。</p>}</section> : null}
    {tab === "similar" ? original ? <SimilarPeople actor={actor} original={original} target={target} canMerge={canMerge} setInput={setInput} onAdopt={(name, id) => { setVariants(rows => [...rows, { name, language: "und", variant_type: "alias", source_note: `来自候选人物记录 ${id} 的标准名称称，仍待核对原文与身份。`, is_verified: false, displayable: false }]); setTab("basic"); }} /> : <p className={styles.empty}>请先保存独立人物，再核对其他人物。</p> : null}
    {tab === "history" && original ? <section className={styles.panel}><h2>人工核对与操作历史</h2>{original.history.length ? <ol className={styles.history}>{original.history.map(row => <li key={row.id}><strong>{row.operation === "decision" ? row.decision === "independent" ? "保持独立身份" : "需要更多证据" : row.operation === "create" ? "建立人物资料" : "更新人物资料"}</strong><time>{stamp(row.created_at)}</time><p>{row.reason}</p><span>{row.fields.map(field => labels[field] || field).join("、")}</span>{row.target_id ? <Link href={personPage(row.target_id)}>查看比较人物</Link> : null}{row.event_ids.length ? <p>已记录 {row.event_ids.length} 项公开更新任务，执行状态以原发布台为准。</p> : null}</li>)}</ol> : <p>尚无规范编辑记录</p>}{canMerge ? <History sourceId={original.id} credential={getServerSessionCredential() ?? ""} /> : null}</section> : null}
    {input ? <CommandPreview actor={actor} input={input} onClose={() => setInput(null)} onSaved={() => { setInput(null); refresh?.(); }} /> : null}
  </>;
}

function materialsSummary(value: unknown) {
  return Array.isArray(value) && value.length ? value.map((row,index)=>`${index+1}. ${asRecord(row).caption||"未填写说明"}`).join("；") : "未添加资料";
}

function VariantEditor({ value, onChange, remove }: { value: AuthorityVariant; onChange: (value: AuthorityVariant) => void; remove?: () => void }) {
  return <fieldset className={styles.variant}><div className={styles.row}><input aria-label="异名" required value={value.name} maxLength={240} onChange={event => onChange({ ...value, name: event.target.value })} /><input aria-label="异名语言" value={value.language} maxLength={24} required onChange={event => onChange({ ...value, language: event.target.value })} /><select aria-label="异名类型" value={value.variant_type} onChange={event => onChange({ ...value, variant_type: event.target.value as AuthorityVariant["variant_type"] })}>{[["alias", "别名"], ["translation", "译名"], ["transliteration", "音译"], ["abbreviation", "简称"], ["historical", "历史名称"]].map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>{remove ? <button type="button" onClick={remove}>取消新增</button> : null}</div><textarea aria-label="异名来源与核验依据" placeholder="记录出处、原文位置或人工核验依据" rows={2} maxLength={5000} value={value.source_note} onChange={event => onChange({ ...value, source_note: event.target.value })} /><div className={styles.checks}><label><input type="checkbox" checked={value.is_verified} onChange={event => onChange({ ...value, is_verified: event.target.checked, displayable: event.target.checked ? value.displayable : false })} />已人工核验</label><label><input type="checkbox" checked={value.displayable} disabled={!value.is_verified} onChange={event => onChange({ ...value, displayable: event.target.checked })} />允许公开显示</label><small>{value.source_kind ? `原来源：${value.source_kind}` : "新异名 · 尚未保存"}</small></div></fieldset>;
}

function SimilarPeople({ actor, original, target, canMerge, setInput, onAdopt }: { actor: string; original: AuthorityDetail; target: string; canMerge: boolean; setInput: (input: AuthorityInput) => void; onAdopt: (name: string, id: string) => void }) {
  const resource = useApiResource<PersonDuplicates>(personApi.duplicates(original.id), getServerSessionCredential(), actor);
  const [reason, setReason] = useState(""), [failure, setFailure] = useState(""), [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => { const request = new AbortController(); controller.current = request; return () => request.abort(); }, []);
  async function decision(id: string, kind: "independent" | "needs_evidence") {
    const request = controller.current; if (!request || busy || request.signal.aborted) return;
    if (reason.trim().length < 2) { setFailure("请填写本次判断依据。"); return; }
    setBusy(true); setFailure("");
    try { const other = await authorityRequest<AuthorityDetail>(actor, `${id}/workspace/`, { signal: request.signal }); if (!request.signal.aborted) setInput({ operation: "decision", person_id: original.id, expected_version: original.version, target_id: id, target_version: other.version, decision: kind, reason }); }
    catch (error) { if (!request.signal.aborted) setFailure(error instanceof Error ? error.message : "读取比较人物失败。"); }
    finally { if (!request.signal.aborted) setBusy(false); }
  }
  return <><section className={styles.panel}><div className={styles.row}><h2>相似人物候选</h2><Link href={`${personPage()}?new=1`}>新建人物，保持独立</Link></div><p>以下是实际名称或标识匹配线索，不代表同一人物，也不计算没有依据的相似百分比。</p>{resource.error ? <p role="alert">{resource.error}<button onClick={resource.retry}>重新读取</button></p> : resource.loading ? <LoadingState role="status">正在读取候选…</LoadingState> : <>{resource.data?.results.length ? <><label>本次判断依据<textarea value={reason} onChange={event => setReason(event.target.value)} maxLength={1000} rows={2} /></label><div className={styles.candidates}>{resource.data.results.map(row => <article key={row.person.id}><div><h3>{row.person.preferred_name}</h3><p>{row.person.original_name} · {row.person.birth_year ?? "生年未详"}{row.person.death_year ? `—${row.person.death_year}` : ""}</p><p>{row.matches.map(match => `${asRecord(match).kind === "name" ? "名称" : "外部标识"}：${textValue(asRecord(match).values)}`).join("；")}</p>{row.identity_conflicts.length ? <p className={styles.warning}>存在 {row.identity_conflicts.length} 项身份差异，需要进一步核对。</p> : null}</div><div className={styles.actions}><Link href={personPage(original.id, row.person.id)}>比较与预览</Link><button disabled={busy || !original.can_edit || original.pending_draft} onClick={() => onAdopt(row.person.preferred_name, row.person.id)}>作为待核验异名</button><button disabled={busy} onClick={() => void decision(row.person.id, "independent")}>保持独立</button><button disabled={busy} onClick={() => void decision(row.person.id, "needs_evidence")}>需要更多证据</button></div></article>)}</div></> : <p>暂未发现名称或标识匹配的人物；这不能证明馆内没有重复身份。</p>}{resource.data?.has_more ? <p>候选超过20条，请在人物库补充名称缩小范围。</p> : null}</>}{failure ? <p role="alert">{failure}</p> : null}</section><details className={styles.panel}><summary>查找其他人物进行比较</summary><PersonPicker sourceId={original.id} credential={getServerSessionCredential() ?? ""} /></details>{target ? canMerge ? <PreviewLoader sourceId={original.id} targetId={target} credential={getServerSessionCredential() ?? ""} /> : <p className={styles.notice}>合并影响预览及实际合并需要馆长权限。当前账户仍可记录人工核对判断。</p> : null}</>;
}

function Recovery({ actor, onResolved }: { actor: string; onResolved?: (result: AuthorityReceipt) => void }) {
  const router = useRouter(), [id, setId] = useState(""), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => { const request = new AbortController(); controller.current = request; const read = () => { if (request.signal.aborted) return; try { setId(sessionStorage.getItem(storageKey(actor)) || ""); } catch { setMessage("原请求标识暂不可读，请先核对操作记录。"); } }; queueMicrotask(read); window.addEventListener("stl-person-request", read); return () => { request.abort(); window.removeEventListener("stl-person-request", read); }; }, [actor]);
  async function lookup(cancel = false) {
    const request = controller.current; if (!id || busy || !request || request.signal.aborted) return;
    setBusy(true); setMessage("");
    try {
      const result = await authorityRequest<AuthorityReceipt>(actor, `workspace/receipts/${id}/`, { signal: request.signal, ...(cancel ? {method:"POST",body:JSON.stringify({action:"cancel_pending"})} : {}) });
      if(result.request_id!==id || !["applied","cancelled"].includes(result.state) || result.state==="applied"&&!result.person_id)throw Error("操作结果与原请求不一致，请保留请求编号并核对记录。");
      sessionStorage.removeItem(storageKey(actor)); window.dispatchEvent(new Event("stl-person-request"));
      if (!request.signal.aborted) { setId(""); if (onResolved) onResolved(result); else if(result.person_id){ router.push(personPage(result.person_id)); router.refresh(); } else setMessage("尚未执行的原保存已停止，可以继续编辑。"); }
    } catch (error) { if (!request.signal.aborted) setMessage(error instanceof Error ? error.message : "暂未收到原请求结果。"); }
    finally { if (!request.signal.aborted) setBusy(false); }
  }
  if (!id && !message) return null;
  return <aside className={styles.notice}><strong>{id?"有一次保存需要核对结果":"保存结果核对"}</strong>{id?<><p>这里只保留请求编号，没有保存表单正文。查询不会再次保存；停止只阻止未执行的请求，已保存的内容会返回真实操作结果。</p><div className={styles.actions}><button type="button" disabled={busy} onClick={() => void lookup()}>核对原请求</button><button type="button" disabled={busy} onClick={() => void lookup(true)}>停止未执行的保存</button></div></>:null}{message ? <p role="status">{message}</p> : null}</aside>;
}

function CommandPreview({ actor, input, onClose, onSaved, stayOnPage = false }: { actor: string; input: AuthorityInput; onClose: () => void; onSaved: () => void; stayOnPage?: boolean }) {
  const router = useRouter(), [preview, setPreview] = useState<AuthorityPreview | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false);
  const pending = useRef<AuthorityCommand | null>(null), sending = useRef(false), controller = useRef<AbortController | null>(null);
  useEffect(() => { const request = new AbortController(); controller.current = request; void authorityRequest<AuthorityPreview>(actor, "workspace/preview/", { method: "POST", body: JSON.stringify(input), signal: request.signal }).then(value => { if (!request.signal.aborted) setPreview(value); }, reason => { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "预览失败。"); }); return () => request.abort(); }, [actor, input]);
  async function save() {
    const request = controller.current; if (!preview || sending.current || !request || request.signal.aborted) return;
    sending.current = true; setBusy(true); setError("");
    try {
      if (!pending.current) { const old = sessionStorage.getItem(storageKey(actor)); if (old) throw Error("上次保存尚未核对，请先关闭此预览并读取原请求结果。"); pending.current = { ...input, preview_hash: preview.preview_hash, confirmed: true, request_id: createRequestKey() }; sessionStorage.setItem(storageKey(actor), pending.current.request_id); window.dispatchEvent(new Event("stl-person-request")); }
      const result = await authorityRequest<AuthorityReceipt>(actor, "workspace/command/", { method: "POST", body: JSON.stringify(pending.current), signal: request.signal });
      if (result.request_id !== pending.current.request_id || !["applied","cancelled"].includes(result.state) || result.state==="applied"&&!result.person_id) throw Error("操作结果与原请求不一致，请核对操作记录。");
      sessionStorage.removeItem(storageKey(actor)); window.dispatchEvent(new Event("stl-person-request")); if (!request.signal.aborted) { if(result.state==="cancelled"){pending.current=null;setUncertain(false);setError("此请求已停止，输入仍保留。请返回修改后重新预览。");return;} onSaved(); if (!stayOnPage && result.person_id) { router.push(personPage(result.person_id)); router.refresh(); } }
    } catch (reason) {
      if (request.signal.aborted) return;
      const rejected = reason instanceof ApiRequestError && !(reason instanceof PrivateOwnerVerificationError) && [400, 401, 403, 404, 409].includes(reason.status);
      if (rejected && pending.current) { sessionStorage.removeItem(storageKey(actor)); window.dispatchEvent(new Event("stl-person-request")); pending.current = null; }
      setUncertain(!rejected && Boolean(pending.current)); setError(reason instanceof Error ? reason.message : "未收到保存结果，请核对原请求。");
    } finally { sending.current = false; if (!request.signal.aborted) setBusy(false); }
  }
  return <Dialog open className={styles.dialog} aria-labelledby="authority-preview-title" onRequestClose={busy ? undefined : onClose}><h2 id="authority-preview-title">核对变化与影响</h2>{preview ? <><p>{input.operation === "decision" ? `记录判断：${input.decision === "independent" ? "保持独立身份" : "需要更多证据"}` : `变更 ${preview.fields.map(field => labels[field] || field).join("、")}`}</p><p>关联 {preview.edition_count} 个作品版本、{preview.profile_count} 个学者档案。</p>{preview.public_update ? <p className={styles.notice}>这次确认会更新正式人物资料，并为关联公开书目记录发布任务。学者页的既有发布版本仍由原学者编辑流程管理。</p> : <p>本次保存不会自动发布学者页或合并人物。</p>}{preview.fields.some(field=>field==="key_concerns"||field==="biographical_materials")?<p>研究领域与生平资料沿同一学者档案保存。资料关联和已有公开档案的更改先存为草稿，需在原学者编辑页核对并发布；尚无档案时从当前人物建立草稿，不另建人物。</p>:null}<p>依据：{preview.reason}</p>{preview.before && preview.after ? <dl className={styles.changes}>{preview.fields.filter(field => field !== "name_variants").map(field => <div key={field}><dt>{labels[field] || field}</dt><dd>{field==="biographical_materials"?materialsSummary(asRecord(preview.before)[field]):textValue(asRecord(preview.before)[field])} → {field==="biographical_materials"?materialsSummary(asRecord(preview.after)[field]):textValue(asRecord(preview.after)[field])}</dd></div>)}</dl> : null}{preview.variant_changes.length ? <section className={styles.variantChanges}><h3>本次异名变化</h3>{preview.variant_changes.map((change,index)=><article key={index}><strong>{change.before ? `${change.before.name} → ${change.after.name}` : `新增：${change.after.name}`}</strong><p>{change.before ? `${variantSummary(change.before)} → ` : ""}{variantSummary(change.after)}</p>{change.before?.source_note ? <p>原依据：{change.before.source_note}</p> : null}<p>修改后依据：{change.after.source_note || "尚未填写"}</p></article>)}</section> : null}</> : !error ? <LoadingState role="status">正在核对当前记录与影响…</LoadingState> : null}{error ? <p role="alert">{error}</p> : null}<div className={styles.actions}><button disabled={busy} onClick={onClose}>{uncertain ? "关闭并保留原请求" : "返回修改"}</button><button className={styles.primary} disabled={!preview || busy || Boolean(error && !uncertain)} onClick={() => void save()}>{busy ? "正在保存…" : uncertain ? "重试同一次保存" : "确认并保存"}</button></div></Dialog>;
}

function variantSummary(value: AuthorityVariant) {
  const names: Record<string,string> = {alias:"别名",translation:"译名",abbreviation:"简称",historical:"历史名称",transliteration:"音译"};
  return `${value.language} · ${names[value.variant_type] || value.variant_type} · ${value.is_verified ? "已人工核验" : "未核验"} · ${value.displayable ? "允许公开显示" : "不公开显示"}`;
}

/** Inline variant maintenance reuses the complete authority preview and receipt. */
export function PersonAliasesDialog({ owner, personId, onClose, onSaved, ...options }: { owner: string; personId: string; onClose: () => void; onSaved: () => void } & SourceEditorOptions) {
  const load = useCallback((path: string, signal: AbortSignal) => authorityRequest<AuthorityDetail>(owner, path, { signal }), [owner]);
  const resource = usePersistentWorkspace<AuthorityDetail>(`${personId}/workspace/`, owner, undefined, load);
  if (!resource.data) return <SourceEditorFrame embedded={options.embedded} onClose={onClose} label="人物异名来源"><h2>人物异名来源</h2><p role={resource.error ? "alert" : "status"}>{resource.error || "正在读取馆内人物记录…"}</p><button type="button" onClick={resource.reload}>重新读取</button><button type="button" onClick={onClose}>关闭</button></SourceEditorFrame>;
  return <AliasesEditor {...options} key={`${owner}:${resource.data.id}`} actor={owner} source={resource.data} readError={resource.error} onClose={onClose} onSaved={onSaved} reload={resource.reload} />;
}

function AliasesEditor({ actor, source, readError, onClose, onSaved, reload, embedded, formId, onState }: { actor: string; source: AuthorityDetail; readError: string; onClose: () => void; onSaved: () => void; reload: () => void } & SourceEditorOptions) {
  // Focus revalidation may reveal a competing revision; it never replaces this draft.
  const [original, setOriginal] = useState(source);
  const [variants, setVariants] = useState(original.variants), [reason, setReason] = useState("");
  const [input, setInput] = useState<AuthorityInput | null>(null), [notice, setNotice] = useState(""), [refreshing, setRefreshing] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(()=>{const active=new AbortController();request.current=active;return()=>active.abort();},[]);
  const dirty = useUnsavedForm({variants, reason}, {variants:original.variants, reason:""});
  const needsPublisher = source.values.authority_status === "verified" && !source.can_verify;
  const readOnly = !source.can_edit || source.pending_draft || needsPublisher || Boolean(input) || refreshing;
  const saveable=!readOnly&&dirty&&source.version===original.version;
  useEffect(()=>{onState?.({dirty,busy:Boolean(input)||refreshing,saveable});},[onState,dirty,input,refreshing,saveable]);
  async function close() { if (!input && !refreshing && (!dirty || (await confirmAction("异名修改尚未保存，关闭会放弃当前输入。是否关闭？")))) onClose(); }
  async function refreshSource() {
    const active=request.current;
    if(!active || active.signal.aborted || refreshing || dirty && !(await confirmAction("重新读取会放弃当前未保存输入。是否继续？")))return;
    setRefreshing(true);
    try {
      const next=await authorityRequest<AuthorityDetail>(actor,`${original.id}/workspace/`,{signal:active.signal});
      if(!active.signal.aborted){setOriginal(next);setVariants(next.variants);setReason("");setNotice("");reload();}
    } catch(error){if(!active.signal.aborted){setNotice(error instanceof Error?error.message:"来源暂不可读，当前输入仍保留。");reload();}}
    finally{if(!active.signal.aborted)setRefreshing(false);}
  }
  function review(event: FormEvent) {
    event.preventDefault(); if (readOnly) return;
    setInput({operation:"update",person_id:original.id,expected_version:original.version,values:original.values,reason,variants:variants.map(row=>({...(row.id?{id:row.id}:{}),name:row.name,language:row.language,variant_type:row.variant_type,source_note:row.source_note,is_verified:row.is_verified,displayable:row.displayable}))});
  }
  return <SourceEditorFrame embedded={embedded} label="人物异名来源" onClose={close}><header className={styles.row}><h2 id="inline-alias-title">{original.values.preferred_name} · 人名与异名</h2><button type="button" disabled={Boolean(input)||refreshing} onClick={close}>关闭</button></header><p>编辑人物别名和核对依据。检索词按已保存的核验和公开状态同步，原人物记录保留。</p>
    <Recovery actor={actor} onResolved={result=>{setNotice(result.state==="cancelled"?"尚未执行的原保存已停止，本次输入仍保留。":result.person_id===original.id?"原人物操作已确认，重新读取后可继续维护。":"已确认此前另一人物的保存，本次输入仍保留。");onSaved();reload();}}/>
    {readError ? <p role="alert">{readError}；当前输入仍保留。</p> : null}{source.version!==original.version ? <p role="alert" className={styles.notice}>来源已有新版本，当前输入仍保留。请先核对新记录，不能覆盖他人的修改。</p> : null}
    {notice ? <p role="status" className={styles.notice}>{notice}</p> : null}{source.pending_draft ? <p className={styles.notice}>关联学者仍有草稿，须先在<Link href={`/admin/scholars/${source.scholar_id}`}>学者编辑页</Link>完成版本核对，再更新正式人物异名。</p> : null}{!source.can_edit || needsPublisher ? <p className={styles.notice}>{needsPublisher ? "此人物已正式核验，修改需规范发布权限。" : "当前账户可查看来源，不能修改人物资料。"}</p> : null}
    <form id={formId} onSubmit={review}><fieldset className={styles.aliasFields} disabled={readOnly}>{variants.map((variant,index)=><VariantEditor key={variant.id||index} value={variant} onChange={value=>setVariants(rows=>rows.map((row,at)=>at===index?value:row))} remove={!variant.id?()=>setVariants(rows=>rows.filter((_,at)=>at!==index)):undefined}/>)}{!variants.length ? <p>尚无异名。请按真实出处添加，不能依据检索相似度推定同一人物。</p> : null}<button type="button" disabled={variants.length>=200} onClick={()=>setVariants(rows=>[...rows,{name:"",language:"und",variant_type:"alias",source_note:"",is_verified:false,displayable:false}])}>添加异名</button><label className={styles.aliasReason}>本次修改依据<textarea value={reason} required minLength={2} maxLength={1000} rows={3} onChange={event=>setReason(event.target.value)} /></label><p className={styles.muted}>原异名记录不可删除。取消人工核验后停止用于公开匹配，后台仍保留来源。新增或修改已核验异名需要规范发布权限。</p><div className={styles.actions}><button className={styles.primary} type="submit" disabled={!dirty||source.version!==original.version}>预览变化与影响</button></div></fieldset></form>
    <button type="button" disabled={Boolean(input)||refreshing} onClick={()=>void refreshSource()}>{refreshing?"正在读取…":"重新读取来源"}</button>
    {input ? <CommandPreview actor={actor} input={input} stayOnPage onClose={()=>setInput(null)} onSaved={()=>{setInput(null);onSaved();onClose();}}/> : null}
  </SourceEditorFrame>;
}
