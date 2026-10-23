import { CatalogingWorkbench } from "@/components/admin/workflow/cataloging-session";

export const metadata={title:"字段候选与材料助手"};
export default async function CandidatesPage({params}:{params:Promise<{sessionId:string}>}){
  const {sessionId}=await params;
  return <CatalogingWorkbench sessionId={sessionId} initialAssistant/>;
}
