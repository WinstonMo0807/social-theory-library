"use client";

import { writeClipboardText } from "@/lib/clipboard";
import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { CheckCircle2, Copy, FileText, Info, Mail, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Dialog } from "../ui/dialog";
import { ConfirmDialog } from "../confirm-dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { sharingRequest, shareLink, sectionLabels, type ShareSection, type ShareSelection, type SharePreview,
  type SharePreviewInput, type ShareCreateInput, type ShareReceipt, type ShareRecoveryResult, type GroupDirectory, type GroupDetail, type ShareNotifyResult, type ShareSourcesPage } from "@/lib/api/sharing.client";
import { SharingAccount, SharingPagination, SharingCover, SharedSummary, useSharingAction } from "./sharing-common";
import styles from "./sharing.module.css";

type SourceKind = "research" | "booklist";
type SourcePage = ShareSourcesPage;
type Selections=Record<ShareSection,string[]>;
type ChosenSource={kind:SourceKind;id:string;title:string;version:string;values:Selections};
const emptySelections=():Selections=>({questions:[],materials:[],notes:[]});
type Prepared = { input: SharePreviewInput; output: SharePreview };

export function ShareComposer({ sourceId = "", sourceKind = "research" }: { sourceId?: string; sourceKind?: SourceKind }) {
  return <SharingAccount next="/account/sharing/new" composer>{owner => <Composer owner={owner} initialId={sourceId} initialKind={sourceKind} />}</SharingAccount>;
}

function Composer({ owner, initialId, initialKind }: { owner: string; initialId: string; initialKind: SourceKind }) {
  const [kind, setKind] = useState<SourceKind>(initialKind), [id, setId] = useState(initialId), [sourcePage, setSourcePage] = useState(1);
  const [section, setSection] = useState<ShareSection>("materials"), [page, setPage] = useState(1), [phase, setPhase] = useState(1),[choicesOpen,setChoicesOpen]=useState(false);
  const [objects,setObjects]=useState<ChosenSource[]>(()=>initialId?[{kind:initialKind,id:initialId,title:"从原位置选入的对象",version:"",values:emptySelections()}]:[]);
  const activeObject=objects.find(row=>row.kind===kind&&row.id===id);
  const selected=activeObject?.values||emptySelections();
  const sourceVersion=String(activeObject?.version||"");
  const [destination, setDestination] = useState<"public" | "proposal" | "campus" | "team" | "">("");
  const [groupId, setGroupId] = useState(""), [groupPage, setGroupPage] = useState(1), [members, setMembers] = useState<string[]>([]);
  const [message, setMessage] = useState(""), [expires, setExpires] = useState(30), [prepared, setPrepared] = useState<Prepared | null>(null), [confirmed, setConfirmed] = useState(false);
  const [receipt, setReceipt] = useState<ShareReceipt | null>(null), [recovery, setRecovery] = useState<string | null>(null), [retryReady, setRetryReady] = useState(false);
  const [stopOpen, setStopOpen] = useState(false), [manual, setManual] = useState("");
  const [storageReady,setStorageReady]=useState(false),[storageError,setStorageError]=useState("");
  const pending = useRef<ShareCreateInput | null>(null), action = useSharingAction(owner), setActionMessage = action.setMessage;
  const storageKey = `stl-share-request:${owner}`;
  const loadSources = useCallback((path: string, signal: AbortSignal) => sharingRequest<SourcePage>(owner, path, { signal }), [owner]);
  const sources = usePersistentWorkspace<SourcePage>(`/reading/shares/sources/?source_kind=${kind}&page=${sourcePage}`, owner, undefined, loadSources);
  const loadChoices = useCallback((_: string, signal: AbortSignal) => sharingRequest<ShareSelection>(owner, "/reading/shares/selection/", {
    method: "POST", signal, body: JSON.stringify({ source_kind: kind, source_id: id, section, page, ...(sourceVersion?{expected_version:sourceVersion}:{}) }) }), [owner, kind, id, section, page, sourceVersion]);
  const choices = usePersistentWorkspace<ShareSelection>(id ? `share-selection:${kind}:${id}:${section}:${page}:${sourceVersion}` : "", owner, undefined, loadChoices);
  const data = choices.error ? null : choices.data;
  const loadGroups = useCallback((path: string, signal: AbortSignal) => sharingRequest<GroupDirectory>(owner, path, { signal }), [owner]);
  const groups = usePersistentWorkspace<GroupDirectory>(destination === "campus" || destination === "team" ? `/reading/groups/?page=${groupPage}&kind=${destination}` : "", owner, undefined, loadGroups);
  const loadGroup = useCallback((path: string, signal: AbortSignal) => sharingRequest<GroupDetail>(owner, path, { signal }), [owner]);
  const group = usePersistentWorkspace<GroupDetail>(groupId ? `/reading/groups/${groupId}/` : "", owner, undefined, loadGroup);
  const groupData = group.error ? null : group.data;
  const totals={questions:0,materials:0,notes:0};
  objects.forEach(object=>(Object.keys(totals) as ShareSection[]).forEach(key=>{totals[key]+=object.values[key].length;}));
  const selectedCount=totals.questions+totals.materials+totals.notes;
  const blocked = action.busy || Boolean(recovery) || Boolean(receipt) || !storageReady || !!storageError;
  useUnsavedForm(Boolean(recovery)||(!receipt&&(objects.length>0||!!message)),false);
  useEffect(() => {
    const restore = () => {
      try {
        const requestId = sessionStorage.getItem(storageKey);
        if(requestId&&!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId))throw Error("恢复标识格式异常，请保留本页并核对分享记录，未开放新提交。");
        if(requestId)setRecovery(requestId);
        setStorageReady(true);setStorageError("");
      } catch(reason) { setStorageError(reason instanceof Error?reason.message:"恢复标识无法读取，请先核对分享记录。"); }
    };
    restore(); window.addEventListener("storage", restore);
    return () => window.removeEventListener("storage", restore);
  }, [storageKey]);
  function remember(value: string | null) {
    if(value)sessionStorage.setItem(storageKey,value);else sessionStorage.removeItem(storageKey);
    setRecovery(value);
  }
  function invalidate() { setPrepared(null); setConfirmed(false); }
  function chooseSource(nextKind:SourceKind,nextId=""){
    setKind(nextKind);setId(nextId);setPage(1);
  }
  function toggleSource(row:{id:string;title:string;version:string},checked:boolean){
    if(blocked)return;
    if(checked&&objects.length>=5){setActionMessage("一次最多组合5个对象，请先移除不需要的对象。");return;}
    setObjects(value=>checked?(value.some(item=>item.kind===kind&&item.id===row.id)||value.length>=5?value:[...value,{...row,kind,values:emptySelections()}]):value.filter(item=>item.kind!==kind||item.id!==row.id));
    if(checked)chooseSource(kind,row.id);
    invalidate();
  }
  function removeSource(object:ChosenSource){
    setObjects(value=>value.filter(row=>row.kind!==object.kind||row.id!==object.id));invalidate();
  }
  function setSelected(update:(value:Selections)=>Selections){
    if(!data||blocked)return;
    if(!activeObject&&objects.length>=5){setActionMessage("一次最多选择5个对象，请先移除一个。");return;}
    setObjects(value=>{
      const old=value.find(row=>row.kind===kind&&row.id===id);
      const original=old?.values||emptySelections();
      const next={kind,id,title:data.source.title,version:old?.version||data.source.version,values:update({questions:[...original.questions],materials:[...original.materials],notes:[...original.notes]})};
      return old?value.map(row=>row===old?next:row):[...value,next];
    });invalidate();
  }
  function input():SharePreviewInput|null{
    if(!objects.length||objects.some(row=>!row.version||!Object.values(row.values).some(values=>values.length)))return null;
    const scopes=objects.map(row=>({source_kind:row.kind,source_id:row.id,expected_version:row.version,...row.values}));
    return {...scopes[0],...(scopes.length>1?{additional_sources:scopes.slice(1)}:{}),
      destination:destination==="campus"||destination==="team"?"group":destination||"public",
      ...(destination==="campus"||destination==="team"?{group_id:groupId,group_revision:groupData?.group.revision,member_ids:members}:{}),message,expires_days:expires};
  }
  const currentInput = input();
  const ready = Boolean(prepared && currentInput && JSON.stringify(currentInput) === JSON.stringify(prepared.input) && destination);
  function preview(nextPhase = 2) {
    if (!currentInput) return;
    const captured = currentInput;
    void action.run(signal => sharingRequest<SharePreview>(owner, "/reading/shares/preview/", { method: "POST", body: JSON.stringify(captured), signal }), output => {
      setPrepared({ input: captured, output }); setConfirmed(false); setPhase(nextPhase);
    });
  }
  function finish(value: ShareReceipt) {
    if(value.owner_id!==owner||(pending.current&&value.request_id!==pending.current.request_id)||(recovery&&value.request_id!==recovery))throw Error("提交结果与当前账户或原编号不一致，请保留记录。");
    remember(null);pending.current = null; setRetryReady(false); setReceipt(value); setPhase(4);
    setActionMessage(value.share.revoked ? "原提交后来已撤回，旧请求不会重新建立授权。" : "已提交，请核对接收范围与有效期。");
  }
  function send(original?: ShareCreateInput) {
    if (pending.current && original !== pending.current) return;
    if (!original && (!prepared || !ready || !confirmed)) return;
    const body: ShareCreateInput = original || { ...prepared!.input, request_id: createRequestKey(), preview_hash: prepared!.output.preview_hash, confirmed: true };
    try{remember(body.request_id);}catch{setStorageError("浏览器不能保存原提交编号，尚未发送请求。请恢复存储后重新读取本页。");return;}
    pending.current = body; setRetryReady(true);
    void action.run(signal => sharingRequest<ShareReceipt>(owner, "/reading/shares/", { method: "POST", body: JSON.stringify(body), signal }), finish, reason => {
      setConfirmed(false);
      setActionMessage(`${reason instanceof Error?reason.message:"提交尚未确认。"} 原编号已保留；请先查询结果，或取消尚未执行的原提交。`);
    });
  }
  function stopPending(){
    if(!recovery)return;
    const expected=recovery;
    void action.run(signal=>sharingRequest<ShareRecoveryResult>(owner,"/reading/shares/receipt/",{method:"POST",signal,body:JSON.stringify({request_id:expected,action:"cancel_pending"})}),value=>{
      if(value.owner_id!==owner||value.request_id!==expected)throw Error("取消操作结果与当前账户或原编号不一致，请保留记录。");
      if(value.state==="applied"){
        if(!value.receipt||value.receipt.request_id!==expected||value.receipt.owner_id!==owner)throw Error("原提交结果不完整，请保留编号。");
        finish(value.receipt);setActionMessage("原分享已建立，停止待提交请求不会撤回它；可进入内容与授权查看，必要时另行撤回。");
      }else if(value.state==="cancelled"){
        remember(null);pending.current=null;setRetryReady(false);invalidate();setActionMessage("已在服务器取消原提交，迟到请求不会建立分享。内容选择保留，重新预览确认后才可发起新提交。");
      }else throw Error("原提交状态无法确认，请保留编号。");
      setStopOpen(false);
    });
  }
  function copyLink() {
    if (!receipt) return;
    void action.run(async signal => {
      const current = await sharingRequest<ShareReceipt>(owner, `/reading/shares/receipt/?request_id=${receipt.request_id}`, { signal });
      if (!current.token) throw Error("此分享的公开链接已经到期或撤回。");
      return shareLink(current.share.id, current.token);
    }, link => { void writeClipboardText(link).then(() => { setManual(""); setActionMessage("分享链接已复制。持有链接的人可查看已确认的内容摘要。"); }).catch(() => setManual(link)); });
  }
  if (action.invalid) return <div className={styles.empty} role="alert"><p>账户或权限需要重新核对，已隐藏原账户内容。</p><button onClick={() => window.location.reload()}>重新核对账户</button></div>;
  return <>
    <header className={styles.heading}><div><h1>分享或提交策划的内容范围</h1><p>选择要分享或提交的内容，预览将公开的范围，明确目的地或接收范围。默认不包含您的私人正文及 PDF 原件。</p></div><aside className={styles.scopeNote}><Info size={17}/><div><strong>说明</strong><p>仅分享您选择的内容。不会包含您的私人正文、未勾选的个人笔记及 PDF 原件。来源文献的全文需由接收方通过本馆访问或自行获取，状态为“尚未核实”。</p><small>本次主动勾选的本人笔记会列入范围。</small></div></aside></header>
    {action.message ? <p className={styles.feedback} role="status">{action.message}</p> : null}
    {storageError?<p className={styles.feedback} role="alert">{storageError} <Link href="/account/sharing">查看本人分享记录</Link></p>:null}
    {recovery ? <section className={styles.recovery}><h2>核对原提交结果</h2><p>原编号：{recovery}。尚未确认时不能另起提交，刷新后仍可查询；取消只阻止尚未执行的请求。</p><div className={styles.actions}><button disabled={action.busy} onClick={() => void action.run(signal => sharingRequest<ShareReceipt>(owner, `/reading/shares/receipt/?request_id=${recovery}`, { signal }), finish)}>查询原结果</button>{retryReady?<button disabled={action.busy} onClick={()=>{if(pending.current)send(pending.current);}}>重试原提交</button>:null}<button disabled={action.busy} onClick={()=>setStopOpen(true)}>取消尚未执行的提交</button><Link href="/account/sharing">查看分享记录</Link></div></section>:null}
    <ConfirmDialog open={stopOpen} title="取消尚未执行的分享提交" description="服务器先核对原编号。已经建立的分享会返回原操作结果，不会被撤回；尚未执行的请求会登记取消，迟到后也不会建立授权。" confirmLabel="核对并取消待提交请求" pending={action.busy} onCancel={()=>setStopOpen(false)} onConfirm={stopPending}/>

    <nav className={styles.mobileSteps} aria-label="分享步骤">{["选择内容", "预览", "选择目的地", "确认提交"].map((label, index) => <button key={label} aria-current={phase === index + 1 ? "step" : undefined} disabled={action.busy} onClick={() => setPhase(index + 1)}><span>{index + 1}</span>{label}</button>)}</nav>
    <div className={styles.steps} data-phase={phase}>
      <section className={styles.step}><h2><span>1</span><b className={styles.desktopStepTitle}>选择当前研究或书单对象</b><b className={styles.mobileStepTitle}>选择对象</b></h2><div className={styles.stepBody}>
        <div className={styles.tabs}>{(["research", "booklist"] as const).map(value => <button key={value} aria-pressed={kind === value} disabled={blocked} onClick={() => { chooseSource(value); setSourcePage(1); }}>{value === "research" ? "我的研究" : "我的书单"}</button>)}</div>
        {sources.error ? <p role="alert">{sources.error}<button onClick={sources.reload}>重新读取</button></p> : sources.data ? <><div className={styles.objectList}>{sources.data.results.map(row=>{const chosen=objects.some(item=>item.kind===kind&&item.id===row.id);return <div className={styles.sourceRow} key={row.id}><input type="checkbox" aria-label={`选择${row.title}`} checked={chosen} disabled={blocked||!chosen&&objects.length>=5} onChange={event=>toggleSource(row,event.target.checked)}/><button type="button" aria-pressed={id===row.id} disabled={blocked} onClick={()=>chooseSource(kind,row.id)}><SharingCover work={row.first_material}/><span><strong>{row.title}</strong>{row.first_material?<small>首条选材：{row.first_material.title}{row.first_material.authors?.length?` · ${row.first_material.authors.join("、")}`:""}{row.first_material.year?` · ${row.first_material.year} 年`:""}</small>:<small>{row.material_count?"首条选材当前无公开书目信息":"尚未添加选材"}</small>}<small>共 {row.material_count} 条选材</small><small>{chosen?"已加入范围 · 查看并勾选具体内容":"预览分享内容"}</small></span></button></div>;})}</div>{!sources.data.results.length ? <p className={styles.muted}>没有可选择的{kind === "research" ? "研究" : "书单"}。</p> : null}<SharingPagination page={sourcePage} total={sources.data.total_pages} disabled={blocked} onPage={setSourcePage} /></> : <p role="status">正在读取本人对象…</p>}
        {data?<p className={styles.muted}>当前查看：{data.source.title}</p>:null}
        {objects.length?<><p className={styles.muted}>已选 {objects.length}/5 个对象。每类内容跨对象合计最多20项；每个对象至少勾选一项才能预览。</p><ul className={styles.scopeList}>{objects.map(object=><li key={`${object.kind}:${object.id}`}><button type="button" disabled={blocked} onClick={()=>chooseSource(object.kind,object.id)}>{object.title} · {Object.values(object.values).reduce((sum,items)=>sum+items.length,0)} 项</button><button type="button" disabled={blocked} onClick={()=>removeSource(object)}>移除</button></li>)}</ul></>:null}
      </div></section>
      <section className={styles.step}><h2><span>2</span><b className={styles.desktopStepTitle}>选择要包含的内容项</b><b className={styles.mobileStepTitle}>选择内容项</b></h2><div className={styles.stepBody}>
        <div className={styles.scopeKinds}>{(Object.keys(sectionLabels) as ShareSection[]).map(key=><div key={key}><input type="checkbox" aria-label={`包含${sectionLabels[key]}`} checked={totals[key]>0} disabled={blocked} onChange={event=>{if(!event.target.checked){setObjects(value=>value.map(object=>({...object,values:{...object.values,[key]:[]}})));invalidate();}else{setSection(key);setPage(1);setChoicesOpen(true);}}}/><FileText size={26}/><div><strong>{sectionLabels[key]} <small>{totals[key]} 项已选择</small></strong><p>{key==="questions"?"包含我提出的研究问题及简要说明。":key==="materials"?"包含我选择的文献条目与引用位置。":"包含我撰写的笔记与标签。"}</p></div><button disabled={blocked} onClick={()=>{setSection(key);setPage(1);setChoicesOpen(true);}}>选择 ›</button></div>)}</div>
        <div className={styles.excluded}><div><input type="checkbox" disabled checked={false} readOnly />私人正文 · 不包含</div><div><input type="checkbox" disabled checked={false} readOnly />PDF 原件 · 不包含</div><p>本人笔记需逐项勾选。未选中的内容不会分享。</p></div>
      </div></section>
      <section className={styles.step}><h2><span>3</span>预览将公开或提交的内容</h2><div className={styles.stepBody}><div className={styles.summaryBox}>{prepared ? <SharedSummary value={prepared.output} /> : <p className={styles.muted}>已选择 {selectedCount} 项。生成预览后，请逐项核对实际文字和来源。</p>}</div><button disabled={blocked || !currentInput || !selectedCount} onClick={() => preview()}>生成或更新预览</button></div></section>
      <section className={styles.step}><h2><span>4</span>选择目的地或接收范围</h2><div className={styles.stepBody}>
        <div className={styles.destinations}>{([
          ["campus", "学术小组", "仅本次明确选择的成员可见"], ["team", "合作研究团队", "仅本次明确选择的成员可见"],
          ["public", "公开分享链接（仅内容摘要）", "任何获得链接的人均可查看所选内容"], ["proposal", "提交为策划提案", "仅本站具有提案审核权限的编辑可查看"],
        ] as const).map(([value, title, copy]) => <label key={value}><input type="radio" name="share-destination" checked={destination === value} disabled={blocked} onChange={() => { setDestination(value); setGroupPage(1); setGroupId(""); setMembers([]); invalidate(); }} /><span>{title}<small>{copy}</small></span></label>)}</div>
        {(destination === "campus" || destination === "team") ? <div className={styles.destinationFields}>
          {groups.error ? <p role="alert">{groups.error}<button onClick={groups.reload}>重新读取小组</button></p> : <label>选择小组<select disabled={blocked} value={groupId} onChange={event => { setGroupId(event.target.value); setMembers([]); invalidate(); }}><option value="">请选择</option>{groups.data?.groups.results.filter(row => row.kind === destination).map(row => <option value={row.id} key={row.id}>{row.title}</option>)}</select></label>}
          {groups.data ? <SharingPagination page={groupPage} total={groups.data.groups.total_pages} disabled={blocked} onPage={setGroupPage} /> : null}
          <Link href="/account/groups">管理小组与邀请</Link>
          {group.error ? <p role="alert">{group.error}<button onClick={group.reload}>重新读取成员</button></p> : groupData ? <><p>明确选择接收成员</p><div className={styles.receiverList}>{groupData.members.map(member => <label key={member.membership_id}><input type="checkbox" checked={members.includes(member.user_id)} disabled={blocked} onChange={event => { setMembers(values => event.target.checked ? [...values, member.user_id] : values.filter(value => value !== member.user_id)); invalidate(); }} />{member.name}{member.user_id === owner ? "（自己）" : ""}</label>)}</div></> : null}
        </div> : null}
        <div className={styles.destinationFields}><label>附言（可选）<textarea value={message} maxLength={200} disabled={blocked} onChange={event => { setMessage(event.target.value); invalidate(); }} /><small>{message.length}/200</small></label><label>分享有效期<select value={expires} disabled={blocked} onChange={event => { setExpires(Number(event.target.value)); invalidate(); }}>{[7, 30, 90, 365].map(days => <option key={days} value={days}>{days} 天</option>)}</select></label></div>
      </div></section>
      <section className={styles.step}><h2><span>5</span>确认并提交</h2><div className={styles.stepBody}>
        <dl className={styles.confirmation}><div><dt>对象</dt><dd>{objects.length?objects.map(object=>object.title).join("、"):"尚未选择"}</dd></div><div><dt>包含内容</dt><dd>{(Object.keys(sectionLabels) as ShareSection[]).map(key => `${sectionLabels[key]} ${totals[key]} 项`).join(" · ")}</dd></div><div><dt>不包含</dt><dd>私人正文、PDF 原件、未选中的笔记</dd></div><div><dt>目的地</dt><dd>{destination ? prepared?.output.destination.title || "请更新预览核对" : "尚未选择"}</dd></div><div><dt>有效期</dt><dd>{expires} 天</dd></div></dl>
        {!ready ? <><p className={styles.muted}>请选择目的地，并更新预览核对当前内容。</p><button disabled={blocked || !destination || !selectedCount || !currentInput} onClick={() => preview(4)}>更新预览并核对</button></> : null}
        <label className={styles.check}><input type="checkbox" checked={confirmed} disabled={blocked || !ready} onChange={event => setConfirmed(event.target.checked)} />我已核对以上内容，并同意仅分享所选内容。</label>
        <div className={styles.actions}><Link href="/account/sharing">取消</Link><button className={styles.primary} disabled={blocked || !ready || !confirmed} onClick={() => send()}>确认提交</button></div>
      </div></section>
      <section className={styles.step}><h2><span>6</span>提交结果 · 返回原位置</h2><div className={styles.stepBody}>
        {receipt ? <><div className={styles.receipt}><CheckCircle2 size={40} /><h3>{receipt.share.revoked ? "原分享已撤回" : "已取得提交结果"}</h3><p>有效至 {new Date(receipt.share.expires_at).toLocaleString("zh-CN")}。接收方仅能查看确认范围内的内容。</p></div><div className={styles.objectList}>
          {receipt.token ? <button disabled={action.busy} onClick={copyLink}><Copy size={15} />复制分享链接</button> : null}
          {receipt.share.destination === "group" && !receipt.share.revoked ? <button disabled={action.busy} onClick={() => void action.run(signal => sharingRequest<ShareNotifyResult>(owner, `/reading/shares/${receipt.share.id}/`, { method: "POST", signal, body: JSON.stringify({ action: "notify", expected_revision: receipt.share.revision }) }), value => setActionMessage(`${value.message} 新增 ${value.created} 条，共 ${value.total} 位接收者已有通知。`))}><Mail size={15} />发送站内通知</button> : null}
          <Link href={`/account/sharing/${receipt.share.id}`}>查看内容与授权</Link><Link href="/account/sharing">查看提交记录</Link>
          {receipt.share.source_id ? <Link href={receipt.share.source_kind === "research" ? `/account/research/${receipt.share.source_id}` : `/account/collections/${receipt.share.source_id}`}>{receipt.share.source_count>1?"返回首个原对象":"返回原位置"}</Link> : null}
        </div></> : <p className={styles.muted}>提交后，可在这里查看结果和分享链接。</p>}
        {manual ? <label className={styles.manual}>手动复制分享链接<textarea readOnly value={manual} onFocus={event => event.currentTarget.select()} /></label> : null}
      </div></section>
    </div>
    <Dialog open={choicesOpen} onRequestClose={()=>{if(!action.busy)setChoicesOpen(false);}} className={`${styles.dialog} ${styles.choiceDialog}`} aria-label={`选择${sectionLabels[section]}`}><header className={styles.heading}><h2>选择{sectionLabels[section]}</h2><button disabled={action.busy} aria-label="关闭内容选择" onClick={()=>setChoicesOpen(false)}><X size={18}/></button></header><p>{data?.source.title||"请先选择本人研究或书单"}</p>        {!id ? <p className={styles.muted}>先选择一个本人研究或书单。</p> : choices.error ? <p role="alert">{choices.error}<button onClick={choices.reload}>重新读取</button>{activeObject?<button disabled={blocked} onClick={()=>removeSource(activeObject)}>清除此对象选择，再重新读取</button>:null}</p> : !data ? <p role="status">正在读取可选内容…</p> : <>
          {data.results.map(row => <label className={styles.choice} key={row.id}><input type="checkbox" checked={selected[section].includes(row.id)} disabled={blocked || !row.available || (totals[section]>=20||!activeObject&&objects.length>=5) && !selected[section].includes(row.id)} onChange={event => { const checked = event.target.checked; setSelected(value => ({ ...value, [section]: checked ? [...value[section], row.id] : value[section].filter(key => key !== row.id) })); invalidate(); }} /><span><strong>{row.title}</strong>{row.text ? <p>{row.text}</p> : null}<small>{row.available ? row.truncated ? "只分享预览显示的前 2000 字" : "只包含本项明确选择的内容" : "当前不可分享"}</small></span></label>)}
          {!data.results.length ? <p className={styles.muted}>当前对象没有此类内容。</p> : null}
          <SharingPagination page={page} total={data.total_pages} disabled={blocked} onPage={setPage} />
          {selected[section].length ? <button disabled={blocked} onClick={() => { setSelected(value => ({ ...value, [section]: [] })); invalidate(); }}>清空此对象本类选择</button> : null}
        </>}
<div className={styles.actions}><button className={styles.primary} disabled={action.busy} onClick={()=>setChoicesOpen(false)}>完成选择</button></div></Dialog>
    <div className={styles.mobileNext}>{phase > 1 ? <button disabled={action.busy} onClick={() => setPhase(value => value - 1)}>上一步</button> : null}{phase < 4 ? <button className={styles.primary} disabled={blocked || phase === 1 && (!currentInput || !selectedCount)} onClick={() => phase === 1 ? preview(2) : phase === 3 ? preview(4) : setPhase(value => value + 1)}>{phase === 1 ? "下一步：预览内容" : phase === 2 ? "下一步：选择目的地" : "下一步：确认范围"}</button> : null}</div>
  </>;
}
