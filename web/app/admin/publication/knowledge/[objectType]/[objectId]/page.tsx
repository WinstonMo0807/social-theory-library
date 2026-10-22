import {KnowledgeHistory} from "@/components/admin/knowledge/knowledge-history";

export default async function KnowledgeHistoryPage({params}:{params:Promise<{objectType:string;objectId:string}>}) {
  const {objectType,objectId}=await params;
  return <KnowledgeHistory objectType={objectType} objectId={objectId}/>;
}
