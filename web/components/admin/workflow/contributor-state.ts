export function fillContributor(rows: Record<string, unknown>[], person: { id: string; name: string }, role: string, extra: Record<string, unknown> = {}): Record<string, unknown>[] {
  if (rows.some(row => row.person_id === person.id && row.role === role)) return rows;
  const unresolved = rows.map((row, index) => ({ row, index })).filter(({ row }) => !row.person_id && (row.role || "author") === role);
  const matching = unresolved.find(({ row }) => String(row.display_name || "").trim() === person.name.trim());
  const index = matching?.index ?? (unresolved.length === 1 ? unresolved[0].index : -1);
  const linked = { ...(index >= 0 ? rows[index] : {}), person_id: person.id, display_name: person.name, role, resolution_state: "selected", ...extra };
  return index >= 0 ? rows.map((row, i) => i === index ? linked : row) : [...rows, linked];
}

export const contributorRoleOptions = [
  { value: "author", label: "作者" },
  { value: "chief_editor", label: "主编" },
  { value: "editor", label: "编者" },
  { value: "translator", label: "译者" },
  { value: "annotator", label: "校注" },
  { value: "photographer", label: "摄影" },
  { value: "advisor", label: "导师" },
  { value: "subject", label: "研究对象" },
  { value: "other", label: "其他贡献者" },
] as const;
