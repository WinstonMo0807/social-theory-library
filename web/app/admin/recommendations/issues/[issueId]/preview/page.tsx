import { RecommendationIssueEditor } from "@/components/admin/recommendation-issue-editor";
import { IssuePreviewFrame } from "@/components/admin/curation/issue-preview-frame";
import { loadSiteChromeConfig } from "@/lib/api/site.server";
export default async function Page({ params,searchParams }: { params: Promise<{ issueId: string }>;searchParams:Promise<Record<string,string|string[]|undefined>> }) {
  const [{issueId},query]=await Promise.all([params,searchParams]);
  if(query.frame==="1") {const {config}=await loadSiteChromeConfig();return <IssuePreviewFrame key={String(query.version||"")} issueId={issueId} version={typeof query.version==="string"?query.version:""} config={config}/>;}
  return <RecommendationIssueEditor issueId={issueId} fullPreview />;
}
