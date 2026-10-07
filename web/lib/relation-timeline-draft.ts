export type RelationDraft = {
  source_node:string; target_node:string; relation_type:string; direction:string;
  description:string; evidence_source:string; confidence:number; status:string;
};
export function relationToDraft(row:RelationDraft):RelationDraft {
  return {source_node:row.source_node,target_node:row.target_node,relation_type:row.relation_type,direction:row.direction,
    description:row.description,evidence_source:row.evidence_source,confidence:row.confidence,status:row.status};
}
export function buildRelationPayload(draft:RelationDraft,saved:RelationDraft|null):Partial<RelationDraft> {
  if (!saved) return {...draft};
  return Object.fromEntries(Object.entries(draft).filter(([name,value])=>value!==saved[name as keyof RelationDraft]));
}

export type TimelineRelation = {
  id?:string; relation_type:string; node:string|null; node_name?:string; discipline:string|null; discipline_name?:string;
  scholar:string|null; scholar_name?:string; work:string|null; work_title?:string; evidence:string|null; description:string; sort_order:number;
};
export type TimelineEvidenceFile = {
  id:string; work_id:string; work_title:string; edition_id:string; edition_label:string;
  filename:string; version:number; page_count:number; reader_href:string|null; detail:string;
};
export type TimelineRecord = {
  id:string; title:string; description:string; event_type:string; start_year:number|null; end_year:number|null; date_label:string;
  orientation:string; source:string; evidence_asset:string|null; evidence_file?:TimelineEvidenceFile|null; evidence_page:number|null;
  evidence_printed_label:string; evidence_text:string; confidence:number; review_status:string; display_order:number;
  discipline:string|null; theory_school:string|null; subdiscipline:string|null; scholar:string|null; work:string|null; relations:TimelineRelation[];
};
export type TimelineDraft = {
  title:string; description:string; event_type:string; start_year:string; end_year:string; date_label:string; source:string;
  source_work:string; source_edition:string; evidence_asset:string; evidence_page:string; evidence_printed_label:string; evidence_text:string;
  confidence:number; review_status:string; display_order:number; nodes:string[]; disciplines:string[]; scholar:string; work:string;
};
export const emptyTimelineDraft:TimelineDraft = {
  title:"",description:"",event_type:"publication",start_year:"",end_year:"",date_label:"",source:"",source_work:"",source_edition:"",
  evidence_asset:"",evidence_page:"",evidence_printed_label:"",evidence_text:"",confidence:1,review_status:"suggested",display_order:0,
  nodes:[],disciplines:[],scholar:"",work:"",
};
const unique = (values:Array<string|null>) => [...new Set(values.filter((value):value is string=>Boolean(value)))];
export function timelineToDraft(event:TimelineRecord):TimelineDraft {
  return {title:event.title,description:event.description,event_type:event.event_type,start_year:event.start_year?.toString()??"",
    end_year:event.end_year?.toString()??"",date_label:event.date_label,source:event.source,source_work:event.evidence_file?.work_id??"",
    source_edition:event.evidence_file?.edition_id??"",evidence_asset:event.evidence_asset??"",evidence_page:event.evidence_page?.toString()??"",
    evidence_printed_label:event.evidence_printed_label,evidence_text:event.evidence_text,confidence:event.confidence,review_status:event.review_status,
    display_order:event.display_order,nodes:unique(event.relations.map(row=>row.node)),disciplines:unique(event.relations.map(row=>row.discipline)),
    scholar:event.scholar??event.relations.find(row=>row.scholar)?.scholar??"",work:event.work??event.relations.find(row=>row.work)?.work??""};
}
const sameIds = (left:string[],right:string[]) => JSON.stringify([...new Set(left)].sort())===JSON.stringify([...new Set(right)].sort());
const relationValues = (row:TimelineRelation) => ({relation_type:row.relation_type,node:row.node,discipline:row.discipline,scholar:row.scholar,
  work:row.work,evidence:row.evidence,description:row.description,sort_order:row.sort_order});

export function buildTimelinePayload(draft:TimelineDraft,saved:TimelineRecord|null):Record<string,unknown> {
  const before = saved ? timelineToDraft(saved) : null;
  const payload:Record<string,unknown> = {};
  const strings = ["title","description","event_type","date_label","source","evidence_printed_label","evidence_text","confidence","review_status","display_order"] as const;
  for (const name of strings) if (!before || draft[name]!==before[name]) payload[name]=draft[name];
  for (const name of ["start_year","end_year","evidence_page"] as const) if (!before || draft[name]!==before[name]) payload[name]=draft[name] ? Number(draft[name]) : null;
  for (const name of ["evidence_asset","scholar","work"] as const) if (!before || draft[name]!==before[name]) payload[name]=draft[name] || null;
  if (!before || draft.source_work!==before.source_work || draft.source_edition!==before.source_edition || "evidence_asset" in payload) {
    payload.evidence_work_id=draft.source_work || null;
    payload.evidence_edition_id=draft.source_edition || null;
  }
  if (!before || !sameIds(draft.nodes,before.nodes) || !sameIds(draft.disciplines,before.disciplines)) {
    const retained=(saved?.relations || []).filter(row=>(!row.node || draft.nodes.includes(row.node)) && (!row.discipline || draft.disciplines.includes(row.discipline)));
    let order=Math.max(-1,...(saved?.relations || []).map(row=>row.sort_order))+1;
    const additions:TimelineRelation[]=[];
    for (const node of unique(draft.nodes)) if (!retained.some(row=>row.node===node)) additions.push({relation_type:"subject",node,discipline:null,scholar:null,work:null,evidence:null,description:"",sort_order:order++});
    for (const discipline of unique(draft.disciplines)) if (!retained.some(row=>row.discipline===discipline)) additions.push({relation_type:"context",node:null,discipline,scholar:null,work:null,evidence:null,description:"",sort_order:order++});
    payload.relations=[...retained,...additions].map(relationValues);
  }
  return payload;
}
