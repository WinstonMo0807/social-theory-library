import { legacyTheorySchoolAdminTarget } from "../../../../lib/legacy-admin-routes.mjs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ entityId: string }> },
) {
  const { entityId } = await params;
  return new Response(null, {
    status: 307,
    headers: {
      location: legacyTheorySchoolAdminTarget(request.url, entityId),
    },
  });
}
