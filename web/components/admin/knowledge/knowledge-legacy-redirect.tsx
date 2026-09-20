"use client";
import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
/** Preserve object selection, filters, paging, return address and hash on retired entrances. */
export function KnowledgeLegacyRedirect({destination,taxonomy=false}:{destination?:string;taxonomy?:boolean}) {
 const router=useRouter(); const search=useSearchParams();
 useEffect(()=>{
  const query=new URLSearchParams(search.toString());const type=query.get("object_type") || "";const id=query.get("object_id") || "";
  let next=destination || "/admin/theories";
  if(!destination){
   if(type==="scholar") next=id?`/admin/scholars/${encodeURIComponent(id)}`:"/admin/scholars";
   else if(type==="topic") next=id?`/admin/topics/${encodeURIComponent(id)}`:"/admin/topics";
   else if(type==="discipline" || type==="subdiscipline"){next=`/admin/theories/${type==="discipline"?"disciplines":"subdisciplines"}`;if(id)query.set(type,id);}
   else if(type==="reading_path"){next="/admin/theories/reading-paths";if(id)query.set("path",id);}
   else if(type==="work"){next="/admin/library";if(id)query.set("work",id);}
   else if(id)next=`/admin/theories/${encodeURIComponent(id)}`;
  }
  if(taxonomy){const kind=query.get("kind") || query.get("type") || type;const theory=kind==="theory" || kind==="theory_school" || Boolean(query.get("theory")) || /theor/.test(window.location.hash);const selected=id || query.get(theory?"theory":"topic") || query.get("id");next=theory?"/admin/theories":"/admin/topics";if(selected){if(theory)query.set("legacy_id",selected);else next+=`/${encodeURIComponent(selected)}`;}}
  if(destination==="/admin/theories" && query.get("node")) next=`/admin/theories/${encodeURIComponent(query.get("node")!)}`;
  router.replace(`${next}${query.size?`?${query.toString()}`:""}${window.location.hash}`);
 },[destination,taxonomy,router,search]);
 return <p role="status">正在打开对应的内容编辑位置…</p>;
}
