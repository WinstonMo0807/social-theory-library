// Optional local documentation check. No application/production connection.
// npm install --prefix tmp/mermaid-validation mermaid@11 --ignore-scripts --no-audit --no-fund
// node scripts/check-architecture-mermaid.mjs [--channel msedge]
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { chromium } from '../web/node_modules/playwright/index.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'tmp/mermaid-validation/node_modules/mermaid/dist');
const out = path.join(root, 'tmp/mermaid-validation/rendered');
fs.mkdirSync(out, { recursive: true });
const docs = [path.join(root, 'README.md'), ...fs.readdirSync(path.join(root, 'docs/architecture')).filter(name => name.endsWith('.md')).map(name => path.join(root, 'docs/architecture', name))];
const blocks = docs.flatMap(file => [...fs.readFileSync(file, 'utf8').matchAll(/^```mermaid\r?\n([\s\S]*?)^```/gm)].map((match, i) => ({ file: path.relative(root, file).replaceAll('\\', '/'), block: i + 1, code: match[1] })));
const html = '<!doctype html><meta charset="utf-8"><style>body{margin:24px;background:white;font-family:Arial,"Microsoft YaHei",sans-serif}#diagram{width:1800px}svg{max-width:100%}</style><div id="diagram"></div><script type="module">import mermaid from "/mermaid.esm.min.mjs";mermaid.initialize({startOnLoad:false,securityLevel:"strict",theme:"neutral",fontFamily:"Arial, Microsoft YaHei, sans-serif"});window.auditMermaid=mermaid;</script>';
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  if (pathname === '/') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(html); return; }
  const file = path.resolve(dist, '.' + decodeURIComponent(pathname));
  if (!file.startsWith(dist + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404).end(); return; }
  res.setHeader('Content-Type', file.endsWith('.mjs') || file.endsWith('.js') ? 'text/javascript' : 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const channelIndex = process.argv.indexOf('--channel');
let browser;
const results = [];
try {
  browser = await chromium.launch({ headless: true, ...(channelIndex >= 0 ? { channel: process.argv[channelIndex + 1] } : {}) });
  const page = await browser.newPage({ viewport: { width: 1850, height: 1200 }, deviceScaleFactor: 1 });
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(() => Boolean(window.auditMermaid));
  for (const [index, block] of blocks.entries()) {
    try {
      const result = await page.evaluate(async ({ code, id }) => {
        await window.auditMermaid.parse(code);
        const { svg } = await window.auditMermaid.render(id, code);
        document.querySelector('#diagram').innerHTML = svg;
        const element = document.querySelector('#diagram svg');
        return { svg, viewBox: element.getAttribute('viewBox'), nodes: element.querySelectorAll('.node, .entityBox, .actor').length };
      }, { code: block.code, id: `auditDiagram${index}` });
      const name = `${String(index + 1).padStart(2, '0')}-${path.basename(block.file, '.md')}-${block.block}`;
      fs.writeFileSync(path.join(out, name + '.svg'), result.svg);
      await page.locator('#diagram').screenshot({ path: path.join(out, name + '.png') });
      results.push({ file: block.file, block: block.block, status: 'rendered', viewBox: result.viewBox, nodes: result.nodes });
    } catch (error) {
      results.push({ file: block.file, block: block.block, status: 'failed', error: String(error.message).split('\n').slice(0, 7).join('\n') });
    }
  }
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
const version = JSON.parse(fs.readFileSync(path.join(dist, '../package.json'), 'utf8')).version;
const report = { mermaid: version, blocks: blocks.length, passed: results.filter(r => r.status === 'rendered').length, results };
fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.passed === blocks.length ? 0 : 1;
