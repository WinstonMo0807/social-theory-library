import { ScholarKnowledgeRelations } from "@/components/admin/knowledge/scholar-knowledge-relations";
export default async function Page({params}:{params:Promise<{scholarId:string}>}) {
  const {scholarId} = await params;
  return <ScholarKnowledgeRelations key={scholarId} scholarId={scholarId}/>;
}
