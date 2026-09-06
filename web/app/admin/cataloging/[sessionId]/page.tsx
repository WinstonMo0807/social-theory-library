import { CatalogingWorkbench } from "@/components/admin/workflow/cataloging-session";

export const metadata = { title: "编目工作台" };

export default async function CatalogingPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <CatalogingWorkbench sessionId={sessionId} />;
}
