/** Presentation only. Never use this text for source matching, offsets or storage. */
export function formatSourceText(value: string, { joinSpacedLines = true }: { joinSpacedLines?: boolean } = {}): string {
  const lines = value.replace(/\r\n?/g, "\n").replace(/\u00ad[ \t]*\n[ \t]*/g, "").replace(/\u00ad/g, "").split("\n");
  const output: string[] = [];
  let paragraph = "";
  let previousLine = "";
  const flush = () => { if (paragraph) output.push(paragraph); paragraph = ""; };
  const listItem = /^(?:[-*•●▪]\s|\d+[.)、]\s*|[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十]+、)/;
  for (const [index, source] of lines.entries()) {
    const line = source.trim().replace(/[ \u00a0\u3000]+/g, " ")
      .replace(/(\p{Script=Han}) +(?=\p{Script=Han})/gu, "$1")
      .replace(/ +([，。；：！？、）》」』])/g, "$1");
    if (!line) {
      const next = lines[index + 1]?.trim() || "";
      // OCR sometimes inserts an empty row after every printed line. Join only
      // an unfinished prose sentence; headings, lists, tables and paragraph
      // punctuation remain boundaries. This never changes source offsets.
      const continuation = joinSpacedLines && paragraph && previousLine.length >= 18 && next.length >= 8
        && /\p{Script=Han}/u.test(previousLine) && /\p{Script=Han}/u.test(next)
        && !/[。！？.!?；;：:][”’」』）)]?\s*[①-⑳\d\[\]]*$/u.test(previousLine)
        && !listItem.test(next) && !/^\s*(?:第[一二三四五六七八九十\d]+[章节篇]|\d+\s*$)/u.test(next)
        && !lines[index + 1]?.includes("\t") && !/^(?: {4}|\u3000{2})/.test(lines[index + 1] || "");
      if (continuation) continue;
      flush(); previousLine = ""; if (output.at(-1) !== "") output.push(""); continue;
    }
    // Lists and tab-separated text retain their line structure. No layout guessing.
    if (listItem.test(line) || source.includes("\t") || /^\d+$/.test(line) || /^第[一二三四五六七八九十百\d]+[章节篇]/u.test(line)) { flush(); previousLine = ""; output.push(line); continue; }
    if (paragraph) {
      const joinWithoutSpace = /[\p{Script=Han}，。；：！？、（《「『\u00ad-]$/u.test(paragraph)
        || /^[\p{Script=Han}，。；：！？、）》」』]/u.test(line);
      paragraph += (joinWithoutSpace ? "" : " ") + line;
    } else paragraph = line;
    previousLine = line;
  }
  flush();
  return output.join("\n").trim();
}

/** Explicit display option: only exact, known marginal lines at excerpt edges. */
export function omitSourceMarginalia(value: string, candidates: readonly string[] = []): string {
  const lines = value.replace(/\r\n?/g, "\n").split("\n");
  const visible = lines.map((text, index) => ({ text: text.trim(), index })).filter(row => row.text);
  const known = new Set(candidates.map(text => text.trim()).filter(Boolean));
  const edges = new Set([...visible.slice(0, 3), ...visible.slice(-2)].filter(row => known.has(row.text)).map(row => row.index));
  return lines.filter((_, index) => !edges.has(index)).join("\n").trim();
}
