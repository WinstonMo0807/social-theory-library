"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { createRequestKey } from "../../../lib/request-key";
import { useCallback, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, GripVertical, LayoutGrid, List, MoreVertical, Search, SlidersHorizontal } from "lucide-react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { PlacementState, PlacementGroup } from "@/lib/api/curation-workspace.client";
import { placementAuthors, placementGroupKey, placementType } from "@/components/public/placement-list";
import type { PlacementChoice } from "../knowledge/placement-source-picker";
import styles from "./placement-workspace.module.css";

type CatalogChoice = PlacementChoice & {version_count?:number};
type SourcePage = {count:number;next:string|null;previous:string|null;results:CatalogChoice[];topics?:string[];languages?:string[]};
type Item = PlacementState["items"][number];
export type PlacementPickerDraft={selected:Item[];group:number};
const sourceKey = (row: PlacementChoice) => row.source.work_id || row.target.id;
export function PlacementCatalogPicker({owner,title,groups,existing,onFinish,onCancel,value,onChange,blocked=false,targetPicker}:{owner:string;title:string;groups:PlacementGroup[];existing:Item[];onFinish:(items:Item[],group:PlacementGroup)=>void;onCancel:()=>void;value:PlacementPickerDraft;onChange:(value:PlacementPickerDraft)=>void;blocked?:boolean;targetPicker?:ReactNode}) {
  const [q,setQ]=useState(""),[search,setSearch]=useState(""),[page,setPage]=useState(1),[filters,setFilters]=useState({document_type:"",topic:"",language:"",readable:"",sort:"relevance"});
  const [grid,setGrid]=useState(false),[mobile,setMobile]=useState("search"),[message,setMessage]=useState(""),[versionWork,setVersionWork]=useState(""),[versionPage,setVersionPage]=useState(1),[drag,setDrag]=useState(""),[active,setActive]=useState(""),[filtersOpen,setFiltersOpen]=useState(true);
  const {selected,group}=value;
  const current=selected.find(row=>row.id===active)||selected[0];
  const setSelected=(next:Item[]|((current:Item[])=>Item[]))=>onChange({...value,selected:typeof next==="function"?next(selected):next});
  const setGroup=(next:number)=>onChange({...value,group:next});
  const target = groups[group] || groups[0] || {area:"main",name:"延伸阅读"};
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<SourcePage>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const params=new URLSearchParams({type:"edition",group_by:"work",q:search,page:String(page)});Object.entries(filters).forEach(([key,value])=>{if(value)params.set(key,value);});
  const resource=usePersistentWorkspace<SourcePage>(`/catalog/admin/content-placements/sources/?${params}`,owner,undefined,load);
  const versions=usePersistentWorkspace<SourcePage>(versionWork?`/catalog/admin/content-placements/sources/?type=edition&work_id=${encodeURIComponent(versionWork)}&page=${versionPage}`:"",owner,undefined,load);
  const duplicate=(choice:PlacementChoice)=>existing.some(row=>(row.area||"main")===target.area&&(row.group||"")===target.name&&row.source?.work_id===choice.source.work_id);
  function add(choice:PlacementChoice) {
    if(duplicate(choice)){setMessage("此作品已经在目标分组中。请返回编辑页修改原条目或选择其他分组。");return;}
    if(!choice.source.public_eligible||!choice.source.reader_url){setMessage("此版本尚未核实可读全文，请先在馆藏中补充并发布准确来源。");return;}
    if(selected.some(row=>row.source?.work_id===sourceKey(choice))){setMessage("已加入此作品。更换版本前请先从已选清单移除原版本。");return;}
    if(selected.length+existing.length>=100){setMessage("每个页面最多编排100项，请先整理已有内容。");return;}
    setSelected([...selected,{id:createRequestKey(),target:choice.target,source:choice.source,area:target.area,group:target.name,reason:"",internal_goal:"",display_fields:["authors","year","type","tags"]}]);setMessage("");
  }
  function move(id:string,index:number) {setSelected(rows=>{const next=[...rows],from=next.findIndex(row=>row.id===id);if(from<0||index<0||index>=next.length)return rows;const [row]=next.splice(from,1);next.splice(index,0,row);return next;});}
  function patch(id:string,values:Partial<Item>) {setSelected(rows=>rows.map(row=>row.id===id?{...row,...values}:row));}
  function chooseGroup(index:number){setGroup(index);setMessage("");}
  function finish(){if(blocked)return;if(selected.length+existing.length>100){setMessage("目标页面容纳不下本次清单，每页最多100项。请减少选择或更换目标页面。");setMobile("selected");return;}if(selected.some(row=>duplicate({target:row.target,source:row.source!}))){setMessage("目标分组已经包含所选作品，请移除重复项后继续。");setMobile("selected");return;}onFinish(selected.map(row=>({...row,area:target.area,group:target.name})),target);}
  function chooseVersion(choice:PlacementChoice){
    if(duplicate(choice)){setMessage("此作品已在目标分组中，请返回编辑页修改原条目。");return;}
    if(!choice.source.public_eligible||!choice.source.reader_url){setMessage("此版本尚无已核实的公开全文，请选择其他版本或先补充馆藏资料。");return;}
    const previous=selected.find(row=>row.source?.work_id===sourceKey(choice));
    if(previous){
      // Keep the page's prose and order; a different edition cannot retain an old page anchor.
      patch(previous.id,{target:choice.target,source:choice.source,reading_target:null});
      setMessage("已更换版本，推荐理由和顺序保留；原阅读页码已清除，请按新版本重新核对落点。");
    }else add(choice);
  }
  function sourceRow(choice:CatalogChoice){
    const work=String(sourceKey(choice)),selectedItem=selected.find(row=>row.source?.work_id===work),used=duplicate(choice);
    const src=selectedItem?.source||choice.source,added=!!selectedItem,cover=normalizePublicResourceUrl(String(src.image_url||""));
    const multiple=(choice.version_count||1)>1,open=versionWork===work;
    const toggleVersions=()=>{setVersionWork(open?"":work);setVersionPage(1);};
    const pick=()=>{if(multiple){setVersionWork(work);setVersionPage(1);setMessage("请展开此作品，选择需要加入的准确出版版本。");}else add(choice);};
    return <article key={work} className={styles.sourceRow}>
      <input type="checkbox" aria-label={`选择 ${src.title}`} checked={added||used} disabled={used||!multiple&&(!src.public_eligible||!src.reader_url)} onChange={()=>added?setSelected(selected.filter(row=>row.id!==selectedItem!.id)):pick()}/>
      <div className={styles.cover}>{cover?<img src={cover} alt="" loading="lazy"/>:<span>暂无封面</span>}</div>
      <div className={styles.sourceBody}><strong>{src.title}</strong><p>{placementAuthors(src)}</p><small>{[src.publication_year,placementType(src.document_type),src.edition_label,src.publisher].filter(Boolean).join(" · ")}</small>
        {Array.isArray(src.tags)?<p className={styles.tags}>{src.tags.map(tag=><span key={String(tag)}>{String(tag)}</span>)}</p>:null}
        <p className={styles.sourceAvailability}>{used?"已存在于目标分组":added?`分组：${target.name}`:multiple?`${choice.version_count} 个版本，请选择准确版本`:src.reader_url?"可阅读原文":"仅有书目或全文尚未公开"}</p>
        <div className={styles.sourceActions} data-added={used||added}><button type="button" disabled={used||added||!multiple&&(!src.public_eligible||!src.reader_url)} onClick={pick}>{used||added?"已加入":"加入"}</button>
          {src.work_id?<button type="button" aria-expanded={open} aria-controls={`placement-versions-${work}`} onClick={toggleVersions}>{open?"收起版本":"选择版本"}</button>:null}
          {src.edit_url?<details data-action-menu className={styles.rowMenu}><summary aria-label={`更多：${src.title}`}><MoreVertical size={16}/></summary><div data-menu-panel><a href={src.edit_url} target="_blank" rel="noopener">核对馆藏资料 ↗</a>{selectedItem?<button onClick={()=>{setActive(selectedItem.id);setMobile("selected");}}>编辑本页推荐理由</button>:null}</div></details>:null}
          {used?<button type="button" onClick={onCancel}>返回已有位置</button>:null}
        </div>
        {open?<section className={styles.versionChoices} id={`placement-versions-${work}`} aria-label={`${src.title}的出版版本`}>
          <h4>选择出版版本{multiple?"（必选）":""}</h4>
          {versions.error?<p role="alert">{versions.error}<button type="button" onClick={versions.reload}>重试</button></p>:!versions.data?<LoadingState role="status">正在读取版本…</LoadingState>:<>
            {versions.data.results.map(version=>{
              const option=version.source,active=selectedItem?.source?.edition_id===option.edition_id,available=!!option.public_eligible&&!!option.reader_url;
              return <div key={version.target.id}><label><input type="radio" name={`placement-version-${work}`} checked={active} disabled={used||!available} onChange={()=>chooseVersion(version)}/><span><strong>{String(option.edition_label||"未填写版本名称")}</strong><small>{[placementAuthors(option),option.publication_year,option.publisher].filter(Boolean).join(" · ")||"尚无出版说明"}</small><small>{active?"已选":available?"可阅读原文":"仅书目或全文尚未公开，暂不可加入"}</small></span></label>{option.edit_url?<a href={option.edit_url} target="_blank" rel="noopener">核对本版本</a>:null}</div>;
            })}
            {!versions.data.results.length?<p>当前没有可选版本，请重新读取馆藏结果。</p>:null}
            <nav className={styles.actions} aria-label="出版版本分页"><button type="button" disabled={!versions.data.previous} onClick={()=>setVersionPage(versionPage-1)}>上一页版本</button><span>第 {versionPage} 页 · {versions.data.count} 个版本</span><button type="button" disabled={!versions.data.next} onClick={()=>setVersionPage(versionPage+1)}>下一页版本</button></nav>
          </>}
        </section>:null}
      </div>
    </article>;
  }
  return <section className={styles.picker} data-mobile-panel={mobile} data-filters-open={filtersOpen}><header className={styles.heading}><div><p>{title} / 内容编排</p><h2>从馆藏选书与配置展示</h2></div><div className={styles.actions}><button type="button" onClick={onCancel}>返回编辑页面</button><button type="button" className={styles.primary} disabled={blocked||!selected.length} onClick={finish}>完成选择并返回（{selected.length}）</button></div></header><nav className={styles.mobileTabs} aria-label="选书视图"><button aria-pressed={mobile==="search"} onClick={()=>setMobile("search")}>搜索馆藏</button><button aria-pressed={mobile==="selected"} onClick={()=>setMobile("selected")}>已选清单（{selected.length}）</button></nav>{blocked?<p role="alert" className={styles.notice}>编排版本已变化或原请求尚未确认。本次清单保留在当前页面，请返回编辑页核对后重新打开选书继续。</p>:null}{message?<p role="alert" className={styles.notice}>{message}</p>:null}
    <div className={styles.pickerGrid}><section data-panel="search"><form onSubmit={event=>{event.preventDefault();setSearch(q.trim());setPage(1);}}><div className={styles.search}><Search size={17}/><input aria-label="搜索题名、作者、关键词" maxLength={500} value={q} onChange={event=>setQ(event.target.value)} placeholder="搜索题名、作者、关键词…"/><button className={styles.primary}>搜索</button><button type="button" className={styles.filterToggle} aria-label="筛选馆藏" aria-expanded={filtersOpen} onClick={()=>setFiltersOpen(!filtersOpen)}><SlidersHorizontal size={18}/></button></div><div className={styles.filters}><select data-stl-select aria-label="书刊类型" value={filters.document_type} onChange={event=>{setFilters({...filters,document_type:event.target.value});setPage(1);}}><option value="">书刊类型</option>{["book","journal_article","journal_issue","thesis","report"].map(value=><option key={value} value={value}>{placementType(value)}</option>)}</select><select data-stl-select aria-label="主题" value={filters.topic} onChange={event=>{setFilters({...filters,topic:event.target.value});setPage(1);}}><option value="">主题</option>{(resource.data?.topics||[]).map(topic=><option key={topic} value={topic}>{topic}</option>)}</select><select data-stl-select aria-label="可读状态" value={filters.readable} onChange={event=>{setFilters({...filters,readable:event.target.value});setPage(1);}}><option value="">可读状态</option><option value="yes">可读全文</option><option value="no">未公开全文</option></select><select data-stl-select aria-label="语言" value={filters.language} onChange={event=>{setFilters({...filters,language:event.target.value});setPage(1);}}><option value="">语言</option>{(resource.data?.languages||[]).map(language=><option key={language} value={language}>{({"zh":"中文","zh-CN":"简体中文","zh-TW":"繁体中文","en":"英语","fr":"法语","de":"德语","ja":"日语"} as Record<string,string>)[language]||language}</option>)}</select><button type="button" onClick={()=>{setFilters({document_type:"",topic:"",language:"",readable:"",sort:"relevance"});setQ("");setSearch("");setPage(1);}}>清除筛选</button></div></form><div className={styles.heading}><h3>搜索结果 {resource.data?`（${resource.data.count} 部作品）`:""}</h3><div className={styles.actions}><select data-stl-select aria-label="排序" value={filters.sort} onChange={event=>{setFilters({...filters,sort:event.target.value});setPage(1);}}><option value="relevance">相关度</option><option value="title">题名</option><option value="newest">年份从新到旧</option><option value="oldest">年份从旧到新</option></select><button title="列表" aria-label="列表" aria-pressed={!grid} onClick={()=>setGrid(false)}><List size={16}/></button><button title="网格" aria-label="网格" aria-pressed={grid} onClick={()=>setGrid(true)}><LayoutGrid size={16}/></button></div></div>{resource.error?<p role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p>:!resource.data?<LoadingState role="status">正在搜索馆藏…</LoadingState>:<><div className={grid?styles.sourceGrid:styles.sources}>{resource.data.results.map(sourceRow)}</div>{!resource.data.count?<div className={styles.empty}><h3>未找到相关馆藏</h3><p>请核对书名、作者，或减少主题、语言和可读条件。</p></div>:null}<nav className={styles.actions} aria-label="馆藏分页"><button disabled={!resource.data.previous} onClick={()=>setPage(page-1)}>上一页</button><span>第 {page} 页</span><button disabled={!resource.data.next} onClick={()=>setPage(page+1)}>下一页</button></nav></>}
    </section><aside data-panel="selected" className={styles.selectedPanel}><section className={styles.selectedCard}><header className={styles.heading}><h3>已选清单 <small>{selected.length} 项</small></h3><button disabled={blocked||!selected.length} onClick={()=>setSelected([])}>清空</button></header>{!selected.length?<p className={styles.empty}>先在左侧选择准确出版版本。</p>:<ol className={styles.selectedList}>{selected.map((row,index)=><li key={row.id} data-selected={current?.id===row.id} draggable onDragStart={()=>setDrag(row.id)} onDragOver={event=>event.preventDefault()} onDrop={event=>{event.preventDefault();move(drag,index);setDrag("");}}><GripVertical size={13}/><span>{index+1}</span><button className={styles.selectedBook} onClick={()=>setActive(row.id)}><div className={styles.cover}>{row.source?.image_url?<img src={normalizePublicResourceUrl(String(row.source.image_url))} alt=""/>:<span>暂无封面</span>}</div><span><strong>{row.source?.title}</strong><small>{[placementAuthors(row.source),row.source?.publication_year,placementType(row.source?.document_type)].filter(Boolean).join(" · ")}</small></span></button><span className={styles.itemState}>已加入</span><details data-action-menu className={styles.rowMenu}><summary aria-label={`${row.source?.title||"所选内容"}操作`}><MoreVertical size={16}/></summary><div data-menu-panel><button aria-label="上移所选书目" disabled={!index} onClick={()=>move(row.id,index-1)}><ArrowUp size={14}/>上移</button><button aria-label="下移所选书目" disabled={index===selected.length-1} onClick={()=>move(row.id,index+1)}><ArrowDown size={14}/>下移</button><button onClick={()=>setSelected(selected.filter(item=>item.id!==row.id))}>从已选清单移除</button></div></details></li>)}</ol>}</section><section className={styles.selectedCard}><h3>目标页面／分组</h3><div className={styles.targetPage}><span>目标页面</span><strong>{title}</strong>{targetPicker}</div><label className={styles.targetGroup}>分组<select data-stl-select value={group} onChange={event=>chooseGroup(Number(event.target.value))}>{(groups.length?groups:[target]).map((row,index)=><option key={placementGroupKey(row)} value={index}>{row.name||"未命名分组"}</option>)}</select></label><small>这些作品将展示在页面的“{target.name}”分组。</small></section>{current?<section className={styles.selectedCard}><h3>本页推荐理由（发布后展示）</h3><p className={styles.currentTitle}>{current.source?.title}</p><label><span className="sr-only">本页推荐理由</span><textarea maxLength={200} value={current.reason||""} onChange={event=>patch(current.id,{reason:event.target.value})}/><small className={styles.counter}>{current.reason?.length||0}/200</small></label><h3>阅读落点</h3><p>{current.reading_target?`PDF 第 ${current.reading_target.pdf_page} 页`:String(current.source?.edition_label||"所选版本原文")}</p>{current.source?.reader_url?<a href={current.source.reader_url} target="_blank" rel="noopener">选择版本／章节／原文 ↗</a>:<p>暂无可读全文</p>}{current.source?.asset_id&&current.source?.document_revision_id?<label>物理页（留空使用版本入口）<input type="number" min={1} max={typeof current.source.page_count==="number"?current.source.page_count:undefined} value={current.reading_target?.pdf_page||""} onChange={event=>patch(current.id,{reading_target:event.target.value?{asset_id:current.source!.asset_id!,document_revision_id:current.source!.document_revision_id!,pdf_page:Number(event.target.value)}:null})}/></label>:null}<section data-content-section className={styles.internalNote}><header data-section-heading>内部阅读目标（仅编辑可见）</header><label>预期阅读收获<textarea maxLength={1000} value={current.internal_goal||""} onChange={event=>patch(current.id,{internal_goal:event.target.value})}/></label></section>{current.source?.edit_url?<p className={styles.catalogLink}>发现书目信息错误？ <a href={current.source.edit_url} target="_blank" rel="noopener">前往编辑馆藏信息 →</a></p>:null}</section>:null}</aside></div><footer className={styles.pickerFooter}><button onClick={()=>setMobile("selected")}>已选 {selected.length} 项</button><button className={styles.primary} disabled={blocked||!selected.length} onClick={finish}>完成选择并返回</button></footer>
  </section>;
}
