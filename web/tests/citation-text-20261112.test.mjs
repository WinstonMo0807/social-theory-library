import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {CitationText} from '../components/citation-text.tsx';

test('manual-copy citation preserves book-title italics without accepting HTML',()=>{
  const html=renderToStaticMarkup(React.createElement(CitationText,{text:'作者. 危险<script>. 出版社.',italicTitle:'危险<script>'}));
  assert.match(html, /<i>危险&lt;script&gt;<\/i>/);
  assert.doesNotMatch(html, /<script>|download=/);
  assert.match(html, /aria-readonly="true"/);
  const gbt=renderToStaticMarkup(React.createElement(CitationText,{text:'作者. 书名[M]. 北京: 出版社, 2020: 12.'}));
  assert.doesNotMatch(gbt, /<i>/);
  assert.match(gbt, /2020: 12\./);
});
