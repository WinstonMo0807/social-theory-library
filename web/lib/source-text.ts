/** Presentation only. Never use this text for source matching, offsets or storage. */
export function formatSourceText(value: string): string {
  const lines = value.replace(/\r\n?/g, "\n").replace(/\u00ad[ \t]*\n[ \t]*/g, "").replace(/\u00ad/g, "").split("\n");
  const output: string[] = [];
  let paragraph = "";
  const flush = () => { if (paragraph) output.push(paragraph); paragraph = ""; };
  const listItem = /^(?:[-*•●▪]\s|\d+[.)、]\s*|[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十]+、)/;
  for (const source of lines) {
    const line = source.trim().replace(/[ \u00a0\u3000]+/g, " ")
      .replace(/(\p{Script=Han}) +(?=\p{Script=Han})/gu, "$1")
      .replace(/ +([，。；：！？、）》」』])/g, "$1");
    if (!line) { flush(); if (output.at(-1) !== "") output.push(""); continue; }
    // Lists and tab-separated text retain their line structure. No layout guessing.
    if (listItem.test(line) || source.includes("\t")) { flush(); output.push(line); continue; }
    if (paragraph) {
      const joinWithoutSpace = /[\p{Script=Han}，。；：！？、（《「『\u00ad-]$/u.test(paragraph)
        || /^[\p{Script=Han}，。；：！？、）》」』]/u.test(line);
      paragraph += (joinWithoutSpace ? "" : " ") + line;
    } else paragraph = line;
  }
  flush();
  return output.join("\n").trim();
}
