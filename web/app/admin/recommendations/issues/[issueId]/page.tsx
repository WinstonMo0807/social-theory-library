import { RecommendationIssueEditor } from "@/components/admin/recommendation-issue-editor";
export default async function Page({ params }: { params: Promise<{ issueId: string }> }) { const { issueId } = await params; return <RecommendationIssueEditor issueId={issueId} />; }
