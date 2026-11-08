import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

const files = [];
function walk(dir) { for (const e of readdirSync(dir, { withFileTypes: true })) { const p = resolve(dir, e.name); if (e.isDirectory()) walk(p); else if (p.endsWith('.tsx')) files.push(p); } }
walk(resolve('app')); walk(resolve('components'));

test('all menu and disclosure call sites have an explicit presentation policy', () => {
  const unclassified = [], invalid = []; let visible = 0, collected = 0, menus = 0, selects = 0;
  for (const file of files) {
    const sf = ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    function visit(n) {
      if (ts.isJsxElement(n)) {
        const tag = n.openingElement.tagName.getText(sf), attrs = n.openingElement.attributes.properties;
        const has = key => attrs.some(a => ts.isJsxAttribute(a) && a.name.text === key);
        const where = `${file}:${sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1}`;
        if (tag === 'details') { if (has('data-action-menu')) menus++; else if (has('data-disclosure')) collected++; else unclassified.push(where); }
        if (tag === 'select') { selects++; if (!has('data-stl-select')) unclassified.push(where); }
        if (has('data-content-section')) {
          visible++;
          if (tag !== 'section' || has('open') || has('onToggle')) invalid.push(where);
          if (n.children.some(c => ts.isJsxElement(c) && c.openingElement.tagName.getText(sf) === 'summary')) invalid.push(where);
        }
        if (tag === 'summary' && (!ts.isJsxElement(n.parent) || n.parent.openingElement.tagName.getText(sf) !== 'details')) invalid.push(where);
      }
      ts.forEachChild(n, visit);
    }
    visit(sf);
  }
  assert.deepEqual(unclassified, [], 'Unreviewed native controls');
  assert.deepEqual(invalid, [], 'Expanded content must not keep disclosure-only semantics');
  assert.ok(visible > 170 && collected > 100 && menus >= 37 && selects >= 296, 'Audit must include the full app/component tree');
});

test('help navigation and account resources do not require a disclosure click', () => {
  const help = readFileSync('components/public/support-hero.tsx','utf8');
  const account = readFileSync('components/reader-center.tsx','utf8');
  assert.ok(!help.includes('<details'));
  assert.ok(account.includes('className="reader-account-navigation"'));
  assert.ok(!account.includes('reader-legacy-nav'));
  assert.ok(!readFileSync('components/public/support-hub.tsx','utf8').includes('stl4-support-reading-final-r2.png'));
});
