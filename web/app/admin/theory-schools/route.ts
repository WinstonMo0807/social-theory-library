import { legacyTheorySchoolAdminTarget } from "../../../lib/legacy-admin-routes.mjs";

export function GET(request: Request) {
  return new Response(null, {
    status: 307,
    headers: {
      location: legacyTheorySchoolAdminTarget(request.url),
    },
  });
}
