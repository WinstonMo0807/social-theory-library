// Read-only source inventory. Business meaning and runtime reachability require review.
// Uses the repository's existing TypeScript parser; no network or application boot.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from '../web/node_modules/typescript/lib/typescript.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const relative = p => path.relative(root, p).split(path.sep).join('/');
const walk = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
const files = ['app', 'components', 'lib'].flatMap(d => walk(path.join(root, 'web', d))).filter(p => /\.(tsx?|jsx?|mjs)$/.test(p));
const fileSet = new Set(files);
const resolve = (file, spec) => {
  const base = spec.startsWith('@/') ? path.join(root, 'web', spec.slice(2)) : spec.startsWith('.') ? path.resolve(path.dirname(file), spec) : null;
  return base && [base, ...['.ts', '.tsx', '.js', '.jsx', '.mjs', '/index.ts', '/index.tsx'].map(ext => base + ext)].find(p => fileSet.has(p));
};
const modules = {};
for (const file of files) {
  const code = fs.readFileSync(file, 'utf8');
  const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true);
  const row = { imports: [], renders: [], calls: [], hooks: [], queryKeys: [], endpoints: [], redirects: [], exports: [] };
  const line = node => source.getLineAndCharacterOfPosition(node.getStart()).line + 1;
  function visit(node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      const target = resolve(file, node.moduleSpecifier.text);
      const typeOnly = Boolean(node.importClause?.isTypeOnly || node.isTypeOnly);
      if (target) row.imports.push({ target: relative(target), line: line(node), typeOnly, symbols: node.importClause?.getText(source) ?? node.exportClause?.getText(source) ?? '*' });
    }
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const name = node.tagName.getText(source);
      if (/^[A-Z]/.test(name)) row.renders.push({ name, line: line(node) });
    }
    if (ts.isCallExpression(node)) {
      const name = node.expression.getText(source);
      row.calls.push({ name, line: line(node) });
      if (/^use[A-Z]/.test(name)) row.hooks.push(name);
      if (/\.get$/.test(name) && node.arguments[0] && ts.isStringLiteral(node.arguments[0]) && /search|params|query/i.test(name)) row.queryKeys.push(node.arguments[0].text);
      if (/redirect$/.test(name)) row.redirects.push(node.arguments.map(n => n.getText(source)).join(', '));
    }
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateExpression(node)) && /^['"`]\/(?:api\/)?(?:catalog|ingestion|reading|auth|distribution)\//.test(node.getText(source))) row.endpoints.push({ expression: node.getText(source), line: line(node) });
    if (ts.isFunctionDeclaration(node) && node.name && node.modifiers?.some(m => m.kind === ts.SyntaxKind.ExportKeyword)) row.exports.push({ name: node.name.text, line: line(node) });
    ts.forEachChild(node, visit);
  }
  visit(source);
  row.hooks = [...new Set(row.hooks)].sort();
  row.queryKeys = [...new Set(row.queryKeys)].sort();
  modules[relative(file)] = row;
}
const routes = Object.entries(modules).filter(([file]) => /^web\/app\/.*\/(page|route)\.tsx?$/.test(file) || file === 'web/app/page.tsx').map(([file, row]) => ({
  url: '/' + file.replace(/^web\/app\//, '').replace(/\/?(?:page|route)\.tsx?$/, '').split('/').filter(p => p && !p.startsWith('(')).join('/'),
  source: file, kind: file.endsWith('route.ts') ? 'handler' : 'page', ...row,
})).sort((a, b) => a.url.localeCompare(b.url));
const target = path.join(root, 'docs', 'architecture', 'inventory');
fs.mkdirSync(target, { recursive: true });
const scratch = path.join(root, 'tmp', 'architecture-inventory');
fs.mkdirSync(scratch, { recursive: true });
fs.writeFileSync(path.join(scratch, 'frontend.json'), JSON.stringify({ method: 'TypeScript AST: imports, actual JSX occurrences, calls, URL parameter reads and literal/template API expressions. Type imports are flagged. An import is not proof of execution; templates remain symbolic.', routes, modules }, null, 2) + '\n');
const csv = rows => rows.map(row => row.map(x => '"' + String(x ?? '').replaceAll('"', '""') + '"').join(',')).join('\n') + '\n';
fs.writeFileSync(path.join(target, 'admin-pages.csv'), csv([
  ['URL', 'entry', 'kind', 'rendered_components', 'direct_imports', 'redirects'],
  ...routes.filter(r => r.url === '/admin' || r.url.startsWith('/admin/')).map(r => [r.url, r.source, r.kind, [...new Set(r.renders.map(x => x.name))].join('; '), r.imports.filter(i => !i.typeOnly).map(i => i.target).join('; '), r.redirects.join('; ')]),
]));
fs.writeFileSync(path.join(target, 'component-imports.csv'), csv([
  ['source', 'target', 'source_line', 'type_only', 'symbols'],
  ...Object.entries(modules).flatMap(([source, r]) => r.imports.map(i => [source, i.target, i.line, i.typeOnly, i.symbols])),
]));
fs.writeFileSync(path.join(target, 'component-renders.csv'), csv([
  ['source', 'component', 'source_line'],
  ...Object.entries(modules).flatMap(([source, r]) => r.renders.map(i => [source, i.name, i.line])),
]));
fs.writeFileSync(path.join(target, 'frontend-api-expressions.csv'), csv([
  ['source', 'source_line', 'expression'],
  ...Object.entries(modules).flatMap(([source, r]) => r.endpoints.map(i => [source, i.line, i.expression])),
]));
console.log(JSON.stringify({ modules: files.length, routes: routes.length, adminEntries: routes.filter(r => r.url === '/admin' || r.url.startsWith('/admin/')).length }));
