export function fillContributor(rows: Record<string, unknown>[], person: { id: string; name: string }, role: string, extra: Record<string, unknown> = {}): Record<string, unknown>[] {
  if (rows.some(row => row.person_id === person.id && row.role === role)) return rows;
  const unresolved = rows.map((row, index) => ({ row, index })).filter(({ row }) => !row.person_id && (row.role || "author") === role);
  const matching = unresolved.find(({ row }) => String(row.display_name || "").trim() === person.name.trim());
  const index = matching?.index ?? (unresolved.length === 1 ? unresolved[0].index : -1);
  const linked = { ...(index >= 0 ? rows[index] : {}), person_id: person.id, display_name: person.name, role, resolution_state: "selected", ...extra };
  return index >= 0 ? rows.map((row, i) => i === index ? linked : row) : [...rows, linked];
}
