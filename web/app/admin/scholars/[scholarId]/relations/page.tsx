import { ScholarRelationsEditor } from "@/components/admin/knowledge/scholar-relations-editor";
export default async function Page({params}:{params:Promise<{scholarId:string}>}) {
  const {scholarId} = await params;
  return <ScholarRelationsEditor key={scholarId} scholarId={scholarId}/>;
}
