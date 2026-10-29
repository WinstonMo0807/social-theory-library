import assert from "node:assert/strict";
import test from "node:test";
import { formatSourceText } from "../lib/source-text.ts";

test("OCR wrapping preserves words, punctuation, paragraphs and source markers", () => {
  assert.equal(formatSourceText("《共\n产党宣言》中对技术进步的赞歌。\n资本主\n义的发展。[24]\n\n第二段，Social\nTheory Library。"), "《共产党宣言》中对技术进步的赞歌。资本主义的发展。[24]\n\n第二段，Social Theory Library。");
  assert.equal(formatSourceText("社会 理论 ， 研究 。"), "社会理论， 研究。");
  assert.equal(formatSourceText("well-\nknown inter\u00ad\nnational"), "well-known international");
  assert.equal(formatSourceText("第一段\r\n\r\n1. 条目甲\r\n2. 条目乙\r\n名称\t数量\r\n甲\t3"), "第一段\n\n1. 条目甲\n2. 条目乙\n名称\t数量\n甲\t3");
});

test("presentation never adds or removes source characters except discretionary soft hyphens", () => {
  const sample = "<b>仅文字</b>\n中文（man）[25]，1998 年。\n\nhttps://example.org/a-b\n- 保留列表\n- 末项";
  const compact = text => text.replace(/\s|\u00ad/g, "");
  assert.equal(compact(formatSourceText(sample)), compact(sample));
  assert.equal(formatSourceText(formatSourceText(sample)), formatSourceText(sample));
  assert.equal(formatSourceText(" \n \t "), "");
});
