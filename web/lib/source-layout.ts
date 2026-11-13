/** A presentation hint, not recovered table structure. No network or model calls. */
export function sourceLayoutHint(text: string): 'table'|'figure'|'formula'|null {
  if (/(?:^|\n)\s*(?:表\s*[\d一二三四五六七八九十]+|Table\s+\d+)(?=[:：.、\s]|\p{Script=Han})/imu.test(text) || text.split('\n').filter(line=>line.split('\t').length>=3).length>=2) return 'table';
  if (/(?:^|\n)\s*(?:图\s*[\d一二三四五六七八九十]+|Fig(?:ure)?\.?\s+\d+)(?=[:：.、\s]|\p{Script=Han})/imu.test(text)) return 'figure';
  if (text.split('\n').some(line=>line.trim().length<100 && !/\p{Script=Han}/u.test(line) && /[A-Za-zα-ωΑ-Ω0-9)]\s*[=≤≥≈∑∫]/u.test(line))) return 'formula';
  return null;
}
