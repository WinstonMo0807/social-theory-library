"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Minus, Plus, RotateCcw } from "lucide-react";
import { relationArrow, scholarRelationLabels, scholarRelationStatus, type ScholarRelation } from "@/lib/api/scholar-relations.types";

export function ScholarRelationNetwork({ relations, centerScholarId, selectedId, initialSelectedId = "", onSelect }: {
  relations: ScholarRelation[]; centerScholarId?: string; selectedId?: string; initialSelectedId?: string; onSelect?: (relation: ScholarRelation) => void;
}) {
  const [selected, setSelected] = useState(initialSelectedId);
  const [filter, setFilter] = useState("");
  const [zoom, setZoom] = useState(1);
  const markerId = useId().replace(/:/g, "");
  const visible = relations.filter(row => !filter || row.relation_type === filter);
  const people = new Map<string,{id:string;name:string;slug?:string}>();
  visible.forEach(row => { people.set(row.source_scholar,{id:row.source_scholar,name:row.source_name,slug:row.source_slug}); people.set(row.target_scholar,{id:row.target_scholar,name:row.target_name,slug:row.target_slug}); });
  const outer = Array.from(people.values()).filter(person => person.id !== centerScholarId);
  const positions = new Map(Array.from(people.values()).map(person => {
    const index = outer.findIndex(item => item.id === person.id);
    const angle = index / Math.max(outer.length,1) * Math.PI * 2 - Math.PI/2;
    return [person.id,{...person,x:person.id === centerScholarId ? 450 : 450+Math.cos(angle)*320,y:person.id === centerScholarId ? 280 : 280+Math.sin(angle)*205}];
  }));
  const active = visible.find(row => row.id === (selectedId ?? selected));
  const select = (relation: ScholarRelation) => { setSelected(relation.id); onSelect?.(relation); };
  return <div className="scholar-relation-network">
    <div className="knowledge-map-toolbar"><label>关系类型<select value={filter} onChange={event=>setFilter(event.target.value)}><option value="">全部关系</option>{Object.entries(scholarRelationLabels).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><span>{people.size} 位学者 · {visible.length} 条关系</span><button type="button" aria-label="缩小学者关系图" onClick={()=>setZoom(value=>Math.max(.6,value-.15))}><Minus size={15}/></button><button type="button" aria-label="放大学者关系图" onClick={()=>setZoom(value=>Math.min(2,value+.15))}><Plus size={15}/></button><button type="button" aria-label="复位学者关系图" onClick={()=>{setZoom(1);setSelected("");}}><RotateCcw size={15}/></button></div>
    {visible.length ? <div className="knowledge-map-stage scholar-relation-stage"><svg viewBox="0 0 900 560" role="img" aria-label="有来源的学者关系图"><defs><marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/></marker></defs><g transform={`translate(450 280) scale(${zoom}) translate(-450 -280)`}>
      {visible.map((relation,index)=>{const source=positions.get(relation.source_scholar)!,target=positions.get(relation.target_scholar)!; const dx=target.x-source.x,dy=target.y-source.y,distance=Math.max(1,Math.hypot(dx,dy));const offset=(index%3-1)*24;const sx=source.x+dx/distance*74,sy=source.y+dy/distance*36,tx=target.x-dx/distance*74,ty=target.y-dy/distance*36;const mx=(sx+tx)/2-dy/distance*offset,my=(sy+ty)/2+dx/distance*offset;return <g key={relation.id} data-relation-id={relation.id} className={active?.id===relation.id?"is-selected":""} role="button" tabIndex={0} aria-label={`${relation.source_name} ${relationArrow(relation.direction)} ${relation.target_name}：${scholarRelationLabels[relation.relation_type]}`} onClick={()=>select(relation)} onKeyDown={event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();select(relation);}}}><path className="scholar-relation-edge" d={`M ${sx} ${sy} Q ${mx} ${my} ${tx} ${ty}`} markerEnd={relation.direction!=="undirected"?`url(#${markerId})`:undefined} markerStart={relation.direction==="bidirectional"?`url(#${markerId})`:undefined}/><text x={mx} y={my-10} textAnchor="middle">{scholarRelationLabels[relation.relation_type]}</text></g>;})}
      {Array.from(positions.values()).map(person=><g key={person.id} className={`knowledge-map-node ${person.id===centerScholarId?"is-center":""}`} role="button" tabIndex={0} aria-label={`查看${person.name}的关系`} onClick={()=>{const row=visible.find(item=>item.source_scholar===person.id||item.target_scholar===person.id);if(row)select(row);}} onKeyDown={event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();const row=visible.find(item=>item.source_scholar===person.id||item.target_scholar===person.id);if(row)select(row);}}}><rect x={person.x-75} y={person.y-29} width={150} height={58} rx={4}/><text x={person.x} y={person.y+5} textAnchor="middle">{person.name.length>11?`${person.name.slice(0,11)}…`:person.name}</text></g>)}
    </g></svg></div> : <p className="empty-state">尚无符合筛选的已确认关系。</p>}
    {active ? <section className="scholar-relation-detail" data-relation-id={active.id}><p className="eyebrow">{scholarRelationLabels[active.relation_type]} · {scholarRelationStatus(active)}</p><h2>{active.source_slug&&!onSelect?<Link href={`/scholars/${active.source_slug}`}>{active.source_name}</Link>:active.source_name} {relationArrow(active.direction)} {active.target_slug&&!onSelect?<Link href={`/scholars/${active.target_slug}`}>{active.target_name}</Link>:active.target_name}</h2><p>{active.summary || "关系说明尚未填写。"}</p><h3>来源</h3><p>{active.source || "尚未补充依据，保持草稿。"}</p></section> : <p className="knowledge-map-hint">选择学者或关系，查看方向、说明与来源。</p>}
    {visible.length ? <details className="knowledge-map-text"><summary>按文字阅读全部关系</summary>{visible.map(relation=><p key={relation.id}><button type="button" data-relation-id={relation.id} onClick={()=>select(relation)}>{relation.source_name} {relationArrow(relation.direction)} {relation.target_name} · {scholarRelationLabels[relation.relation_type]}</button></p>)}</details> : null}
  </div>;
}
