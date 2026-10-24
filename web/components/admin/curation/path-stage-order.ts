/** Reorder the original material objects; their stable IDs and dependencies survive. */
export function movePathMaterial<T extends { key: string; items: { key: string }[] }>(
  stages: T[], itemKey: string, stageKey: string, beforeKey?: string,
): T[] {
  const source = stages.find(stage => stage.items.some(item => item.key === itemKey));
  const target = stages.find(stage => stage.key === stageKey);
  const item = source?.items.find(row => row.key === itemKey);
  if (!source || !target || !item || beforeKey === itemKey || beforeKey && !target.items.some(row => row.key === beforeKey)) return stages;
  return stages.map(stage => {
    if (stage !== source && stage !== target) return stage;
    const items = stage.items.filter(row => row.key !== itemKey);
    if (stage === target) items.splice(beforeKey ? items.findIndex(row => row.key === beforeKey) : items.length, 0, item);
    return { ...stage, items };
  });
}

export function movePathStage<T extends { key: string }>(stages: T[], fromKey: string, beforeKey?: string): T[] {
  const source = stages.find(stage => stage.key === fromKey);
  if (!source || fromKey === beforeKey || beforeKey && !stages.some(row => row.key === beforeKey)) return stages;
  const result = stages.filter(stage => stage !== source);
  result.splice(beforeKey ? result.findIndex(row => row.key === beforeKey) : result.length, 0, source);
  return result;
}
