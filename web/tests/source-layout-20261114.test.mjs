import assert from 'node:assert/strict';
import test from 'node:test';
import {sourceLayoutHint} from '../lib/source-layout.ts';
import {formatSourceText,omitSourceMarginalia} from '../lib/source-text.ts';

test('quantitative layout hints preserve uncertainty and require no services',()=>{
  assert.equal(sourceLayoutHint('表3:组织团结的凝聚力量表的题器构成\n变量名\nQ27_1\n我的工作能力经常得到肯定'),'table');
  assert.equal(sourceLayoutHint('测量模型如下：\n\nX= T+S+e\n\n其中X是观测值。'),'formula');
  assert.equal(sourceLayoutHint('类别\t数量\t比例\n甲\t10\t.25'),'table');
  assert.equal(sourceLayoutHint('作者认为表述与社会经验有关，本文提出三种解释。'),null);
});
test('short OCR continuations join while real paragraphs and source characters remain',()=>{
  const first='在这个意义下，我们以下的讨论中特别强调稳定的社会结';
  const raw=`${first}\n\n\n构和机制。\n\n第二，我们从不同视角考察。`;
  assert.equal(formatSourceText(raw),`${first}构和机制。\n\n第二，我们从不同视角考察。`);
  assert.equal(formatSourceText(raw).replace(/\s/g,''),raw.replace(/\s/g,''));
  assert.equal(omitSourceMarginalia('组织社会学十讲 263\n\n原文内容。',['组织社会学十讲']),'原文内容。');
  assert.equal(omitSourceMarginalia('组织社会学十讲包含263个例子\n\n原文内容。',['组织社会学十讲']),'组织社会学十讲包含263个例子\n\n原文内容。');
});
