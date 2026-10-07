export type TheoryNodeDraft = {
  node_type: string; canonical_name_zh: string; canonical_name_en: string; slug: string;
  aliases: Array<{alias: string; language: string; alias_type: string}>;
  summary: string; definition: string; core_questions: string; basic_propositions: string; theoretical_boundary: string;
  start_year: string; end_year: string; period_label: string; parent: string; primary_discipline: string;
  related_disciplines: string[]; subdisciplines: string[]; topics: string[]; status: string; sort_order: number;
};
type DisciplineLink = {discipline: {id:string}; relation_type:string; discipline_specific_summary:string; sort_order:number; status:string};
type SubdisciplineLink = {subdiscipline: {id:string}; is_primary:boolean; relation_role:string; source:string; confidence:number; sort_order:number; status:string};
type TopicLink = {topic: {id:string}; relation_label:string; source:string; confidence:number; sort_order:number; status:string};
export type TheoryNodeRecord = Omit<TheoryNodeDraft,"core_questions"|"basic_propositions"|"start_year"|"end_year"|"parent"|"primary_discipline"|"related_disciplines"|"subdisciplines"|"topics"> & {
  core_questions:string[]; basic_propositions:string[]; start_year:number|null; end_year:number|null; parent:string|null; primary_discipline:string|null;
  discipline_links:DisciplineLink[]; subdiscipline_links:SubdisciplineLink[]; topic_links:TopicLink[];
};
const same = (a:unknown,b:unknown) => JSON.stringify(a)===JSON.stringify(b);
const lines = (value:string) => value.split(/\r?\n/).map(row=>row.trim()).filter(Boolean);

export function theoryNodeToDraft(node:TheoryNodeRecord):TheoryNodeDraft {
  return {node_type:node.node_type,canonical_name_zh:node.canonical_name_zh,canonical_name_en:node.canonical_name_en,slug:node.slug,
    aliases:node.aliases.map(row=>({alias:row.alias,language:row.language||"zh-CN",alias_type:row.alias_type||"alias"})),
    summary:node.summary,definition:node.definition,core_questions:node.core_questions.join("\n"),basic_propositions:node.basic_propositions.join("\n"),theoretical_boundary:node.theoretical_boundary,
    start_year:node.start_year?.toString()??"",end_year:node.end_year?.toString()??"",period_label:node.period_label,parent:node.parent??"",primary_discipline:node.primary_discipline??"",
    related_disciplines:node.discipline_links.filter(row=>row.relation_type!=="primary").map(row=>row.discipline.id),subdisciplines:(node.subdiscipline_links||[]).map(row=>row.subdiscipline.id),topics:(node.topic_links||[]).map(row=>row.topic.id),status:node.status,sort_order:node.sort_order};
}

export function buildTheoryNodePayload(draft:TheoryNodeDraft, saved:TheoryNodeRecord|null, draftOnly=true):Record<string,unknown> {
  const before=saved?theoryNodeToDraft(saved):null;
  const payload:Record<string,unknown>={};
  const scalarKeys=["node_type","canonical_name_zh","canonical_name_en","slug","summary","definition","core_questions","basic_propositions","theoretical_boundary","start_year","end_year","period_label","parent","primary_discipline","sort_order"] as const;
  for(const key of scalarKeys) {
    if(before&&same(draft[key],before[key]))continue;
    if(key==="slug"&&!saved&&!draft.slug.trim())continue;
    payload[key]=key==="core_questions"||key==="basic_propositions"?lines(draft[key]):key==="start_year"||key==="end_year"?draft[key]?Number(draft[key]):null:key==="parent"||key==="primary_discipline"?draft[key]||null:draft[key];
  }
  if(!before||!same(draft.aliases,before.aliases))payload.aliases=draft.aliases.map(row=>({alias:row.alias.trim(),language:row.language||"zh-CN",alias_type:row.alias_type||"alias"})).filter(row=>row.alias);
  if(!before||!same(draft.related_disciplines,before.related_disciplines)) {
    const existing=saved?.discipline_links||[],maxOrder=Math.max(-1,...existing.map(row=>row.sort_order));
    const selected=new Set(draft.related_disciplines);
    const retain=(row:DisciplineLink)=>({discipline_id:row.discipline.id,relation_type:row.relation_type,discipline_specific_summary:row.discipline_specific_summary,sort_order:row.sort_order,status:row.status});
    payload.discipline_links=[...existing.filter(row=>row.relation_type==="primary"&&!selected.has(row.discipline.id)).map(retain),...draft.related_disciplines.map((id,index)=>{const row=existing.find(row=>row.discipline.id===id);return row?retain(row):{discipline_id:id,relation_type:"related",discipline_specific_summary:"",sort_order:maxOrder+index+1,status:"pending"};})];
  }
  if(!before||!same(draft.subdisciplines,before.subdisciplines)) {
    const existing=saved?.subdiscipline_links||[],maxOrder=Math.max(-1,...existing.map(row=>row.sort_order));
    payload.subdiscipline_links=draft.subdisciplines.map((id,index)=>{const row=existing.find(row=>row.subdiscipline.id===id);return row?{subdiscipline_id:id,is_primary:row.is_primary,relation_role:row.relation_role,source:row.source,confidence:row.confidence,sort_order:row.sort_order,status:row.status}:{subdiscipline_id:id,is_primary:!saved&&index===0,relation_role:!saved&&index===0?"home":"related",source:"editorial",confidence:1,sort_order:maxOrder+index+1,status:"pending"};});
  }
  if(!before||!same(draft.topics,before.topics)) {
    const existing=saved?.topic_links||[],maxOrder=Math.max(-1,...existing.map(row=>row.sort_order));
    payload.topic_links=draft.topics.map((id,index)=>{const row=existing.find(row=>row.topic.id===id);return row?{topic_id:id,relation_label:row.relation_label,source:row.source,confidence:row.confidence,sort_order:row.sort_order,status:row.status}:{topic_id:id,relation_label:"",source:"editorial",confidence:1,sort_order:maxOrder+index+1,status:"pending"};});
  }
  if(!saved)payload.status=draftOnly?"draft":draft.status;
  else if(!draftOnly&&draft.status!==saved.status)payload.status=draft.status;
  return payload;
}
