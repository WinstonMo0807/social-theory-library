import { SemanticIndexAdmin } from "@/components/semantic-index-admin";
import { IndexMaintenance } from "@/components/admin/index-maintenance";
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  return params.legacy === "1" ? <SemanticIndexAdmin /> : <IndexMaintenance />;
}
