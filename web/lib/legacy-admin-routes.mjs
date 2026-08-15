/**
 * @param {string} requestUrl
 * @param {string} [legacyId]
 */
export function legacyTheorySchoolAdminTarget(requestUrl, legacyId = "") {
  const incoming = new URL(requestUrl).searchParams;
  const target = new URLSearchParams();
  target.set("node_type", "theory_tradition");
  if (legacyId) target.set("legacy_id", legacyId);

  for (const [key, value] of incoming) {
    if (key === "node_type" || key === "legacy_id") continue;
    target.append(key, value);
  }

  return `/admin/theory-nodes?${target.toString()}`;
}
