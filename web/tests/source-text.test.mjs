import assert from "node:assert/strict";
import test from "node:test";
import { formatSourceText, omitSourceMarginalia } from "../lib/source-text.ts";

test("OCR wrapping preserves words, punctuation, paragraphs and source markers", () => {
  assert.equal(formatSourceText("《共\n产党宣言》中对技术进步的赞歌。\n资本主\n义的发展。[24]\n\n第二段，Social\nTheory Library。"), "《共产党宣言》中对技术进步的赞歌。资本主义的发展。[24]\n\n第二段，Social Theory Library。");
  assert.equal(formatSourceText("社会 理论 ， 研究 。"), "社会理论， 研究。");
  assert.equal(formatSourceText("well-\nknown inter\u00ad\nnational"), "well-known international");
  assert.equal(formatSourceText("第一段\r\n\r\n1. 条目甲\r\n2. 条目乙\r\n名称\t数量\r\n甲\t3"), "第一段\n\n1. 条目甲\n2. 条目乙\n名称\t数量\n甲\t3");
});

test("OCR blank rows inside unfinished Chinese sentences are joined, real boundaries remain", () => {
  const first = "如果没有民族互利，则是不实在的。所以，也可简要地说，民族";
  const second = "团结就是民族互利与民族认同的有机统一、相互促进。";
  const third = "针对中国社会目前面对的民族问题的实际，郑先生指出：";
  const raw = `${first}\n\n${second}\n\n${third}\n\n第一项说明。`;
  assert.equal(formatSourceText(raw), `${first}${second}\n\n${third}\n\n第一项说明。`);
  assert.equal(formatSourceText(raw, {joinSpacedLines:false}), raw);
  assert.equal(formatSourceText(formatSourceText(raw)), formatSourceText(raw));
  for (const boundary of ["第一章 民族与社会", "1. 列表材料及其来源", "项目\t数量\t说明", "    另起一段的内容足够长", "316"]) {
    assert.ok(formatSourceText(`${first}\n\n${boundary}`).includes("\n"));
  }
  assert.equal(formatSourceText(raw).replace(/\s/g,""), raw.replace(/\s/g,""));
  assert.equal(formatSourceText("第一章 民族与社会\n正文从这里开始。"), "第一章民族与社会\n正文从这里开始。");
  assert.ok(formatSourceText(`${first}。” ①\n\n${third}`).includes("\n\n"));
});

test("marginalia removal is explicit and exact, and never removes a middle numeric paragraph", () => {
  const raw="书名\n316\n\n开篇原文。\n中间原文。\n316\n后续原文。\n结尾原文。\n317";
  assert.equal(omitSourceMarginalia(raw),raw);
  assert.equal(omitSourceMarginalia(raw,["书名","316","317"]),"开篇原文。\n中间原文。\n316\n后续原文。\n结尾原文。");
  assert.equal(omitSourceMarginalia("书名的一部分\n正文。",["书名"]),"书名的一部分\n正文。");
});

test("presentation never adds or removes source characters except discretionary soft hyphens", () => {
  const sample = "<b>仅文字</b>\n中文（man）[25]，1998 年。\n\nhttps://example.org/a-b\n- 保留列表\n- 末项";
  const compact = text => text.replace(/\s|\u00ad/g, "");
  assert.equal(compact(formatSourceText(sample)), compact(sample));
  assert.equal(formatSourceText(formatSourceText(sample)), formatSourceText(sample));
  assert.equal(formatSourceText(" \n \t "), "");
});
